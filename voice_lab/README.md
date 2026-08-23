# Maira Voice Comparison Lab

Isolated evaluation tool for offline/open TTS providers for Maira.

**Default:** Kokoro (`af_heart`)  
**Also wired:** Indic Parler-TTS (Divya), Veena (kavya), optional Chatterbox  

Scripts: **English**, **Hindi**, **Hinglish**.

This lab does **not** modify Maira Brain/Chat. No automatic winner — listen and score yourself.

**Resource policy:** multi-GB models (Veena ~7.5GB, Indic Parler ~3.75GB) are **unavailable** unless already cached or you explicitly set `PARLER_ALLOW_DOWNLOAD=1` / `VEENA_ALLOW_DOWNLOAD=1`. Default `MAX_MODEL_DOWNLOAD_GB=1`.

## Quick start

```powershell
# Base lab (Kokoro)
pip install -e ".[voice-lab]"

# Indic Parler-TTS
pip install git+https://github.com/huggingface/parler-tts.git

# Veena
pip install snac accelerate bitsandbytes

copy voice_lab\.env.example voice_lab\.env
# Set PARLER_ALLOW_DOWNLOAD=1 and/or VEENA_ALLOW_DOWNLOAD=1 for first-time model pulls

python -m voice_lab.runner
python -m voice_lab.runner --ui
```

## Outputs

`voice_lab/output/{provider}_{english|hindi|hinglish}.wav` + `results.json`

Providers: `kokoro`, `indic_parler`, `veena`, `chatterbox`

## Dependency matrix

| Provider | Female voice | Type | Notes |
|----------|--------------|------|-------|
| **Kokoro** | `af_heart` | Local, CPU OK | Default, lightest |
| **Indic Parler** | `Divya` | Local, GPU better | `ai4bharat/indic-parler-tts`, opt-in download |
| **Veena** | `kavya` | Local, **GPU recommended** | `maya-research/veena-tts` ~3B, multi-GB, opt-in download |
| **Chatterbox** | ref clip / default | Local, GPU recommended | Optional |

## Manual checklist (1–10)

Score each provider on English / Hindi / Hinglish separately if needed.

| Category | Kokoro | Indic Parler | Veena | Chatterbox |
| ------------------------ | ------ | ------------ | ----- | ---------- |
| Naturalness | | | | |
| Female voice quality | | | | |
| Hindi pronunciation | | | | |
| English pronunciation | | | | |
| Hinglish | | | | |
| Conversational feel | | | | |
| Latency | | | | |
| Offline suitability | | | | |
| Overall Maira suitability | | | | |

## Tests

```powershell
python -m pytest tests/unit/test_voice_lab.py -q
```
