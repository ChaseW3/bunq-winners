# Lynn Accessibility Voice Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the bunq voice agent into "Lynn," an accessibility-focused assistant with a split-screen demo showing a phone UI (left) and real-time accessibility event log (right).

**Architecture:** The backend system prompt is overhauled for blind-friendly speech patterns. The orchestrator generates `accessibility_events` metadata alongside the LLM reply. The frontend (`demo-transition.html`) is extended with voice agent wiring (ported from `index.html`), an earcon system, auto-greeting, accessibility log panel, and voice-only confirmation. `index.html` is deleted after migration.

**Tech Stack:** Python/FastAPI backend, vanilla JS/HTML frontend, Web Audio API for earcons, ElevenLabs TTS, Anthropic Claude for LLM.

---

### Task 1: System Prompt Overhaul — Lynn Persona

**Files:**
- Modify: `backend/orchestrator/prompts.py`
- Modify: `backend/tests/test_orchestrator_llm.py`

- [ ] **Step 1: Update the test for system prompt content**

The existing test `test_system_prompt_includes_reasoning_guidance` checks for "Summarize" and "confirm_draft_payment". Update it to also check for Lynn-specific rules:

```python
def test_system_prompt_includes_lynn_accessibility_rules(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_text("ok")], "stop_reason": "end_turn"},
    ])
    run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="hi")
    system_sent = llm.calls[0]["system"]
    assert "Lynn" in system_sent
    assert "NATO" in system_sent or "phonetic" in system_sent.lower()
    assert "confirm_draft_payment" in system_sent
    assert "as shown above" not in system_sent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_orchestrator_llm.py::test_system_prompt_includes_lynn_accessibility_rules -v`
Expected: FAIL — "Lynn" not in system prompt

- [ ] **Step 3: Rewrite the STATIC prompt in `prompts.py`**

Replace the entire `STATIC` string in `backend/orchestrator/prompts.py`:

