"""Integration smoke for voice pipeline adapters (skips without voice extras)."""

from __future__ import annotations

import numpy as np
import pytest

from maira.app.settings import load_settings


pytestmark = pytest.mark.integration


def _voice_deps_available() -> bool:
  try:
    import sounddevice  # noqa: F401
    import faster_whisper  # noqa: F401
    import pyttsx3  # noqa: F401
  except ImportError:
    return False
  return True


@pytest.mark.skipif(not _voice_deps_available(), reason="voice extras not installed")
def test_whisper_transcribes_silence_without_crash() -> None:
  from maira.infrastructure.speech.whisper.engine import WhisperEngine

  settings = load_settings()
  engine = WhisperEngine(
    model_size=settings.voice.whisper_model,
    device=settings.voice.whisper_device,
    compute_type=settings.voice.whisper_compute_type,
  )
  assert engine.is_available()
  audio = np.zeros(settings.voice.sample_rate, dtype="float32")
  text = engine.transcribe(audio, language=settings.voice.language)
  assert isinstance(text, str)


@pytest.mark.skipif(not _voice_deps_available(), reason="voice extras not installed")
def test_tts_synthesizes_short_phrase() -> None:
  from maira.infrastructure.speech.kokoro.engine import KokoroEngine

  engine = KokoroEngine()
  assert engine.is_available()
  audio, rate = engine.synthesize("Hello Maira")
  assert rate > 0
  assert len(audio) > 0
