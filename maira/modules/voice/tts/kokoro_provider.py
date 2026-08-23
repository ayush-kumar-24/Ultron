"""Kokoro TTS provider adapter."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from maira.core.interfaces.speech_providers import TTSProvider
from maira.infrastructure.speech.kokoro.engine import KokoroEngine


class KokoroTTSProvider(TTSProvider):
  def __init__(self, engine: KokoroEngine) -> None:
    self._engine = engine

  @property
  def sample_rate(self) -> int:
    return self._engine.sample_rate

  def get_provider_name(self) -> str:
    return "kokoro"

  def is_available(self) -> tuple[bool, str]:
    ok = self._engine.is_available()
    return ok, "ready" if ok else "Kokoro TTS unavailable"

  def warm_up(self) -> None:
    self._engine.warm_up()

  def synthesize(self, text: str) -> tuple[Any, int]:
    return self._engine.synthesize(text)

  def synthesize_stream(self, text: str) -> Iterator[Any]:
    yield from self._engine.synthesize_stream(text)

  def stop(self) -> None:
    return