```python
STATIC = (
    # Persona
    "You are Lynn, bunq's accessibility voice assistant. "
    "You help blind and visually impaired users manage their money through voice alone. "
    "Be direct and warm — never cold, never chatty. "
    "Skip filler phrases like 'Sure!', 'Great!', or 'Of course!'. "
    "Keep every spoken reply to one or two short sentences.\n\n"

    # Accessibility: no visual references
    "Never reference anything visual. Never say 'as shown above', 'you can see', "
    "'the screen shows', 'look at', 'below', or 'on the left/right'. "
    "The user cannot see the screen. Every piece of information must be spoken.\n\n"

    # Accessibility: amounts and IBANs
    "Speak all amounts as full words: 'twenty euros and fifty cents', never '€20.50' or '20 EUR'. "
    "When reading an IBAN, use the NATO phonetic alphabet for letters and speak each digit individually: "
    "'November Lima four two Bravo Uniform November Quebec zero one two three four five six seven eight nine'. "
    "Always read back the full IBAN when confirming a payment.\n\n"

    # Accessibility: lists and navigation
    "When listing items (transactions, accounts, cards), announce the count first: "
    "'You have three recent transactions.' Then read one item at a time. "
    "After each item, offer to continue: 'Want to hear the next one?' "
    "Never dump a full list at once.\n\n"

    # Accessibility: readback before action
    "Before executing any payment or consequential action, read back all details: "
    "recipient name, amount in words, full IBAN spelled phonetically, and description. "
    "Then say: 'Say confirm to proceed, or cancel to stop.' "
    "Wait for an explicit spoken confirmation.\n\n"

    # Ambiguity & missing information
    "Never invent, guess, or assume information. "
    "If a required detail is missing — recipient, amount, account, or date — ask for it explicitly before calling any tool. "
    "Ask one question at a time. "
    "Do not proceed until you have every required field confirmed by the user.\n\n"

    # Reasoning over data
    "When the user asks an open question about their finances "
    "('what did I spend', 'how's my savings', 'what's coming up', 'any unusual activity'), "
    "call the relevant read tool(s), then synthesize a one- or two-sentence spoken reply. "
    "Summarize — group by counterparty (or by description when self-transfers obscure the merchant), "
    "call out totals and the largest or most recent items. "
    "Do not read back raw lists. Prefer one tool call per turn; combine tools only when the question "
    "genuinely needs multiple data sources (e.g. balance plus upcoming scheduled payments). "
    "If the user asks for a specific value (a balance, one payment, one contact), answer it directly "
    "without extra summarization.\n\n"
    "For judgment or reasoning questions — 'can I afford', 'where is my money going', "
    "'anything unusual', 'will I make it to payday', 'am I saving enough', 'how am I doing' — "
    "call financial_context with the right focus instead of chaining multiple tools. "
    "It returns a pre-computed snapshot. Give a clear judgment first (yes/no/caution), "
    "then the one or two numbers that justify it. Don't read the whole snapshot back.\n\n"

    # Conversation style
    "Do not repeat information you have already stated in this conversation unless the user asks you to. "
    "If you just read out a draft payment's details, do not re-read them in your next reply. "
    "Avoid summarising what you are about to do — just do it and report the outcome briefly.\n\n"

    # Payments & safety
    "Before moving any money, always create a draft payment first. "
    "Read the amount and recipient clearly once. "
    "Only call confirm_draft_payment after the user has given an unambiguous yes ('yes', 'confirm', 'do it', 'go ahead'). "
    "If they say anything negative or uncertain, call cancel_pending instead. "
    "Never send money directly without going through the draft flow.\n\n"

    # Errors & tool failures
    "If a tool call fails, retry it once silently. "
    "If it fails a second time, stop and tell the user: 'Something went wrong — please try again in a moment.' "
    "Do not speculate about the cause. Do not retry a third time."
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_orchestrator_llm.py -v`
Expected: ALL PASS (existing tests + new Lynn test)

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/prompts.py backend/tests/test_orchestrator_llm.py
git commit -m "feat: overhaul system prompt for Lynn accessibility persona"
```

---

### Task 2: Accessibility Events in Backend Response

**Files:**
- Modify: `backend/orchestrator/llm.py`
- Modify: `backend/tests/test_orchestrator_llm.py`

- [ ] **Step 1: Write tests for accessibility event generation**

Add to `backend/tests/test_orchestrator_llm.py`:

```python
def test_accessibility_events_includes_full_amount_when_amount_in_reply(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_text("Your balance is one thousand two hundred forty-seven euros.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="what's my balance?")
    events = out["accessibility_events"]
    types = [e["type"] for e in events]
    assert "SPEECH" in types


def test_accessibility_events_includes_voice_confirm_on_draft(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "create_draft_payment", {
            "iban": "NL00BUNQ0000000002", "amount": "20.00",
            "description": "pizza", "counterparty_name": "Finn Bunq",
        })], "stop_reason": "tool_use"},
        {"content": [_text("Sending twenty euros to Finn Bunq. Say confirm to proceed, or cancel to stop.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="send 20 to Finn for pizza")
    events = out["accessibility_events"]
    event_types = [(e["type"], e["event"]) for e in events]
    assert ("ACTION", "voice-confirm") in event_types
    assert ("SPEECH", "readback") in event_types


def test_accessibility_events_includes_error_on_tool_failure(session):
    store, sid = session

    class BoomClient(FakeBunqClient):
        def list_savings_accounts(self):
            raise RuntimeError("api down")

    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "list_savings_accounts", {})], "stop_reason": "tool_use"},
        {"content": [_text("Sorry — I couldn't reach savings right now.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, BoomClient(), store, sid, user_text="savings?")
    events = out["accessibility_events"]
    types = [e["type"] for e in events]
    assert "ERROR" in types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_orchestrator_llm.py::test_accessibility_events_includes_full_amount_when_amount_in_reply backend/tests/test_orchestrator_llm.py::test_accessibility_events_includes_voice_confirm_on_draft backend/tests/test_orchestrator_llm.py::test_accessibility_events_includes_error_on_tool_failure -v`
Expected: FAIL — `accessibility_events` key missing from return dict

- [ ] **Step 3: Add `derive_accessibility_events` function to `llm.py`**

Add this function before `run_llm_turn` in `backend/orchestrator/llm.py`:

```python
import re

def derive_accessibility_events(
    reply: str,
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    has_error = any(tc["is_error"] for tc in tool_calls)
    if has_error:
        events.append({"type": "ERROR", "event": "tool-error", "detail": "Error communicated via voice — no silent failures"})

    tool_names = [tc["name"] for tc in tool_calls]
    has_draft = "create_draft_payment" in tool_names
    has_confirm = "confirm_draft_payment" in tool_names

    amount_words = bool(re.search(
        r'\b(one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|'
        r'eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|'
        r'eighty|ninety|hundred|thousand|million|euro|cent)\b',
        reply.lower()
    ))
    if amount_words:
        events.append({"type": "SPEECH", "event": "full-amount", "detail": "Amount spoken as words, not symbols or digits"})

    iban_phonetic = bool(re.search(
        r'\b(Alpha|Bravo|Charlie|Delta|Echo|Foxtrot|Golf|Hotel|India|'
        r'Juliet|Kilo|Lima|Mike|November|Oscar|Papa|Quebec|Romeo|'
        r'Sierra|Tango|Uniform|Victor|Whiskey|X-ray|Yankee|Zulu)\b',
        reply
    ))
    if iban_phonetic:
        events.append({"type": "SPEECH", "event": "iban-phonetic", "detail": "IBAN read with NATO phonetic alphabet"})

    if has_draft:
        events.append({"type": "SPEECH", "event": "readback", "detail": "Full payment details read back before action"})
        events.append({"type": "ACTION", "event": "voice-confirm", "detail": "Awaiting spoken 'confirm' — no screen interaction needed"})

    if has_confirm:
        events.append({"type": "ACTION", "event": "payment-confirmed", "detail": "Payment confirmed by voice command"})

    return events
```

- [ ] **Step 4: Update `run_llm_turn` to include accessibility events in return value**

Change the return statement at the end of `run_llm_turn` (the line `return {"reply": reply, "tool_calls": tool_calls}`):

```python
        a11y_events = derive_accessibility_events(reply, tool_calls)
        return {"reply": reply, "tool_calls": tool_calls, "accessibility_events": a11y_events}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_orchestrator_llm.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/orchestrator/llm.py backend/tests/test_orchestrator_llm.py
git commit -m "feat: derive accessibility_events from LLM reply and tool calls"
```

---

### Task 3: Update Backend Endpoints to Return Accessibility Events

**Files:**
- Modify: `scripts/serve_test.py`

- [ ] **Step 1: Update `/voice` endpoint to include accessibility_events**

In `scripts/serve_test.py`, update the return dict in the `voice` function (around line 89) to pass through the new field:

```python
        return {
            "user_text": user_text,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "accessibility_events": result.get("accessibility_events", []),
            "pending": pending,
        }
```

- [ ] **Step 2: Update `/text` endpoint to include accessibility_events**

In the `text` function (around line 108), same change:

```python
        return {
            "user_text": message,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "accessibility_events": result.get("accessibility_events", []),
            "pending": pending,
        }
```

- [ ] **Step 3: Update static file serving to serve `demo-transition.html` as the default**

Replace the static mount at the bottom of `scripts/serve_test.py`. The `StaticFiles` with `html=True` already serves `index.html` as the default. Since we're replacing `index.html` with `demo-transition.html`, we need a redirect. Add a route before the static mount:

```python
from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse("/demo-transition.html")

app.mount("/static", StaticFiles(directory="frontend"), name="static")
```

Wait — actually this won't work well with the existing `StaticFiles(html=True)` approach. Simpler: we'll rename `demo-transition.html` to `index.html` in Task 7 when we delete the old one. For now, keep both and access the new one at `/demo-transition.html`.

Revert this step — just do steps 1 and 2 for now.

- [ ] **Step 3 (revised): Verify server starts**

Run: `uv run python -c "from scripts.serve_test import app; print('OK')"`
(This just verifies the import doesn't crash — actual server test happens in Task 7)

- [ ] **Step 4: Commit**

```bash
git add scripts/serve_test.py
git commit -m "feat: pass accessibility_events through /voice and /text endpoints"
```

---

### Task 4: Earcon System (Web Audio API)

**Files:**
- Modify: `frontend/demo-transition.html`

- [ ] **Step 1: Add the earcon synthesis module as a `<script>` block**

Add this script block inside `<body>`, before the existing `<script>` tag in `frontend/demo-transition.html`:

```html
<script>
// ── Earcon System ──
const EarconSystem = (() => {
  let ctx = null;
  function getCtx() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    return ctx;
  }

  function play(name) {
    const ac = getCtx();
    const now = ac.currentTime;
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain);
    gain.connect(ac.destination);

    switch (name) {
      case 'greeting': {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523, now);        // C5
        osc.frequency.linearRampToValueAtTime(784, now + 0.3); // G5
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.linearRampToValueAtTime(0, now + 0.5);
        osc.start(now);
        osc.stop(now + 0.5);
        break;
      }
      case 'mic-on': {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, now); // A5
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.linearRampToValueAtTime(0, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
        break;
      }
      case 'mic-off': {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, now); // E5
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.linearRampToValueAtTime(0, now + 0.12);
        osc.start(now);
        osc.stop(now + 0.12);
        break;
      }
      case 'thinking': {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(440, now); // A4
        gain.gain.setValueAtTime(0.08, now);
        // Pulse: ramp up/down repeatedly over 4 seconds
        for (let i = 0; i < 8; i++) {
          const t = now + i * 0.5;
          gain.gain.linearRampToValueAtTime(0.08, t);
          gain.gain.linearRampToValueAtTime(0.02, t + 0.25);
        }
        gain.gain.linearRampToValueAtTime(0, now + 4);
        osc.start(now);
        osc.stop(now + 4);
        return osc; // Return so caller can stop early
      }
      case 'success': {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(659, now);        // E5
        osc.frequency.setValueAtTime(880, now + 0.15); // A5
        gain.gain.setValueAtTime(0.25, now);
        gain.gain.linearRampToValueAtTime(0, now + 0.45);
        osc.start(now);
        osc.stop(now + 0.45);
        break;
      }
      case 'error': {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(220, now); // A3
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.linearRampToValueAtTime(0, now + 0.4);
        osc.start(now);
        osc.stop(now + 0.4);
        break;
      }
    }
    return osc;
  }

  return { play, getCtx };
})();

