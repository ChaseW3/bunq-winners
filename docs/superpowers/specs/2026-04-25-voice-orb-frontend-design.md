# Voice Orb Frontend — Design

## Goal

Replace the current tap-to-toggle frontend with a hold-to-talk voice assistant interface featuring a beautiful animated particle orb in bunq brand colors. A single press-and-hold gesture drives all interaction: starting a recording from idle, interrupting an in-flight request, or interrupting the assistant while it is "speaking."

## Scope

- Single-file rewrite of `frontend/index.html`. No backend changes.
- The existing transcript and tool-calls panel at the bottom of the screen is preserved exactly as-is for the demo.
- "Speaking" is a **visual-only** state — the backend returns text, and the speaking animation runs for a duration proportional to the reply length. There is no audio playback in this iteration.

## Brand colors

- Cyan: `#00C8FF`
- Magenta: `#FF3D8B`
- Deep blue (ambient/glow): `#1A2B5C`
- Background: `#0A0A0A` (kept from current frontend)

## State machine

Four states:

| State | Entry trigger | Visual behavior |
|---|---|---|
| `idle` | initial load; speaking timeout ends; user interrupts and releases without speaking | slow breathing pulse, subtle hue drift |
| `listening` | `pointerdown` on tap-area | particles scatter outward reactive to mic volume; gradient warms toward magenta on louder input |
| `thinking` | `pointerup` while listening, fetch in flight | particles swirl/orbit faster, brighter glow |
| `speaking` | fetch returns successfully | rhythmic pulse for ~50 ms/char of `reply_text`, capped at 8 s |

### Transitions on `pointerdown`

A single rule covers all "interrupt" semantics:

- `idle` → start recording → `listening`
- `thinking` → abort the in-flight fetch → start recording → `listening`
- `speaking` → stop the speaking animation → start recording → `listening`
- `listening` → ignored (already recording)

### Transitions on `pointerup` / `pointercancel` / `pointerleave`

- Only meaningful in `listening`. Stop the `MediaRecorder`, send audio to `/voice`, transition to `thinking`.
- A press shorter than **200 ms** is treated as an accidental tap: discard the audio, return to `idle`.

## Particle system

- HTML `<canvas>` 2D, sized to `devicePixelRatio`, sits behind a thin centered orb container.
- ~100 particles, each with `(x, y, z)` initialized on a unit sphere plus a phase offset.
- Each frame:
  1. Rotate the cloud slowly around the Y axis (rate depends on state).
  2. Project to 2D with simple perspective (`scale = focal / (focal + z)`).
  3. Sort by z so back-facing particles render smaller and dimmer.
  4. Color each particle by lerping between cyan and magenta based on z, with an ambient deep-blue bloom underneath.
- Per-state modulation of particle radius `r`:
  - `idle`: `r = 1.0 + 0.04 · sin(t + phase)`
  - `listening`: `r += micLevel · 0.6` (smoothed); small outward jitter
  - `thinking`: rotation ×3, `r = 1.0 + 0.08 · sin(t · 3 + phase)`, saturation boosted
  - `speaking`: synchronous pulse `r = 1.0 + 0.18 · sin(t · 2π · 1.6)`

## Mic level

- Reuse the `getUserMedia` stream → `AudioContext.createMediaStreamSource(stream)` → `AnalyserNode` with `fftSize = 256`.
- Each animation frame: `getByteFrequencyData`, average the bins, normalize to `[0, 1]`, then exponential smoothing (`α = 0.2`).
- Stream and AudioContext are torn down on transition out of `listening`.

## Interrupt / abort

- Each `/voice` fetch uses an `AbortController`. On `pointerdown` while in `thinking`, call `controller.abort()` before starting a new recording. The aborted fetch's response handler is a no-op.
- `speaking` is implemented as a `setTimeout` + a `speaking` flag in the animation loop. `pointerdown` clears both.

## Pointer handling

- Use Pointer Events (`pointerdown`, `pointerup`, `pointercancel`, `pointerleave`) — one code path for mouse, touch, and pen.
- `setPointerCapture` on `pointerdown` so dragging off the orb still releases cleanly via `pointerup`.
- `event.preventDefault()` to suppress synthetic clicks and iOS callout/selection.
- The whole top region (above the transcript panel) is the press target — not just the orb — so the user does not need to aim.

## Layout

- Body: column flex, dark background.
- Top region (`flex: 1`): canvas absolutely positioned, orb container centered, hint text below the orb.
- Hint text per state: "Hold to speak" (idle) / "Listening…" (listening) / "Thinking…" (thinking) / "Tap to interrupt" (speaking).
- Bottom region: existing `#output` panel with `#transcript` — markup and styles unchanged.

## Out of scope

- Real text-to-speech audio playback.
- Multi-turn UI (only the latest exchange is shown, matching current behavior).
- WebGL / 3D engine. Plain canvas 2D is sufficient for ~100 particles at 60 fps.
- Mobile-specific gestures beyond press-and-hold.

## Success criteria

- Press-and-hold anywhere in the top region records audio; release sends it.
- The orb visibly reacts to mic volume during recording.
- Pressing again during `thinking` cancels the in-flight request and starts a new recording.
- Pressing again during `speaking` stops the speaking animation and starts a new recording.
- Particle animation runs smoothly (no jank) on a modern laptop browser.
- Transcript panel renders user text, reply text, and tool calls identically to the current frontend.
