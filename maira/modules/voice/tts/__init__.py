"""Text-to-speech submodule — synth and playback can be pipelined."""

from __future__ import annotations

from collections.abc import Iterator

from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.kokoro.engine import KokoroEngine


class TextToSpeech:
  def __init__(self, engine: KokoroEngine, audio: AudioStream) -> None:
    self._engine = engine
    self._audio = audio
    self._speaking = False

  def is_available(self) -> bool:
    return self._engine.is_available()

  def warm_up(self) -> None:
    self._engine.warm_up(synthesize=True)

  @property
  def sample_rate(self) -> int:
    return self._engine.sample_rate

  @property
  def speaking(self) -> bool:
    return self._speaking

  def synthesize_chunks(self, text: str) -> list:
    """Fully synthesize text into audio chunks (no playback)."""
    return [c for c in self._engine.synthesize_stream(text) if c is not None and len(c)]

  def synthesize_stream(self, text: str) -> Iterator:
    yield from self._engine.synthesize_stream(text)

  def play_chunks(self, chunks: list) -> None:
    """Play pre-synthesized chunks; respects stop()."""
    self._speaking = True
    try:
      for chunk in chunks:
        if not self._speaking:
          break
        if chunk is None or len(chunk) == 0:
          continue
        self._audio.play(chunk, sample_rate=self._engine.sample_rate)
    finally:
      self._speaking = False

  def speak(self, text: str) -> None:
    """Play speech ASAP — streams Kokoro chunks instead of waiting for full audio."""
    self._speaking = True
    try:
      for chunk in self._engine.synthesize_stream(text):
        if chunk is None or len(chunk) == 0:
          continue
        if not self._speaking:
          break
        self._audio.play(chunk, sample_rate=self._engine.sample_rate)
    finally:
      self._speaking = False

  def stop(self) -> None:
    self._speaking = False
    self._audio.stop_playback()
