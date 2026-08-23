# Voice Setup

## Requirements

```bash
pip install -e ".[voice]"
```

Ollama must be running with `llama3.2:latest` (do not replace for Phase 2).

## Configuration (`config/default.yaml`)

```yaml
voice:
  enabled: true
  stt_provider: faster_whisper
  tts_provider: kokoro
  whisper_model: tiny.en
  tts_voice: af_heart
  auto_speak: true
  interrupt_on_speech: true
  max_model_download_gb: 1
```

Optional cloud:

```bash
set SARVAM_API_KEY=...
```

Sarvam is never required.

## Benchmarks

```bash
python -m scripts.benchmark_voice
python -m scripts.benchmark_voice_e2e
python -m scripts.benchmark_chat --warmup --runs 5
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Mic error | Check Windows privacy → Microphone; Retry |
| STT unavailable | `pip install -e ".[voice]"` |
| TTS unavailable | Install Kokoro extras; keep `tts_provider: kokoro` |
| Ollama error | Start Ollama; confirm `llama3.2:latest` |
| Huge download blocked | Expected for Veena/Parler; set allow flags only intentionally |
