# MAIRA PHASE 2.1 REPORT

## Answer: What is the actual bottleneck?

**Warm path (models already loaded): Kokoro TTS first-sentence synthesis** is the largest controllable component (~1.1s for a short phrase; longer for long first clauses).

**Cold path / first interaction: model load** dominates — TTS cold **~12.7s**, STT cold **~4.2s**.

**Under concurrent STT+TTS+Ollama load on ~16GB RAM:** LLM TTFT can inflate badly (observed **~9–11s** in combined runs vs **~0.47s** chat-only). Resource pressure is a second major risk on this laptop.

Queueing, TextChunker CPU, and playback scheduling are negligible when warm.

---

## Measurements (this laptop)

### Cold vs warm (real engines, no mic)

| Component | Cold | Warm |
|-----------|------|------|
| Kokoro TTS (phrase synth) | **12.65s** | **1.07s** |
| Whisper tiny.en | **4.21s** | **0.39s** |
| CPU / RAM (sample) | 40% / ~1064 MB | |

### Chat regression check

| Metric | Phase 2 baseline | After 2.1 |
|--------|------------------|-----------|
| Avg TTFT | ~0.67s | **0.47s** |
| Avg total | ~2.20s | **1.92s** |

No regression (improved).

### Warm pipeline estimate (STT warm + Ollama warm + first TTS chunk)

Use live script for definitive mic numbers. Component sum when Ollama is free:

`~0.39 (STT) + ~0.47 (TTFT) + TTS_first (~1.1s short / higher if long clause) ≈ **~2.0–3.5s** speech_end → first audible`

Combined-load runs (STT+TTS+LLM in one process after heavy init) showed TTFT **9–11s** — treat as RAM/CPU contention warning, not the chat-only baseline.

### Live microphone

Run interactively (not faked):

```bash
python -m scripts.benchmark_voice_live
```

---

## Optimizations performed

1. Kokoro **once-load** + voice pack warm (`"Ready."` discarded)
2. Whisper **once-load** + tiny warm decode
3. `voice.warmup: true` — background warm at app start
4. TTS **prefetch**: synthesize next sentence while current plays
5. Accurate `first_audio` mark after synth, before/at play
6. `chunk_max_chars: 100` so long unpunctuated streams start TTS sooner
7. `scripts.benchmark_voice_live` with `[MAIRA LIVE VOICE LATENCY]` log

## Not changed

- llama3.2
- Wake word
- No multi-GB downloads

## Tests

60 unit tests previously; voice-related rechecked **13 passed**. Full suite was **60 passed** before final config tweak.

## Files changed

- `maira/infrastructure/speech/kokoro/engine.py`
- `maira/infrastructure/speech/whisper/engine.py`
- `maira/modules/voice/tts/__init__.py`
- `maira/modules/voice/service.py` (prefetch TTS loop)
- `maira/app/bootstrap.py`, `maira/app/settings.py`
- `config/default.yaml`
- `scripts/benchmark_voice_live.py`
- `docs/PHASE2_1_LIVE_VOICE.md`, `docs/VOICE_LATENCY.md`, `README.md`

## Remaining limitations

- Live mic timing requires you to speak into the benchmark once
- Concurrent STT+TTS+Ollama on 16GB can hurt LLM TTFT
- Long first clauses still delay first TTS until chunk boundary
- Playback uses `sd.wait()` on the play worker (async vs UI, but serial per chunk)