let thinkingOsc = null;
function stopThinkingEarcon() {
  if (thinkingOsc) {
    try { thinkingOsc.stop(); } catch {}
    thinkingOsc = null;
  }
}
</script>
```

- [ ] **Step 2: Test earcons manually in browser**

Open `frontend/demo-transition.html` in a browser, open the console, and run:
```js
EarconSystem.play('greeting');
EarconSystem.play('mic-on');
EarconSystem.play('mic-off');
EarconSystem.play('success');
EarconSystem.play('error');
```
Verify each produces a distinct, pleasant sound.

- [ ] **Step 3: Commit**

```bash
git add frontend/demo-transition.html
git commit -m "feat: add Web Audio API earcon system with 6 sound cues"
```

---

### Task 5: Accessibility Log Panel (HTML + CSS + JS)

**Files:**
- Modify: `frontend/demo-transition.html`

- [ ] **Step 1: Add the log panel HTML**

In `frontend/demo-transition.html`, add the log panel element after the `.phone` div, inside `<body>`:

```html
<div class="a11y-log" id="a11yLog">
  <div class="a11y-log-header">Accessibility Events</div>
  <div class="a11y-log-entries" id="a11yEntries"></div>
</div>
```

- [ ] **Step 2: Add the log panel CSS**

Add these styles inside the existing `<style>` block:

```css
/* ── Accessibility Log Panel ── */
.a11y-log {
  position: fixed;
  top: 40px;
  right: 40px;
  bottom: 40px;
  width: 38vw;
  background: #0a0a0a;
  border: 1px solid #1f2937;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  opacity: 0;
  transform: translateX(40px);
  transition: opacity 0.6s ease 0.3s, transform 0.6s ease 0.3s;
  pointer-events: none;
  overflow: hidden;
  font-family: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace;
}

