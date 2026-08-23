"""Voice port — push-to-talk listening, transcription, and speech playback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class VoiceStatus(str, Enum):
  IDLE = "idle"
  LISTENING = "listening"
  TRANSCRIBING = "transcribing"
  THINKING = "thinking"
  PROCESSING = "processing"  # legacy alias used by older UI subscribers
  SPEAKING = "speaking"
  INTERRUPTED = "interrupted"
  ERROR = "error"


class Voice(ABC):
  @abstractmethod
  def is_available(self) -> bool:
    """Return True when mic, STT, and TTS can run."""

  @abstractmethod
  def status(self) -> VoiceStatus:
    """Current voice pipeline status."""

  @abstractmethod
  def start_listening(self) -> None:
    """Begin push-to-talk recording."""

  @abstractmethod
  def stop_listening(self) -> None:
    """Stop recording, transcribe, send to Brain, and speak the reply."""

  @abstractmethod
  def stop_speaking(self) -> None:
    """Interrupt TTS playback if active."""
