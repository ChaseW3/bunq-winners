# bunq Voice — Hackathon Plan

A voice-first, multi-modal reimagining of the bunq app, designed for blind and low-vision users. Built on the public bunq API.

Working name: **bunq Voice** (alternatives: Hey bunq, bunq Listen, bunq Echo)

---

## 1. The problem we're solving

The bunq app is heavily visual: dense tiles, account switchers, categorized feeds, scannable amounts. Screen readers technically work, but reading a transaction list linearly is exhausting — users drown in raw data before they reach meaning. A truly accessible version is not "add TTS to the existing UI." It's a fundamentally different interaction model built around **intent, summarization, and confirmation**.

Because the entire bunq app runs on the public API (400+ endpoints, real-time, webhooks), the full functionality can be rebuilt over a different modality.

---

## 2. Why this is multi-modal (not just voice)

"Blind people need voice" is too narrow. Many blind users have residual vision; all of them have cameras, hands, and physical context. The multi-modal inputs that matter:

| Modality | Role |
|---|---|
| **Voice input** | Primary channel — natural language requests |
| **Camera input** | Point at a paper invoice, receipt, IBAN on a letter, bank card, QR code. AI reads it aloud and offers to act |
| **Audio cues (earcons)** | Non-speech sounds for confirmation, error, balance direction — faster than speech |
| **Haptics** | Distinct vibration patterns: confirmed action, error, listening state |
| **Screen reader-native output** | Clean semantic text so VoiceOver/TalkBack works cleanly when the user wants to touch-explore |

The **camera** piece is the multi-modal hook judges will remember: "Blind person points phone at a paper bill, hears it read, says 'pay it', bank confirms via voice."

---

## 3. Feature tiers

Build in priority order. Tier 1 must work on stage. Tier 2 and 3 elevate the story.

### Tier 1 — Must work in the demo

- **Balance query** — "What's my balance?" / "How much in my savings account?"
- **Transaction summary** — "Read my last five transactions" → summarized, not raw ("You spent €43 at three grocery stores this week, biggest was Albert Heijn at €22")
- **Send money** — "Send €20 to Michelle" → voice repeat-back ("Sending 20 euros to Michelle Weng. Say yes to confirm.") → biometric gate → submit
- **Scan-to-pay** — camera → vision model → extract payee IBAN + amount → draft payment → voice confirm

### Tier 2 — Shows off the AI

- **Spending insights on demand** — "Where did my money go this month?" → LLM reasons over transaction history
- **Proactive notifications** — incoming payment webhook → spoken push ("You just received €500 from Dad, note: rent")
- **Card controls by voice** — "Block my physical card" / "Turn on contactless"
- **Request money** — "Ask Michelle for 50 euros for groceries" → creates RequestInquiry

### Tier 3 — Stretch / vision

- **Ambient mode** — phone in pocket, haptic tap on incoming payment, shake to hear what it was
- **Receipt capture** — snap a receipt, auto-categorize, attach to the matching transaction as a note
- **Weekly financial briefing** — scheduled voice summary, news-bulletin style
- **Conversational budgeting** — "Can I afford dinner out tonight?" → model considers balance + scheduled payments + recent spend rate

---

## 4. Architecture

### High-level pipeline

```
[Mic] → Wake word / push-to-talk
      → Speech-to-text
      → Intent router (LLM with tool-calling)
      → bunq API (OAuth)
      → Response composer (LLM shapes a spoken reply)
      → TTS
      → Earcon + haptic

[Camera] → Vision model (receipts, bills, IBANs, cards, QR codes)
         → Intent router (same downstream path)

[Webhooks] → Push notification → spoken briefing
```

### Stack choices

| Layer | Choice | Why |
|---|---|---|
| Mobile app | React Native or Flutter | Fastest path to iOS + Android; native accessibility APIs exposed |
| STT | Whisper (via OpenAI API) or platform STT (iOS Speech / Android SpeechRecognizer) | Platform STT is free + lower latency; Whisper is more accurate for accented/noisy input |
| LLM brain | Claude Sonnet / GPT-4o with tool calling | Tool calling is the whole game here |
| Vision | Same model — GPT-4o, Claude, or Gemini multimodal | One model handles voice intents and image understanding |
| TTS | Platform TTS (familiar voice, fast) + ElevenLabs for demo polish | Familiarity matters for blind users; demo needs a *good* voice |
| Backend | Node/Python Express layer between mobile and bunq | Handles bunq API context, signing, webhook endpoints |
| bunq SDK | Python or Java official SDK | Handles installation/session/signing boilerplate |

