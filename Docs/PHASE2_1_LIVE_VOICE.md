# Phase 2.1 — Live Voice Validation

## Goal

Validate and optimize the real microphone → Maira → speaker pipeline on this laptop.

## Commands

```bash
# Cold vs warm STT/TTS only (no mic)
python -m scripts.benchmark_voice_live --cold-warm-only

# Full live turn (you speak after the prompt)
python -m scripts.benchmark_voice_live

# Skip speaker output (still measures TTS synth)
python -m scripts.benchmark_voice_live --no-playback
```

## Acceptance

| speech_end → first audible | Rating |
|----------------------------|--------|
| < 2s | excellent |
| 2–3s | acceptable |
| 3–4s | needs work |
| > 4s | unacceptable |

## Optimizations in 2.1

- Kokoro loads once; voice pack warmed with discarded `"Ready."`
- Whisper warm decode after load
- Startup `voice.warmup: true` (background)
- TTS worker synthesizes next sentence while current plays
- Live latency log: `[MAIRA LIVE VOICE LATENCY]`
