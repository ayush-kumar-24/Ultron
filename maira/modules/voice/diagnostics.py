"""Developer diagnostics snapshot for Maira voice/brain systems."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SystemDiagnostics:
  brain: str = "UNKNOWN"
  llm: str = "UNKNOWN"
  stt: str = "UNKNOWN"
  tts: str = "UNKNOWN"
  memory: str = "UNKNOWN"
  microphone: str = "UNKNOWN"
  audio: str = "UNKNOWN"
  last_latency: dict[str, Any] | None = None

  def as_lines(self) -> list[str]:
    lines = [
      "MAIRA SYSTEM",
      f"Brain: {self.brain}",
      f"LLM: {self.llm}",
      f"STT: {self.stt}",
      f"TTS: {self.tts}",
      f"Memory: {self.memory}",
      f"Microphone: {self.microphone}",
      f"Audio: {self.audio}",
    ]
    if self.last_latency:
      lines.append("Last latency:")
      for key, value in self.last_latency.items():
        lines.append(f"  {key}: {value}")
    return lines


def collect_diagnostics(container) -> SystemDiagnostics:
  """Best-effort snapshot from the DI container (never raises)."""
  diag = SystemDiagnostics()
  try:
    settings = container.resolve("settings")
    diag.llm = settings.ollama.model
  except Exception:  # noqa: BLE001
    pass
  try:
    llm = container.resolve("llm")
    diag.brain = "READY" if llm.is_available() else "UNAVAILABLE"
  except Exception:  # noqa: BLE001
    diag.brain = "UNAVAILABLE"
  try:
    voice = container.resolve("voice")
    diag.stt = "READY" if voice._stt.is_available() else "UNAVAILABLE"  # noqa: SLF001
    diag.tts = "READY" if voice._tts.is_available() else "UNAVAILABLE"  # noqa: SLF001
    diag.microphone = "READY" if voice._audio.is_available() else "UNAVAILABLE"  # noqa: SLF001
    diag.audio = diag.microphone
    lat = voice.last_latency()
    if lat is not None:
      diag.last_latency = {
        "STT": None if lat.stt_start is None or lat.stt_complete is None else round(lat.stt_complete - lat.stt_start, 2),
        "LLM": None if lat.brain_start is None or lat.first_llm_token is None else round(lat.first_llm_token - lat.brain_start, 2),
        "TTS": None if lat.tts_start is None or lat.first_audio is None else round(lat.first_audio - lat.tts_start, 2),
        "Total": None if lat.speech_end is None or lat.complete is None else round(lat.complete - lat.speech_end, 2),
      }
  except Exception:  # noqa: BLE001
    pass
  try:
    worker = container.resolve("memory_worker")
    diag.memory = "BUSY" if getattr(worker, "busy", False) else "READY"
  except Exception:  # noqa: BLE001
    diag.memory = "READY"
  return diag