### Two critical design decisions

**LLM with tool-calling as the brain, not rule-based intent parsing.**
"Send twenty euros to my brother for pizza" and "Pay Jan back the pizza money, twenty bucks" must both work. Exposing bunq endpoints as tools (`getBalance`, `listPayments`, `createDraftPayment`, `listMonetaryAccounts`, `createRequestInquiry`, etc.) lets the LLM handle this naturally.

**Draft payments, never direct payments, in the demo.**
bunq supports a draft-payment concept: payment created but requires confirmation. Perfect for voice — a misheard "fifty" vs "fifteen" cannot move real money. Flow: voice echoes amount → user confirms → draft becomes payment. This is a genuine accessibility win, not just a safety patch.

---

## 5. Intent → bunq endpoint mapping

Rough mapping for Tier 1 & 2 intents. Final endpoint names to be confirmed against live docs during build.

| User says | Tool called | bunq endpoint |
|---|---|---|
| "What's my balance?" | `getBalance` | `GET /user/{userID}/monetary-account` |
| "Read my last transactions" | `listPayments` | `GET /user/{userID}/monetary-account/{id}/payment` |
| "Send €X to [name]" | `createDraftPayment` | `POST /user/{userID}/monetary-account/{id}/draft-payment` |
| "Confirm" | `confirmDraftPayment` | `PUT /user/{userID}/monetary-account/{id}/draft-payment/{id}` |
| "Ask [name] for €X" | `createRequestInquiry` | `POST /user/{userID}/monetary-account/{id}/request-inquiry` |
| "Block my card" | `updateCard` | `PUT /user/{userID}/card/{id}` |
| "Where did my money go?" | `listPayments` + LLM summarization | `GET` payments, then reason over results |
| Incoming webhook | — | Webhook endpoint receives event, pushes to device |

---

## 6. The multi-modal camera flow — end-to-end

This is the demo centerpiece. Full pipeline:

1. User says "scan this bill" or triple-taps screen
2. Camera opens with audio cue ("Camera on")
3. User holds phone over paper; app auto-captures when stable (uses motion sensors) or on tap
4. Image sent to vision model with a structured prompt: *"Extract from this invoice: creditor name, IBAN, amount, due date, reference/description. Return JSON."*
5. Result spoken: "This is an invoice from KPN for 47 euros 82, due November 15, reference 12345. Want me to schedule the payment?"
6. User says "yes" → draft payment created → biometric confirm → submitted
7. Earcon + haptic confirm success

Edge cases to handle:
- Blurry image → "I couldn't read that clearly. Try holding the phone 20cm above the paper."
- Ambiguous amount → read all candidates and ask
- No IBAN found → suggest alternate: "I see an amount but no IBAN. Should I search your contacts for the payee?"

---

## 7. Sharp edges — must address before demo

| Problem | Approach |
|---|---|
| **Auth on a voice interface** — can't say PIN out loud in public | Biometrics (Face/Touch ID) as confirm gate; device-bound trust after initial login (bunq's API context is already device-bound) |
| **Shoulder-surfing / audio privacy** | "Private mode" — sensitive info (amounts, balances) only plays through connected audio, not speaker. Earbud detection required for full disclosure |
| **STT mishears names** | Fuzzy-match against contacts list; if >1 match, spoken disambiguation ("I found two: Jan Bakker and Jen Hendriks. Which one?") |
| **Latency** — voice feels broken above ~1.5s | Stream LLM output into TTS; don't wait for full reply. Show intermediate earcons ("thinking" sound) |
| **Misheard amounts** | Always use draft payments; always repeat back amount before biometric confirm |
| **Accent / non-English input** | bunq is Dutch-first — Whisper handles Dutch well; test NL + EN end-to-end |

