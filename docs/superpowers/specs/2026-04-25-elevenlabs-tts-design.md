# ElevenLabs TTS Voice Output — Design Spec

**Date:** 2026-04-25  
**Status:** Approved

## Summary

Add voice output to the bunq voice banking demo. After each LLM reply, the frontend calls the ElevenLabs TTS API directly and plays the audio through the Web Audio API.

## Scope

- Frontend only (`frontend/index.html`)
- No backend changes required
- Demo quality: API key hardcoded as a JS constant

## Architecture & Data Flow

```
User speaks
  → POST /voice (backend)
  → reply_text displayed in UI
  → speakReply(reply_text) called
  → POST https://api.elevenlabs.io/v1/text-to-speech/{voiceId}
  → ArrayBuffer decoded via AudioContext
  → Audio plays through BufferSourceNode
```

## Implementation Details

### Constants (top of script block)
```js
const ELEVENLABS_API_KEY = 'YOUR_KEY_HERE';
const ELEVENLABS_VOICE_ID = 'gE0owC0H9C8SzfDyIUtB';
```

### New function: `speakReply(text)`
- Reuses existing `AudioContext` (created on first mic tap — satisfies browser user-gesture requirement)
- Calls ElevenLabs REST API: `POST /v1/text-to-speech/{voiceId}`
- Model: `eleven_multilingual_v2`
- Response decoded: `Response.arrayBuffer()` → `AudioContext.decodeAudioData()` → `AudioBufferSourceNode.start()`

### Integration point
Called inside the existing `fetchVoice()` response handler, after `reply_text` is set on the UI, before the orb returns to idle state.

## Error Handling

- ElevenLabs failure (bad key, rate limit, network error) is non-fatal
- Reply text is already displayed — audio failure does not regress UX
- Error logged to console with `console.warn`

## Out of Scope

- Streaming TTS (lower latency but more complex)
- Backend-proxied API key (unnecessary for demo)
- agent.js CLI voice output
