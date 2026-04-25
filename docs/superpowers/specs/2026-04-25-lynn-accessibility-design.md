# Lynn — bunq Accessibility Voice Assistant

## Overview

Transform the existing bunq voice agent into "Lynn," a voice assistant specifically designed to make bunq accessible for blind users. The demo uses a split-screen layout: the left side shows the phone UI (teammate-built), the right side shows a real-time accessibility log that makes the blind-friendly design visible to hackathon judges.

The core differentiator from a generic voice agent: every interaction is designed so the user never needs to see the screen, and judges can watch the accessibility reasoning happen in real time.

## Target Audience

Hackathon judges evaluating multimodal AI + bunq API projects. The product vision is financial independence for blind users; the demo must make that story undeniable at a glance.

## Architecture

### Split-Screen Layout

- **Left panel (~60%):** Teammate's phone mockup (`demo-transition.html`) with the 3-state click transition (app screenshot → blurred → voice orb). This is the product — what the blind user experiences.
- **Right panel (~40%):** Accessibility log. Real-time scrolling event feed showing what Lynn is doing and why each choice serves a blind user. Dark background, monospace, color-coded tags. This is for judges only.

### Transition Choreography

1. **Click 1:** Screenshot blurs (0.7s ease). Log panel stays hidden.
2. **Click 2:** Orb fades in (0.6s ease, 0.3s delay). Log panel slides in from the right with matching timing. Greeting earcon plays. Lynn speaks: "Hi, I'm Lynn, your bunq accessibility assistant. What can I do for you today?"

The log panel starts at `opacity: 0; transform: translateX(40px)` and transitions to `opacity: 1; transform: translateX(0)` in sync with the orb.

## Features

### 1. Auto-Greeting

On activation (state 2 of the transition):
1. Greeting earcon plays (~0.5s warm rising chime)
2. Orb transitions to "speaking" state
3. TTS speaks: "Hi, I'm Lynn, your bunq accessibility assistant. What can I do for you today?"
4. Log entry: `AUDIO: AUTO-GREET — Lynn introduced herself on load, no visual context needed`
5. Orb returns to idle
6. Only plays once per session (flag in session state)

### 2. Earcon System

Six distinct audio cues for state transitions:

| Earcon | Trigger | Sound | Duration |
|--------|---------|-------|----------|
| `greeting` | Activation / page load | Warm rising chime | ~0.5s |
| `mic-on` | User starts hold-to-talk | Soft click/blip | ~0.2s |
| `mic-off` | User releases hold | Softer click | ~0.2s |
| `thinking` | Agent processing | Subtle ambient pulse | Loops until response |
| `success` | Action completed successfully | Bright double-ding | ~0.5s |
| `error` | Something went wrong | Low buzz/tone | ~0.5s |

Earcons are initially prototyped using the Web Audio API (OscillatorNode + GainNode envelopes). Once the sounds are finalized, they are exported as small audio files (`.mp3`) in `frontend/audio/` and played via `<audio>` elements for consistency across browsers. Each earcon triggers a corresponding log entry.

### 3. System Prompt Overhaul

New behavioral rules added to `backend/orchestrator/prompts.py`:

- **Persona:** Lynn, bunq accessibility assistant
- **No visual references:** Never say "as shown above", "you can see", "the screen shows", "look at", etc.
- **Full word amounts:** "twenty euros and fifty cents", never "€20.50" or "20.50"
- **NATO alphabet for IBANs:** "November Lima four two Bravo Uniform November Quebec..."
- **Count-then-list:** When listing items, announce count first ("You have 3 recent transactions"), then read one at a time
- **Readback before action:** Always read back full details (recipient, amount, IBAN, description) before executing any payment or action
- **Voice confirmation:** "Say confirm to proceed, or cancel to stop" — no biometric, no screen tap
- **Navigation offers:** After reading a list item, offer "Want to hear the next one?"
- **Concise but complete:** Don't skip details a sighted user would read on screen

Existing tool-calling logic, safety guardrails, and draft-then-confirm flow remain unchanged.

### 4. Accessibility Log Panel

Real-time event feed on the right side of the screen.

