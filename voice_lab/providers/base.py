"""Common TTS provider interface for the Voice Comparison Lab."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SynthesisResult:
  """Raw audio payload returned by synthesize()."""

  audio_bytes: bytes
  sample_rate: int
  format: str = "wav"
  meta: dict[str, Any] = field(default_factory=dict)


class TTSProvider(ABC):
  """Provider-agnostic TTS contract used by the comparison runner."""

  @abstractmethod
  def get_provider_name(self) -> str:
    """Stable provider id used in filenames and results (e.g. 'sarvam')."""

  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Return (available, human-readable reason)."""

  @abstractmethod
  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    """Generate audio bytes for text. Raises on failure."""

  @abstractmethod
  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    """Synthesize and write audio to disk. Returns the written path."""

  @abstractmethod
  def get_latency(self) -> float | None:
    """Last synthesis latency in seconds, or None if not yet run."""
