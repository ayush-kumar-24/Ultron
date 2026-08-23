# Phase 2 Manual Acceptance Test

## TEST 1 — Start Maira
`python -m maira` — app shell opens.

## TEST 2 — Text chat
Send a short message. Streaming reply appears. No crash.

## TEST 3 — Push-to-talk
Hold **Ctrl+Shift+V**. Status shows Listening.

## TEST 4 — Speak
Say a short sentence while holding.

## TEST 5 — Transcription
Release key. Transcript appears in chat.

## TEST 6 — Fast response start
Maira should begin speaking before the full reply finishes generating (sentence chunks).

## TEST 7 — Audio playback
Hear Kokoro speech.

## TEST 8 — Interrupt
While speaking, hold Ctrl+Shift+V again (or start listening). Speech stops / queue clears.

## TEST 9 — Speak again
Complete another turn successfully.

## TEST 10 — Disable TTS
Set `voice.auto_speak: false` in user config. Restart.

## TEST 11 — Text fallback
Voice still transcribes/brain replies as text without speech.

## TEST 12 — Disable Ollama
Stop Ollama service.

## TEST 13 — Friendly error
Chat/voice shows “Maira can't reach the local AI model.” (or voice-equivalent), no crash.

## TEST 14 — Restart Maira
App starts cleanly.

## TEST 15 — Resource release
No orphan Python TTS workers; Ollama llama-server only as expected for keep_alive.
