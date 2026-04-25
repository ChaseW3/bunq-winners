# Lynn — bunq Voice Banking Assistant

Lynn is an accessibility-first voice banking assistant built on bunq. Designed for blind and visually impaired users, it lets you manage your finances entirely through voice and tap gestures — no screen required.

## Stack

| Layer | Technology |
|---|---|
| LLM | Claude (Anthropic) |
| Speech-to-text | OpenAI Whisper |
| Text-to-speech | ElevenLabs |
| Banking API | bunq |
| Backend | FastAPI (Python) |
| Frontend | Single HTML file |

## Running locally

### 1. Install dependencies

```bash
pip install anthropic openai fastapi uvicorn python-dotenv bunq-sdk-python
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your keys:

```bash
BUNQ_API_KEY=your_bunq_api_key
BUNQ_ENVIRONMENT=SANDBOX          # or PRODUCTION
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key
ELEVENLABS_API_KEY=your_key       # optional, TTS falls back to silence
LLM_MODEL=claude-sonnet-4-6       # optional
```

### 3. Start the server

**bash / zsh:**
```bash
# Real bunq sandbox
uv run python main.py

# Fake data — no bunq API key needed
BUNQ_FAKE=1 uv run python main.py
```

**PowerShell:**
```powershell
$env:BUNQ_FAKE=1; uv run python main.py
```

Open **http://localhost:8000** in Chrome.

### 4. Interact

**Lock screen (first time):**
- **Tap once** → blur effect (accessibility demo)
- **Tap again** → show lock screen
- **Rhythm pattern** (tap-tap-PAUSE-tap-tap) → unlock

**After unlock:**
- **Hold** to record a voice command, **release** to send
- **Single tap** → quick balance
- **Double tap** → read IBAN
- **Voice commands:** "slower", "faster", "repeat" (handled client-side)

**During a payment:**
- **Single tap** → confirm payment (then enter rhythm passcode)
- **Double tap** → cancel payment

## Features

**Voice banking**
- Check balance and account details
- List and search recent transactions
- Send payments via draft → confirm flow
- Request money from contacts
- Manage scheduled/recurring payments
- Block or update cards

**Financial intelligence**
- Answers reasoning questions like "can I afford this?", "where's my money going?", "anything unusual this month?" by synthesizing live transaction data via the `financial_context` tool

**Smart contact matching**
- Exact match → proceeds directly
- Fuzzy match (e.g. STT mishears "Wang" as "Wayne") → Lynn asks "Did you mean Chase Wang?"
- Multiple matches → Lynn reads the names and asks which one

**Accessibility**
- All amounts spoken as words ("twenty euros"), never symbols
- IBANs read with NATO phonetic alphabet
- Tap-once to confirm payments, tap-twice to cancel
- Earcon audio cues for every state transition
- No visual information assumed

**Safety**
- Sending money always goes through a draft → confirm flow
- Rhythm-tap passcode required before money moves
- Lynn never sends money without explicit user confirmation

## Project structure

```
main.py                   FastAPI dev server (entry point)
backend/
  bunq_client/            BunqClient protocol + RealBunqClient implementation
  orchestrator/           LLM loop, system prompt, Anthropic adapter
  tools/                  36 tool implementations + registry
  session/                In-memory session store
  tests/                  Unit tests + FakeBunqClient
frontend/
  demo-transition.html    Full voice UI (lock screen, voice orb, payment flow)
  audio/                  Earcon WAV files
scripts/
  seed_sandbox.py         Seed bunq sandbox with test transactions
  repl_fake.py            Text REPL against the fake client (for prompt iteration)
```

## Running tests

```bash
pytest backend/tests/
```
