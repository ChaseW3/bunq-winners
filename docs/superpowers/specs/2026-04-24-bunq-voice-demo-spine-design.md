# bunq Voice — Demo Spine Design

**Date:** 2026-04-24
**Status:** Approved for implementation planning
**Scope:** Minimum architecture to deliver the three on-stage demo flows. Everything outside those three flows is explicitly deferred.

---

## 1. Scope

Three flows must work live on stage:

1. **Balance query** — "What's my balance?" → spoken reply.
2. **Send money** — "Send €20 to Michelle" → spoken repeat-back → biometric confirm → bunq draft payment created and confirmed.
3. **Scan bill** — camera capture of paper invoice → vision model extracts payee IBAN/amount → spoken confirm → biometric → payment.

Out of scope for this spec: webhooks / proactive notifications, card controls, request-money, insights/summarization, wake word, native mobile wrapper, multi-account switching, multi-language, production deployment, persistent storage.

## 2. High-level shape

```
┌────────────────────────┐         ┌──────────────────────────────────┐
│   Mobile PWA (browser) │         │   FastAPI backend                │
│                        │         │                                  │
│  • Push-to-talk mic    │ ──WS──▶ │  /voice  (audio in, audio out)   │
│  • Camera capture      │ ──POST─▶│  /scan   (image → extracted JSON)│
│  • Audio playback      │ ◀──WS── │                                  │
│  • Confirm sheet       │         │  ┌────────────────────────────┐  │
│  • Service worker      │         │  │  Orchestrator              │  │
│                        │         │  │   STT → LLM(tools) → TTS   │  │
└────────────────────────┘         │  └──────┬─────────────────────┘  │
                                   │         │                        │
                                   │         ▼                        │
                                   │  ┌────────────────────────────┐  │
                                   │  │  bunq client (official SDK)│  │
                                   │  └──────┬─────────────────────┘  │
                                   └─────────┼────────────────────────┘
                                             ▼
                                       bunq sandbox API
```

Four external services: bunq sandbox API, LLM provider (Claude Sonnet or GPT-4o — chosen at build based on API credits), Whisper (STT), ElevenLabs or OpenAI TTS.

**Key decisions:**
- **PWA frontend**, no native wrapper. Mic + camera via `getUserMedia`. Opens on a phone; looks like an app; ships in hours.
- **Thin client, fat backend.** All secrets and orchestration on the server. Browser is dumb: capture audio/image, play audio, trigger biometric prompt.
- **Python + FastAPI backend.** Official bunq SDK handles installation/session/signing. FastAPI supports streaming responses for TTS.
- **No database.** Session state is an in-memory dict; server restart during demo is a bigger problem than state loss.

## 3. Backend modules

Five focused modules with clear boundaries.

| Module | Responsibility |
|---|---|
| `transport/` | WebSocket + REST endpoints. Accepts audio chunks and images, streams audio back. No business logic. |
| `orchestrator/` | One function per user turn: `run_turn(session, audio) -> audio`. Owns the STT → LLM → TTS sequence. |
| `tools/` | Pure functions over a bunq client, exposed to the LLM. Each has a JSON schema. |
| `bunq_client/` | Thin wrapper over the official SDK. Installation/session/context done once at startup; exposes typed methods. |
| `media/` | STT + TTS adapters behind one interface each. Swappable providers. |
| `session/` | In-memory store for per-session state. |

**Isolation rules:**
- Tools never touch HTTP or audio.
- Orchestrator never touches bunq directly — only through tools.
- Transport never imports tools or bunq_client.

These boundaries are what let us swap models, add tools, or rewrite transport without cascading changes.

## 4. The three flows, traced

### 4.1 Balance query (one turn, stateless)

```
mic → WS audio chunks → STT → text: "what's my balance"
  → LLM with tools → tool_call: get_balance()
  → bunq_client.balance() → €1,247.00
  → LLM composes reply: "You have 1,247 euros in your main account."
  → TTS → audio stream → browser plays
```

### 4.2 Send money (two turns, stateful)

**Turn 1 — "Send 20 euros to Michelle":**
```
STT → LLM → tool calls in sequence:
  find_contact("Michelle") → [{id, name: "Michelle Weng", iban}]
  create_draft_payment(account, iban, 20.00, "")
    → draft_id stored in session.pending_draft
LLM reply: "Sending 20 euros to Michelle Weng. Say yes to confirm."
Response envelope includes requires_confirm: true.
```

**Client-side biometric gate:** when the response carries `requires_confirm: true`, the browser shows a WebAuthn or styled confirm prompt. Only on success does it send the next user turn. The LLM never learns about biometrics — that is a transport concern.

**Turn 2 — "yes":**
```
STT → LLM (system prompt contains current pending_draft)
  → tool_call: confirm_draft_payment(draft_id)
  → session.pending_draft cleared
LLM reply: "Done. New balance: 1,227 euros."
```

If the user says "no" / "cancel" / "never mind", the LLM calls `cancel_pending()` instead.

### 4.3 Scan bill

