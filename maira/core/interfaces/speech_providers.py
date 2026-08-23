"""Provider-agnostic STT / TTS ports for Maira voice."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class STTProvider(ABC):
  @abstractmethod
  def get_provider_name(self) -> str: ...

  @abstractmethod
  def is_available(self) -> tuple[bool, str]: ...

  @abstractmethod
  def transcribe(self, audio: Any) -> str: ...

  def warm_up(self) -> None:
    return

  def start_stream(self) -> None:
    raise NotImplementedError("Streaming STT not implemented for this provider")

  def stop_stream(self) -> str:
    raise NotImplementedError("Streaming STT not implemented for this provider")


class TTSProvider(ABC):
  @abstractmethod
  def get_provider_name(self) -> str: ...

  @abstractmethod
  def is_available(self) -> tuple[bool, str]: ...

  @abstractmethod
  def synthesize(self, text: str) -> tuple[Any, int]:
    """Return (audio_array, sample_rate)."""

  def synthesize_stream(self, text: str) -> Iterator[Any]:
    audio, _rate = self.synthesize(text)
    if audio is not None and len(audio):
      yield audio

  def save_audio(self, text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    audio, rate = self.synthesize(text)
    from maira.shared.utils.wav_io import write_wav_float32

    write_wav_float32(path, audio, rate)
    return path

  def warm_up(self) -> None:
    return

  def stop(self) -> None:
    return
