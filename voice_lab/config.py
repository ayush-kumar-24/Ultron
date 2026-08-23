"""Voice lab configuration — paths, scripts, and provider defaults."""

from __future__ import annotations

import os
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = LAB_ROOT / "output"
TEST_SCRIPT_PATH = LAB_ROOT / "test_script.txt"
RESULTS_PATH = OUTPUT_DIR / "results.json"
ENV_EXAMPLE_PATH = LAB_ROOT / ".env.example"

# Load .env from voice_lab/ if present (never commit secrets).
_ENV_PATH = LAB_ROOT / ".env"
if _ENV_PATH.exists():
  for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
      continue
    key, _, value = stripped.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if key and key not in os.environ:
      os.environ[key] = value


def _truthy(name: str, default: str = "0") -> bool:
  return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


SCRIPTS = {
  "english": (
    "Good morning. I'm Maira, your personal AI companion. "
    "You have three important things to focus on today. "
    "First, continue developing the Maira project. "
    "Second, finish testing the current system. "
    "And third, take some time to plan what you want to accomplish tomorrow. "
    "If you'd like, I can help you organize your entire day."
  ),
  "hindi": (
    "नमस्ते। मैं मैरा हूँ, आपकी व्यक्तिगत एआई साथी। "
    "आज आपके तीन महत्वपूर्ण काम हैं। "
    "पहला, मैरा प्रोजेक्ट का विकास जारी रखना। "
    "दूसरा, वर्तमान सिस्टम को ठीक से जाँचना। "
    "और तीसरा, कल के लक्ष्यों की योजना बनाना। "
    "अगर आप चाहें, तो मैं आपका पूरा दिन व्यवस्थित कर सकती हूँ।"
  ),
  "hinglish": (
    "Good morning. Aaj tumhare teen important tasks hain. "
    "Pehla, Maira project ka development continue karna hai. "
    "Dusra, current system ko properly test karna hai. "
    "Aur teesra, kal ke goals ko plan karna hai. "
    "Agar tum chaho, main tumhara pura day organize kar sakti hoon."
  ),
}

# Kokoro — default light offline English female
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
KOKORO_LANG = os.environ.get("KOKORO_LANG", "a")

# Indic Parler-TTS — AI4Bharat (Divya female)
PARLER_SPEAKER = os.environ.get("PARLER_SPEAKER", "Divya")
PARLER_DEVICE = os.environ.get("PARLER_DEVICE", "auto")
PARLER_ALLOW_DOWNLOAD = _truthy("PARLER_ALLOW_DOWNLOAD")

# Veena — Maya Research (kavya female)
VEENA_SPEAKER = os.environ.get("VEENA_SPEAKER", "kavya")
VEENA_DEVICE = os.environ.get("VEENA_DEVICE", "auto")
VEENA_ALLOW_DOWNLOAD = _truthy("VEENA_ALLOW_DOWNLOAD")

CHATTERBOX_DEVICE = os.environ.get("CHATTERBOX_DEVICE", "cpu")
CHATTERBOX_VOICE_PROMPT = os.environ.get("CHATTERBOX_VOICE_PROMPT", "").strip()
CHATTERBOX_ALLOW_DOWNLOAD = _truthy("CHATTERBOX_ALLOW_DOWNLOAD")

# Refuse automatic multi-GB downloads in the lab unless explicitly allowed above.
MAX_MODEL_DOWNLOAD_GB = float(os.environ.get("MAX_MODEL_DOWNLOAD_GB", "1") or "1")

LAB_PROVIDERS = ("kokoro", "indic_parler", "veena", "chatterbox")


def ensure_output_dir() -> Path:
  OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
  return OUTPUT_DIR