```
camera → POST /scan (multipart image)
  → vision LLM with structured prompt
    → JSON {creditor, iban, amount, due_date, reference}
  → session.pending_draft written (source="scan")
  → response: spoken text + JSON
  → TTS plays "This is an invoice from KPN for 47 euros 82..."
user says "yes" → same confirm path as flow 4.2 turn 2.
```

Scan reuses the confirm path. Scan produces a pending_draft; "yes" confirms it.

## 5. Tools exposed to the LLM

```
get_balance(account_id?: str) -> {account, balance, currency}
  # omit account_id → returns primary

list_recent_payments(account_id?: str, limit: int = 5)
  -> [{date, counterparty, amount, description}]

find_contact(query: str) -> [{id, name, iban}]
  # fuzzy match over cached contact list; 0/1/many results

create_draft_payment(account_id, iban, amount, description) -> {draft_id}
  # also writes session.pending_draft = {draft_id, amount, counterparty, source}

confirm_draft_payment(draft_id: str) -> {status, new_balance}
  # requires session.pending_draft.draft_id to match; clears on success

cancel_pending() -> {}
  # user declined — clears session.pending_draft
```

Scan is not a tool. It is a separate endpoint because the image never goes through the voice LLM.

## 6. Session state

Keyed by session id, in-memory dict:

```python
{
  "bunq_user_id": int,
  "primary_account_id": int,
  "contacts_cache": [...],          # loaded once at session start
  "pending_draft": {                # None unless mid-flow
    "draft_id": str,
    "amount": Decimal,
    "counterparty": str,
    "source": "voice" | "scan",
  },
  "history": [...],                 # last N LLM turns
}
```

**System prompt structure per turn:**
- **Static:** "You are bunq Voice. You help users bank by voice. Use tools. Keep replies under 2 sentences. Amounts must be spoken clearly."
- **Dynamic:** a `current_session_state` block. If `pending_draft` is set, the prompt says: *"The user has a pending payment: €20 to Michelle Weng. If they confirm ('yes', 'confirm', 'do it'), call confirm_draft_payment. If they decline, call cancel_pending."*

Multi-turn confirmation is robust because the LLM does not have to "remember" — state is freshly injected every turn.

## 7. Repo layout

```
bunq-winners/
├── backend/
│   ├── app.py                      # FastAPI entrypoint
│   ├── transport/
│   │   ├── voice_ws.py             # /voice WebSocket
│   │   ├── scan.py                 # /scan POST
│   │   └── session.py              # /session create/destroy
│   ├── orchestrator/
│   │   ├── turn.py                 # run_turn(session, audio)
│   │   ├── scan.py                 # run_scan(session, image)
│   │   └── prompts.py              # system prompt + state injection
│   ├── tools/
│   │   ├── registry.py             # JSON schemas + dispatch
│   │   ├── balance.py
│   │   ├── payments.py
│   │   └── contacts.py
│   ├── bunq_client/
│   │   ├── client.py               # SDK wrapper, singleton
│   │   └── bootstrap.py            # installation/session at startup
│   ├── media/
│   │   ├── stt.py                  # Whisper adapter
│   │   └── tts.py                  # ElevenLabs/OpenAI adapter
│   ├── session/
│   │   └── store.py                # in-memory session dict
│   └── tests/
│       ├── test_tools.py
│       ├── test_orchestrator.py
│       └── test_flows.py
├── frontend/
│   ├── index.html
│   ├── app.js                      # mic, camera, WS, playback
│   ├── confirm.js                  # biometric/confirm sheet
│   ├── styles.css
│   └── sw.js                       # service worker (PWA)
├── fixtures/
│   ├── audio/                      # pre-recorded demo phrases
│   └── bills/                      # sample invoice images
└── docs/
    └── superpowers/specs/
```

## 8. Testing

Hackathon-appropriate — not exhaustive.

- **Tools:** unit tests against a mocked bunq client. Fast; catches schema drift.
- **Orchestrator:** tests with a fake LLM that returns scripted tool calls. Verifies the state machine (draft → confirm, draft → cancel, scan → confirm).
- **Flows:** end-to-end against bunq sandbox using pre-recorded audio fixtures. Run before the demo.
- **Not tested:** browser UI. Too costly for the timeframe. Manually rehearse instead.

## 9. Config & secrets

`.env` loaded at startup via `config.py`, validated fail-fast:

- `BUNQ_API_KEY` — sandbox personal API key.
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — LLM provider.
- `OPENAI_API_KEY` — Whisper STT (may overlap with above).
- `ELEVENLABS_API_KEY` — TTS (optional; OpenAI TTS is a fallback).

`.env` is already in `.gitignore`.

## 10. Explicit non-goals

- Webhooks / proactive notifications.
- Native mobile app.
- Persistent storage.
- Multi-account or multi-user isolation.
- Production-grade auth. Sessions are trusted by id; fine for a single-user demo.
- Dutch-language support. English only for the demo.
- Offline mode.
- Wake-word detection. Push-to-talk only.

These can be added after the hackathon without reshaping the architecture.