**Visual style:**
- Dark background (#0a0a0a), monospace font (JetBrains Mono or system monospace)
- Auto-scrolling, newest events at bottom
- Each event: colored tag + event name + plain-English accessibility rationale

**Event categories and colors:**

| Tag | Color | Events |
|-----|-------|--------|
| `AUDIO` | Cyan (#00C8FF) | Greeting, TTS playback |
| `EARCON` | Magenta (#FF3D8B) | Sound cue played and why |
| `SPEECH` | Green (#4ADE80) | Readback, phonetic IBAN, full-word amounts |
| `STATE` | Yellow (#FACC15) | State transitions communicated non-visually |
| `ACTION` | Bright green (#22C55E) | Voice-confirmed actions |
| `ERROR` | Red (#EF4444) | Error handling via audio |

**Example flow — "Send 20 euros to Michelle":**
```
EARCON: mic-on         Audio cue confirms recording started
STATE: listening       Lynn is listening — ambient tone active
EARCON: mic-off        Audio confirms input captured
STATE: thinking        Ambient tone plays while processing
SPEECH: full-amount    Speaking "twenty euros" not "€20.00"
SPEECH: iban-phonetic  Reading IBAN with NATO alphabet
SPEECH: readback       Full detail readback before action
ACTION: voice-confirm  Awaiting spoken "confirm" — no screen needed
EARCON: success        Audio confirms payment completed
```

**Data flow:** The backend returns accessibility event metadata in the response JSON alongside the normal LLM reply. Frontend-only events (earcons, mic state) are logged directly by the frontend JS.

### 5. Voice Agent Wiring

Port the following from `index.html` to `demo-transition.html`:

**Port:**
- Push-to-hold mic recording (MediaRecorder API → webm blob)
- POST `/voice` (audio → STT → LLM → response)
- POST `/text` (for voice confirmation flow)
- TTS playback (ElevenLabs via `/config` API key, fallback to OpenAI)
- Orb state management (idle → listening → thinking → speaking) mapped to CSS classes
- Session management (session ID in request headers)

**New:**
- Earcon playback on every state transition
- Auto-greeting trigger on activation
- Accessibility log rendering from both frontend events and backend metadata
- Voice confirmation flow: Lynn reads back → user holds to say "confirm"/"cancel" → confirm_draft_payment
- Entire screen is one hold-to-talk target (not just the orb)

**Don't port:**
- Old particle canvas animation (teammate's orb replaces it)
- Tool call inspection panel (accessibility log replaces it)
- Visual transcript panel (Lynn speaks everything; log shows it for judges)

### 6. Voice Confirmation Flow

For payments and other consequential actions:

1. LLM calls `create_draft_payment` → backend stores pending draft
2. Lynn speaks full readback: "Sending twenty euros to Michelle at November Lima four two Bravo Uniform November Quebec zero one two three four five six seven eight nine. Say confirm to proceed, or cancel to stop."
3. Log shows: `SPEECH: readback`, `ACTION: voice-confirm — Awaiting spoken "confirm", no screen needed`
4. User holds to speak "confirm" or "cancel"
5. On "confirm": `confirm_draft_payment` called, success earcon plays, Lynn announces result and new balance
6. On "cancel": `cancel_draft_payment` called, Lynn confirms cancellation

### 7. Touch Simplification

The entire screen area is one touch target. Hold anywhere to talk. No buttons, no navigation, no gestures to discover. This is a deliberate accessibility choice: a blind user doesn't need to find a specific button.

## Backend Changes

### Response Format Extension

The `/voice` and `/text` endpoints return an additional `accessibility_events` array:

```json
{
  "reply": "Sending twenty euros to Michelle...",
  "tool_calls": [...],
  "accessibility_events": [
    {"type": "SPEECH", "event": "full-amount", "detail": "Speaking 'twenty euros' not '€20.00'"},
    {"type": "SPEECH", "event": "iban-phonetic", "detail": "Reading IBAN with NATO alphabet"},
    {"type": "SPEECH", "event": "readback", "detail": "Full detail readback before action"},
    {"type": "ACTION", "event": "voice-confirm", "detail": "Awaiting spoken 'confirm' — no screen needed"}
  ]
}
```

These events are derived from the tool calls and response content by the orchestrator after the LLM turn completes. The logic inspects:
- Whether amounts appear in the response (→ `full-amount` event)
- Whether IBANs appear (→ `iban-phonetic` event)
- Whether a draft was created (→ `readback` + `voice-confirm` events)
- Whether an error occurred (→ `error` event)

## Files Changed

| File | Change |
|------|--------|
| `frontend/demo-transition.html` | Add accessibility log panel, wire voice agent, earcons, auto-greeting, hold-to-talk |
| `backend/orchestrator/prompts.py` | System prompt overhaul for Lynn persona + accessibility rules |
| `backend/orchestrator/llm.py` | Generate accessibility_events in response |
| `scripts/serve_test.py` | Serve demo-transition.html instead of index.html, update response format |
| `frontend/index.html` | Delete after migration complete |

## Out of Scope

- Screen reader / ARIA support (voice-first replaces this)
- Haptic feedback (device-dependent, not reliable for demo)
- Spatial audio
- Multi-language support beyond what Whisper already handles
- Persistent conversation history
- Teammate's left-side phone UI changes (handled separately)
