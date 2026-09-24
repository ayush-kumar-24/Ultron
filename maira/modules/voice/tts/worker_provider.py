"""TTS provider for models that run in their own environment (Chatterbox, Indic Parler)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from maira.core.interfaces.speech_providers import TTSProvider
from maira.infrastructure.speech.worker.engine import WorkerTTSEngine


class WorkerTTSProvider(TTSProvider):
  def __init__(self, name: str, engine: WorkerTTSEngine) -> None:
    self._name = name
    self._engine = engine  # bootstrap wires this engine into TextToSpeech

  @property
  def sample_rate(self) -> int:
    return self._engine.sample_rate

  def get_provider_name(self) -> str:
    return self._name

  def is_available(self) -> tuple[bool, str]:
    if self._engine.is_available():
      return True, "ready"
    return False, f"{self._name} voice is not installed. Run: python -m scripts.setup_voice {self._name}"

  def warm_up(self) -> None:
    self._engine.warm_up()

  def synthesize(self, text: str) -> tuple[Any, int]:
    return self._engine.synthesize(text)

  def synthesize_stream(self, text: str) -> Iterator[Any]:
    yield from self._engine.synthesize_stream(text)

  def stop(self) -> None:
    return
