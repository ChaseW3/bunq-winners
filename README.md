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
ELEVENLABS_API_KEY=your_key       # optional, TTS falls back to browser
LLM_MODEL=claude-sonnet-4-6       # optional
```

### 3. Start the server

```bash
# Against the real bunq sandbox
uv run python scripts/serve_test.py

# No bunq key needed — uses fake data
BUNQ_FAKE=1 uv run python scripts/serve_test.py
```

Open **http://localhost:8000** in Chrome.

### 4. Interact

- **Tap once** → blur effect (accessibility demo)
- **Tap again** → lock screen
- **Tap rhythm** (tap-tap-PAUSE-tap-tap) → unlock
- **Hold** → record voice command
- **Release** → sends to Lynn

## Features

**Voice banking**
- Check balance and account details
- List and search recent transactions
- Send payments via draft-then-confirm flow
- Request money from contacts
- Manage scheduled/recurring payments
- Block or update cards

**Financial intelligence**
- Answers questions like "can I afford this?", "where's my money going?", "anything unusual this month?" using live transaction data

**Accessibility**
- All amounts spoken as words ("twenty euros"), never symbols
- IBANs read with NATO phonetic alphabet
- Tap-once to confirm payments, tap-twice to cancel
- Earcon audio cues for every state transition
- No visual information assumed

**Safety**
- Payments always go through a draft → confirm flow
- Rhythm-tap passcode required before money moves
- Lynn never sends money without explicit user confirmation

## Project structure

```
backend/
  bunq_client/     BunqClient protocol + RealBunqClient implementation
  orchestrator/    LLM loop, system prompt, Anthropic adapter
  tools/           36 tool implementations + registry
  session/         In-memory session store
  tests/           Unit tests + FakeBunqClient
scripts/
  serve_test.py    FastAPI dev server (entry point)
frontend/
  demo-transition.html   Full voice UI (tap auth, voice orb, payment flow)
```

## Running tests

```bash
pytest backend/tests/
```