---

## 8. Demo script — 3 minutes

Target: one live flow that touches voice, vision, and proactive notifications.

**0:00–0:20 — Setup**
Stage: "Meet Sarah. She's blind. She's been using bunq for three years. Here's what her banking looks like today." [brief — current app VoiceOver reading a transaction list]

**0:20–0:45 — Voice balance + transactions**
"Hey bunq, what's my balance?" → "You have 1,247 euros in your main account, and 3,400 in savings."
"What did I spend this week?" → "About 180 euros. Mostly groceries — Albert Heijn three times, total 65 euros. And a 40 euro Uber on Tuesday."

**0:45–1:30 — Scan a bill**
Hold up a paper KPN invoice.
"Hey bunq, scan this."
[camera shutter earcon, brief pause]
"This is an invoice from KPN for 47 euros 82, due November 15. Want me to pay it?"
"Yes."
"Paying 47 euros 82 to KPN. Confirm with Face ID."
[confirm]
[success chime + haptic]
"Done. New balance: 1,199 euros."

**1:30–2:00 — Send money to contact**
"Send 20 euros to Michelle for dinner."
"Sending 20 euros to Michelle Weng, note: dinner. Say yes to confirm."
"Yes."
[biometric, chime]

**2:00–2:30 — Proactive notification**
Pre-trigger a webhook from a teammate's phone.
[haptic + discreet chime]
"You just received 500 euros from Dad, note: rent money."

**2:30–3:00 — Close**
"Everything Sarah just did is in the existing bunq app. We just made it reachable without looking at the screen. Built on the public bunq API, multi-modal AI on top."

---

## 9. Build timeline (rough)

Assumes 2-3 developers, ~48-hour hackathon.

| Hours | Milestone |
|---|---|
| 0–4 | Sandbox API key, OAuth flow, basic session creation, SDK installed. First successful `getBalance` call |
| 4–10 | Mobile app shell with push-to-talk, STT in, TTS out, LLM tool-calling wired to 3 bunq tools (balance, list payments, draft payment) |
| 10–18 | Voice flows for Tier 1 — send money, confirm, biometric gate, contact fuzzy match |
| 18–26 | Camera + vision model for scan-to-pay. OCR pipeline, JSON extraction, confirmation flow |
| 26–34 | Webhook receiver + push notification with spoken announcement. Earcons + haptics layer |
| 34–42 | Tier 2 polish — insights query, card controls, request money |
| 42–46 | Demo rehearsal, failure-mode handling, edge-case scripts |
| 46–48 | Slides, video backup of live demo in case Wi-Fi fails on stage |

---

## 10. Open questions / decisions to make

- **OAuth vs personal API key for the demo?** OAuth is the proper story; personal API key is faster to stand up. Recommendation: personal key for speed, mention OAuth in pitch.
- **Which platform first — iOS or Android?** iOS has better TTS and VoiceOver integration; Android has better STT latency on-device. Recommendation: pick whichever the team already has devices for.
- **Do we self-host Whisper or use platform STT?** Platform STT for Tier 1 (free, fast). Whisper as upgrade if time allows.
- **Wake word or push-to-talk?** Push-to-talk (button) for the demo — more reliable, no false triggers on stage. Wake word as Tier 3.
- **Which LLM?** Needs real tool-calling + vision. Claude Sonnet or GPT-4o both work. Pick based on who has API credits.

---

## 11. What makes this win

Judges see a lot of "AI banking assistant" hackathon projects. What makes this different:

1. **Real user group, not a gimmick.** Blind users are a genuinely underserved segment; the accessibility angle is defensible and compelling.
2. **Multi-modal where it matters.** Camera + voice isn't bolted on; it solves a real problem (reading paper bills is hard without sight).
3. **Built on bunq's actual strengths.** The programmable-bank thesis is bunq's whole identity. This demo *is* the pitch for their API.
4. **The draft-payment safety pattern is a feature, not a workaround.** Judges will notice the thoughtfulness.
5. **A clear, emotional demo.** Sarah paying a paper bill by pointing her phone at it is a moment people remember.
