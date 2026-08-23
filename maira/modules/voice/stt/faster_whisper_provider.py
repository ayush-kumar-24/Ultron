"""faster-whisper STT provider adapter."""

from __future__ import annotations

from typing import Any

from maira.core.interfaces.speech_providers import STTProvider
from maira.infrastructure.speech.whisper.engine import WhisperEngine


class FasterWhisperSTT(STTProvider):
  def __init__(self, engine: WhisperEngine, *, language: str | None = None) -> None:
    self._engine = engine
    self._language = language

  def get_provider_name(self) -> str:
    return "faster_whisper"

  def is_available(self) -> tuple[bool, str]:
    ok = self._engine.is_available()
    return ok, "ready" if ok else "faster-whisper unavailable"

  def warm_up(self) -> None:
    self._engine.warm_up()

  def transcribe(self, audio: Any) -> str:
    return self._engine.transcribe(audio, language=self._language)
