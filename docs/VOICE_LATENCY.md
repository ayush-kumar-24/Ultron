# Voice Latency

Logs use:

```
[MAIRA VOICE LATENCY] STT=...s LLM_TTFT=...s First_sentence=...s TTS_first_audio=...s Total=...s
```

## Marks

1. `speech_end`
2. `stt_start` / `stt_complete`
3. `brain_start`
4. `first_llm_token`
5. `first_sentence`
6. `tts_start`
7. `first_audio` / `playback_start`
8. `complete`

## Live device (Phase 2.1)

```bash
python -m scripts.benchmark_voice_live
python -m scripts.benchmark_voice_live --cold-warm-only
```

Log line:

```
[MAIRA LIVE VOICE LATENCY] speech_end=... stt=... llm_ttft=... chunk=... tts_first_audio=... playback=... first_audible=... total=...
```

Warm-up (`voice.warmup: true`) cuts cold TTS from ~12s to ~1s on this laptop.