.a11y-log.visible {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.a11y-log-header {
  padding: 16px 20px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  border-bottom: 1px solid #1f2937;
  flex-shrink: 0;
}

.a11y-log-entries {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.a11y-entry {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  font-size: 12.5px;
  line-height: 1.5;
  animation: fadeInEntry 0.3s ease;
}

@keyframes fadeInEntry {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.a11y-tag {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  height: fit-content;
}

.a11y-tag.AUDIO   { color: #00C8FF; background: rgba(0,200,255,0.1); }
.a11y-tag.EARCON  { color: #FF3D8B; background: rgba(255,61,139,0.1); }
.a11y-tag.SPEECH  { color: #4ADE80; background: rgba(74,222,128,0.1); }
.a11y-tag.STATE   { color: #FACC15; background: rgba(250,204,21,0.1); }
.a11y-tag.ACTION  { color: #22C55E; background: rgba(34,197,94,0.1); }
.a11y-tag.ERROR   { color: #EF4444; background: rgba(239,68,68,0.1); }

.a11y-event {
  color: #9ca3af;
  font-weight: 600;
  flex-shrink: 0;
}

.a11y-detail {
  color: #6b7280;
}
```

- [ ] **Step 3: Add the log panel JS**

Add this in the earcon `<script>` block or a new one:

```html
<script>
const A11yLog = (() => {
  const entries = document.getElementById('a11yEntries');
  const panel = document.getElementById('a11yLog');

  function show() { panel.classList.add('visible'); }
  function hide() { panel.classList.remove('visible'); }

  function log(type, event, detail) {
    const entry = document.createElement('div');
    entry.className = 'a11y-entry';
    entry.innerHTML =
      `<span class="a11y-tag ${type}">${type}</span>` +
      `<span class="a11y-event">${escapeHtml(event)}</span>` +
      `<span class="a11y-detail">${escapeHtml(detail)}</span>`;
    entries.appendChild(entry);
    entries.scrollTop = entries.scrollHeight;
  }

  function logBackendEvents(events) {
    if (!events) return;
    for (const ev of events) {
      log(ev.type, ev.event, ev.detail);
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  return { show, hide, log, logBackendEvents };
})();
</script>
```

- [ ] **Step 4: Wire log panel visibility to the transition state**

Update the existing click handler script in `demo-transition.html`. Replace:

```javascript
const screen = document.getElementById('screen');
let state = 0;
screen.addEventListener('click', () => {
  state = (state + 1) % 3;
  screen.classList.toggle('blurred', state >= 1);
  screen.classList.toggle('active',  state >= 2);
});
```

With:

```javascript
const screen = document.getElementById('screen');
let state = 0;
let activated = false;
screen.addEventListener('click', () => {
  if (activated) return; // After activation, clicks go to voice agent
  state = (state + 1) % 3;
  screen.classList.toggle('blurred', state >= 1);
  screen.classList.toggle('active',  state >= 2);

  if (state === 2 && !activated) {
    activated = true;
    A11yLog.show();
    triggerGreeting();
  }
});
```

- [ ] **Step 5: Test in browser**

Open `frontend/demo-transition.html`. Click twice. Verify:
- Orb fades in (existing behavior)
- Log panel slides in from the right simultaneously
- Panel has dark background, "Accessibility Events" header

- [ ] **Step 6: Commit**

```bash
git add frontend/demo-transition.html
git commit -m "feat: add accessibility log panel with slide-in transition"
```

---

### Task 6: Auto-Greeting

**Files:**
- Modify: `frontend/demo-transition.html`

- [ ] **Step 1: Add greeting function and TTS config**

Add this to the voice agent script section in `demo-transition.html`:

```javascript
const BACKEND = 'http://localhost:8000';
const ELEVENLABS_VOICE_ID = 'gE0owC0H9C8SzfDyIUtB';
let elevenLabsApiKey = '';

fetch(`${BACKEND}/config`)
  .then(r => r.json())
  .then(cfg => { elevenLabsApiKey = cfg.elevenlabs_api_key; })
  .catch(() => {});

async function speakText(text) {
  if (!text || !elevenLabsApiKey) return;
  try {
    const resp = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}`,
      {
        method: 'POST',
        headers: { 'xi-api-key': elevenLabsApiKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          model_id: 'eleven_multilingual_v2',
          voice_settings: { stability: 0.5, similarity_boost: 0.75 }
        })
      }
    );
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    await audio.play();
    return audio;
  } catch (e) {
    console.warn('TTS error:', e);
  }
}

async function triggerGreeting() {
  EarconSystem.play('greeting');
  A11yLog.log('AUDIO', 'AUTO-GREET', "Lynn introduced herself — no visual context needed");
  A11yLog.log('EARCON', 'greeting', "Warm chime signals app is alive");

  // Small delay for earcon to finish
  await new Promise(r => setTimeout(r, 600));
  await speakText("Hi, I'm Lynn, your bunq accessibility assistant. What can I do for you today?");
}
```

- [ ] **Step 2: Test in browser**

Open `frontend/demo-transition.html`, click twice. Verify:
- Greeting earcon plays
- Log shows AUTO-GREET and greeting entries
- TTS speaks "Hi, I'm Lynn..." (if ElevenLabs key is configured)

- [ ] **Step 3: Commit**

```bash
git add frontend/demo-transition.html
git commit -m "feat: add auto-greeting with earcon and TTS on activation"
```

---

### Task 7: Wire Voice Agent to Demo Frontend

**Files:**
- Modify: `frontend/demo-transition.html`

This is the largest task — porting the voice interaction from `index.html`.

- [ ] **Step 1: Add voice agent state and mic recording**

Add this to the main script section, after the greeting code:

```javascript
// ── Voice Agent State ──
let appState = 'idle'; // idle | listening | thinking | speaking
let pressStartedAt = 0;
let recorder = null;
let micStream = null;
let audioCtx = null;
let analyser = null;
let micLevel = 0;
let chunks = [];
let abortCtrl = null;
let speakingTimer = null;
let ttsAudio = null;
const MIN_HOLD_MS = 200;

function setVoiceState(s) {
  appState = s;
  const orb = document.querySelector('.orb');
  const hint = document.querySelector('.hint');
  if (orb) {
    orb.classList.toggle('listening', s === 'listening');
    orb.classList.toggle('thinking',  s === 'thinking');
    orb.classList.toggle('speaking',  s === 'speaking');
  }
  if (hint) {
    hint.textContent = ({
      idle:      'Hold to speak',
      listening: 'Listening…',
      thinking:  'Thinking…',
      speaking:  'Speaking…',
    })[s] || 'Hold to speak';
  }
}

function startMicAnalyser(stream) {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const src = audioCtx.createMediaStreamSource(stream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  src.connect(analyser);
  const buf = new Uint8Array(analyser.frequencyBinCount);
  function tick() {
    if (!analyser) return;
    analyser.getByteFrequencyData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i];
    micLevel = micLevel * 0.8 + (sum / buf.length / 255) * 0.2;
    requestAnimationFrame(tick);
  }
  tick();
}

function teardownMic() {
  if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
  if (audioCtx) { try { audioCtx.close(); } catch {} audioCtx = null; }
  analyser = null;
  micLevel = 0;
}

function stopTts() {
  if (ttsAudio) { try { ttsAudio.pause(); } catch {} ttsAudio = null; }
}
```

- [ ] **Step 2: Add recording start/stop and send logic**

```javascript
async function startRecording() {
  try {
    chunks = [];
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(micStream);
    recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = onRecorderStop;
    recorder.start();
    startMicAnalyser(micStream);

    EarconSystem.play('mic-on');
    A11yLog.log('EARCON', 'mic-on', 'Audio cue confirms recording started');
    A11yLog.log('STATE', 'listening', 'Lynn is listening — user is speaking');
    setVoiceState('listening');
    pressStartedAt = performance.now();
  } catch (e) {
    A11yLog.log('ERROR', 'mic-denied', 'Microphone access denied');
    setVoiceState('idle');
  }
}

function endRecordingAndSend() {
  const heldFor = performance.now() - pressStartedAt;
  if (heldFor < MIN_HOLD_MS) {
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.onstop = null; recorder.stop(); } catch {}
    }
    recorder = null;
    teardownMic();
    setVoiceState('idle');
    return;
  }
  if (recorder && recorder.state !== 'inactive') {
    try { recorder.stop(); } catch {}
  }
  EarconSystem.play('mic-off');
  A11yLog.log('EARCON', 'mic-off', 'Audio confirms input captured');
  teardownMic();

  thinkingOsc = EarconSystem.play('thinking');
  A11yLog.log('STATE', 'thinking', 'Ambient tone plays while processing');
  setVoiceState('thinking');
}

function onRecorderStop() {
  if (appState !== 'thinking') return;
  sendAudio();
}

async function sendAudio() {
  const blob = new Blob(chunks, { type: 'audio/webm' });
  const form = new FormData();
  form.append('audio', blob, 'recording.webm');
  abortCtrl = new AbortController();
  try {
    const resp = await fetch(`${BACKEND}/voice`, {
      method: 'POST',
      body: form,
      signal: abortCtrl.signal,
    });
    const data = await resp.json();
    stopThinkingEarcon();
    if (appState !== 'thinking') return;

    // Log backend accessibility events
    A11yLog.logBackendEvents(data.accessibility_events);

    // Check for success/error earcons based on tool calls
    const hasError = data.tool_calls?.some(tc => tc.is_error);
    const hasConfirm = data.tool_calls?.some(tc => tc.name === 'confirm_draft_payment');
    if (hasError) {
      EarconSystem.play('error');
      A11yLog.log('EARCON', 'error', 'Audio signals something went wrong');
    } else if (hasConfirm) {
      EarconSystem.play('success');
      A11yLog.log('EARCON', 'success', 'Audio confirms payment completed');
    }

    // Speak the reply
    if (data.reply_text) {
      A11yLog.log('AUDIO', 'tts-playback', 'Lynn speaking response aloud');
      setVoiceState('speaking');
      ttsAudio = await speakText(data.reply_text);
      if (ttsAudio) {
        ttsAudio.onended = () => { setVoiceState('idle'); };
      } else {
        // Fallback: estimate speaking time
        const ms = Math.min(8000, Math.max(1200, data.reply_text.length * 50));
        setTimeout(() => { if (appState === 'speaking') setVoiceState('idle'); }, ms);
      }
    } else {
      setVoiceState('idle');
    }
  } catch (e) {
    stopThinkingEarcon();
    if (e.name === 'AbortError') return;
    EarconSystem.play('error');
    A11yLog.log('ERROR', 'network', 'Could not reach backend');
    setVoiceState('idle');
  } finally {
    abortCtrl = null;
  }
}

function interrupt() {
  if (abortCtrl) { try { abortCtrl.abort(); } catch {} abortCtrl = null; }
  stopTts();
  stopThinkingEarcon();
  clearTimeout(speakingTimer);
  if (recorder && recorder.state !== 'inactive') {
    try { recorder.onstop = null; recorder.stop(); } catch {}
  }
  recorder = null;
  teardownMic();
}
```

- [ ] **Step 3: Add pointer event handlers on the screen element**

Replace the existing click handler (the one we modified in Task 5) with this combined handler that manages both the transition and voice input:

```javascript
const screen = document.getElementById('screen');
let transitionState = 0;
let activated = false;

screen.addEventListener('pointerdown', async (e) => {
  e.preventDefault();
  try { screen.setPointerCapture(e.pointerId); } catch {}

  if (!activated) {
    // Transition animation
    transitionState = (transitionState + 1) % 3;
    screen.classList.toggle('blurred', transitionState >= 1);
    screen.classList.toggle('active', transitionState >= 2);

    if (transitionState === 2) {
      activated = true;
      A11yLog.show();
      triggerGreeting();
    }
    return;
  }

  // Voice agent interaction (after activation)
  if (appState === 'idle') {
    await startRecording();
  } else if (appState === 'thinking' || appState === 'speaking') {
    interrupt();
    await startRecording();
  }
});

function onRelease(e) {
  try { screen.releasePointerCapture(e.pointerId); } catch {}
  if (activated && appState === 'listening') endRecordingAndSend();
}
screen.addEventListener('pointerup', onRelease);
screen.addEventListener('pointercancel', onRelease);
```

- [ ] **Step 4: Update `speakText` to return the audio element and track it as `ttsAudio`**

The `speakText` function from Task 6 already returns the audio element. Update it to also set `ttsAudio`:

```javascript
async function speakText(text) {
  if (!text || !elevenLabsApiKey) return null;
  try {
    const resp = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}`,
      {
        method: 'POST',
        headers: { 'xi-api-key': elevenLabsApiKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          model_id: 'eleven_multilingual_v2',
          voice_settings: { stability: 0.5, similarity_boost: 0.75 }
        })
      }
    );
    if (!resp.ok) return null;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    if (ttsAudio) { try { ttsAudio.pause(); } catch {} }
    ttsAudio = new Audio(url);
    ttsAudio.onended = () => URL.revokeObjectURL(url);
    await ttsAudio.play();
    return ttsAudio;
  } catch (e) {
    console.warn('TTS error:', e);
    return null;
  }
}
```

- [ ] **Step 5: Test full voice flow in browser**

1. Start backend: `uv run python scripts/serve_test.py`
2. Open `http://localhost:8000/demo-transition.html`
3. Click twice to activate (orb + log panel appear, greeting plays)
4. Hold on the phone screen, speak "What's my balance?", release
5. Verify: mic-on earcon → listening state → mic-off earcon → thinking tone → response spoken → accessibility events in log panel

- [ ] **Step 6: Commit**

```bash
git add frontend/demo-transition.html
git commit -m "feat: wire full voice agent into demo-transition.html"
```

---

### Task 8: Replace `index.html` with `demo-transition.html`

**Files:**
- Delete: `frontend/index.html`
- Rename: `frontend/demo-transition.html` → stays as-is (served via static files)
- Modify: `scripts/serve_test.py`

- [ ] **Step 1: Update serve_test.py to route `/` to the demo page**

In `scripts/serve_test.py`, replace the static mount line:

```python
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
```

With:

```python
from starlette.responses import FileResponse

@app.get("/")
async def root():
    return FileResponse("frontend/demo-transition.html")

app.mount("/frontend", StaticFiles(directory="frontend"), name="static")
```

This serves `demo-transition.html` at `/` and keeps other frontend files (like the background image) accessible.

Wait — the background image is referenced as `../picture/Frontend.jpeg`. Let's check:

The `demo-transition.html` references `url('../picture/Frontend.jpeg')` which is relative to the HTML file's location. When served from FastAPI at `/`, the relative path breaks. We need to fix the image path in the CSS to be absolute: `url('/picture/Frontend.jpeg')` and mount the picture directory.

Actually, `StaticFiles(directory="frontend")` at `/frontend` means the HTML at `/` would reference `/frontend/../picture/Frontend.jpeg` which is messy. Simpler approach: mount at root with html=False, and add an explicit `/` route:

```python
from starlette.responses import FileResponse

@app.get("/")
async def root():
    return FileResponse("frontend/demo-transition.html")

app.mount("/picture", StaticFiles(directory="picture"), name="picture")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend-static")
```

And update the CSS background-image in `demo-transition.html` from `url('../picture/Frontend.jpeg')` to `url('/picture/Frontend.jpeg')`.

- [ ] **Step 2: Fix the background image path in `demo-transition.html`**

Replace in the `.bg-screenshot` CSS rule:

```css
background-image: url('../picture/Frontend.jpeg');
```

With:

```css
background-image: url('/picture/Frontend.jpeg');
```

- [ ] **Step 3: Delete `index.html`**

```bash
git rm frontend/index.html
```

- [ ] **Step 4: Test the server**

Run: `uv run python scripts/serve_test.py`
Open: `http://localhost:8000`
Verify: The demo-transition page loads with background image, click-through works, voice agent works.

- [ ] **Step 5: Commit**

```bash
git add scripts/serve_test.py frontend/demo-transition.html
git commit -m "feat: replace index.html with demo-transition.html as main frontend"
```

---

### Task 9: Export Earcons to MP3 Files

**Files:**
- Create: `frontend/audio/greeting.mp3`
- Create: `frontend/audio/mic-on.mp3`
- Create: `frontend/audio/mic-off.mp3`
- Create: `frontend/audio/thinking.mp3`
- Create: `frontend/audio/success.mp3`
- Create: `frontend/audio/error.mp3`
- Modify: `frontend/demo-transition.html`

- [ ] **Step 1: Create a Node.js script to render earcons to WAV, then convert to MP3**

This step is manual / deferred. After tuning the Web Audio API earcons in Task 4, use the OfflineAudioContext API or a tool like `ffmpeg` to capture the output:

Create `scripts/export_earcons.html` — a standalone page that renders each earcon to an OfflineAudioContext and offers download links:

```html
<!DOCTYPE html>
<html>
<head><title>Export Earcons</title></head>
<body>
<h1>Earcon Exporter</h1>
<button id="exportAll">Export All</button>
<div id="links"></div>
<script>
const earcons = {
  greeting: (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(523, now);
    osc.frequency.linearRampToValueAtTime(784, now + 0.3);
    gain.gain.setValueAtTime(0.3, now);
    gain.gain.linearRampToValueAtTime(0, now + 0.5);
    osc.start(now); osc.stop(now + 0.5);
    return 0.5;
  },
  'mic-on': (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, now);
    gain.gain.setValueAtTime(0.2, now);
    gain.gain.linearRampToValueAtTime(0, now + 0.15);
    osc.start(now); osc.stop(now + 0.15);
    return 0.2;
  },
  'mic-off': (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(660, now);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.linearRampToValueAtTime(0, now + 0.12);
    osc.start(now); osc.stop(now + 0.12);
    return 0.2;
  },
  thinking: (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(440, now);
    gain.gain.setValueAtTime(0.08, now);
    for (let i = 0; i < 8; i++) {
      const t = now + i * 0.5;
      gain.gain.linearRampToValueAtTime(0.08, t);
      gain.gain.linearRampToValueAtTime(0.02, t + 0.25);
    }
    gain.gain.linearRampToValueAtTime(0, now + 4);
    osc.start(now); osc.stop(now + 4);
    return 4;
  },
  success: (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(659, now);
    osc.frequency.setValueAtTime(880, now + 0.15);
    gain.gain.setValueAtTime(0.25, now);
    gain.gain.linearRampToValueAtTime(0, now + 0.45);
    osc.start(now); osc.stop(now + 0.45);
    return 0.5;
  },
  error: (ac, now) => {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(220, now);
    gain.gain.setValueAtTime(0.2, now);
    gain.gain.linearRampToValueAtTime(0, now + 0.4);
    osc.start(now); osc.stop(now + 0.4);
    return 0.5;
  },
};

document.getElementById('exportAll').onclick = async () => {
  const links = document.getElementById('links');
  links.innerHTML = '';
  for (const [name, fn] of Object.entries(earcons)) {
    const duration = fn(new OfflineAudioContext(1, 1, 44100), 0);
    const oc = new OfflineAudioContext(1, Math.ceil(44100 * (duration + 0.1)), 44100);
    fn(oc, 0);
    const buffer = await oc.startRendering();
    const wav = audioBufferToWav(buffer);
    const blob = new Blob([wav], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${name}.wav`; a.textContent = `Download ${name}.wav`;
    links.appendChild(a);
    links.appendChild(document.createElement('br'));
  }
};

function audioBufferToWav(buffer) {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;
  const data = buffer.getChannelData(0);
  const dataLength = data.length * (bitDepth / 8);
  const headerLength = 44;
  const totalLength = headerLength + dataLength;
  const ab = new ArrayBuffer(totalLength);
  const view = new DataView(ab);
  let offset = 0;
  function writeString(s) { for (let i = 0; i < s.length; i++) view.setUint8(offset++, s.charCodeAt(i)); }
  function writeUint32(v) { view.setUint32(offset, v, true); offset += 4; }
  function writeUint16(v) { view.setUint16(offset, v, true); offset += 2; }
  writeString('RIFF');
  writeUint32(totalLength - 8);
  writeString('WAVE');
  writeString('fmt ');
  writeUint32(16);
  writeUint16(format);
  writeUint16(numChannels);
  writeUint32(sampleRate);
  writeUint32(sampleRate * numChannels * (bitDepth / 8));
  writeUint16(numChannels * (bitDepth / 8));
  writeUint16(bitDepth);
  writeString('data');
  writeUint32(dataLength);
  for (let i = 0; i < data.length; i++) {
    const sample = Math.max(-1, Math.min(1, data[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
    offset += 2;
  }
  return ab;
}
</script>
</body>
</html>
```

- [ ] **Step 2: Export and convert**

1. Open `scripts/export_earcons.html` in a browser
2. Click "Export All"
3. Download all 6 WAV files
4. Convert to MP3 using ffmpeg: `for f in *.wav; do ffmpeg -i "$f" -b:a 128k "${f%.wav}.mp3"; done`
5. Place in `frontend/audio/`

- [ ] **Step 3: Update EarconSystem to use audio files**

Replace the `EarconSystem` in `demo-transition.html`:

```javascript
const EarconSystem = (() => {
  const sounds = {};
  const names = ['greeting', 'mic-on', 'mic-off', 'thinking', 'success', 'error'];
  for (const name of names) {
    const audio = new Audio(`/frontend/audio/${name}.mp3`);
    audio.preload = 'auto';
    sounds[name] = audio;
  }

  function play(name) {
    const audio = sounds[name];
    if (!audio) return null;
    audio.currentTime = 0;
    audio.play().catch(() => {});
    return audio;
  }

  return { play };
})();
```

Update `stopThinkingEarcon` to pause the audio element:

```javascript
let thinkingAudio = null;
function stopThinkingEarcon() {
  if (thinkingAudio) {
    try { thinkingAudio.pause(); thinkingAudio.currentTime = 0; } catch {}
    thinkingAudio = null;
  }
}
```

And where `thinkingOsc = EarconSystem.play('thinking')` is used, change to `thinkingAudio = EarconSystem.play('thinking')`.

- [ ] **Step 4: Test in browser**

Open `http://localhost:8000`, activate, verify all earcons play from MP3 files.

- [ ] **Step 5: Commit**

```bash
git add frontend/audio/ scripts/export_earcons.html frontend/demo-transition.html
git commit -m "feat: export earcons to MP3 files for cross-browser consistency"
```

---

## Task Dependency Order

```
Task 1 (system prompt)     ─── no deps ───┐
Task 2 (accessibility events) ─ needs T1 ──┤
Task 3 (endpoint updates)  ─── needs T2 ──┤
Task 4 (earcon system)     ─── no deps ───┤── all feed into T7
Task 5 (log panel)         ─── no deps ───┤
Task 6 (auto-greeting)     ─── needs T4,T5┤
Task 7 (voice agent wiring)── needs T3-T6 ─┤
Task 8 (replace index.html)── needs T7 ────┘
Task 9 (export earcons)    ── needs T4, can be done any time after T7
```

**Parallelizable:** Tasks 1, 4, 5 can run in parallel. Tasks 2 depends on 1. Task 3 depends on 2. Task 6 depends on 4+5. Task 7 depends on 3+6. Task 8 depends on 7. Task 9 is independent after Task 4.

Plan complete and saved to `docs/superpowers/plans/2026-04-25-lynn-accessibility.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?