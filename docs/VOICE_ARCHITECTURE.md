# Voice Architecture

Maira voice shares the same `BrainService` and conversation session as text chat.

```
Mic / PTT
  → MicrophoneManager / AudioStream (+ VAD silence end in conversation mode)
  → STTProvider (faster-whisper)
  → BrainService (token stream on EventBus)
  → TextChunker (sentence / phrase boundaries)
  → AudioQueue
  → TTSProvider (Kokoro) / TextToSpeech
  → AudioPlayer / AudioStream.play
```

## Providers

Selection is configuration-driven (`voice.stt_provider`, `voice.tts_provider`).

| Role | Default | Notes |
|------|---------|--------|
| STT | `faster_whisper` | `tiny.en` on CPU |
| TTS | `kokoro` | `af_heart`, offline |
| Cloud TTS | `sarvam` | optional; requires `SARVAM_API_KEY` |
| Heavy TTS | veena / indic_parler / chatterbox | blocked by `max_model_download_gb` |

## States

`IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE`

Barge-in: `SPEAKING → INTERRUPTED / LISTENING` clears the audio queue and stops TTS.

## Push-to-talk

- Hold **Ctrl+Shift+V** to listen; release to transcribe → brain → speak
- **Alt+V** or Chat mic toggles continuous voice mode

## Resource policy

`voice.limits.max_model_download_gb` (default `1`) prevents automatic multi-GB model downloads.
