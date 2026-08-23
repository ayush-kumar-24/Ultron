"""Voice latency telemetry (monotonic clocks)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class VoiceLatencyTrace:
  speech_start: float | None = None
  speech_end: float | None = None
  stt_start: float | None = None
  stt_complete: float | None = None
  brain_start: float | None = None
  first_llm_token: float | None = None
  first_sentence: float | None = None
  tts_start: float | None = None
  first_audio: float | None = None
  playback_start: float | None = None
  complete: float | None = None
  marks: dict[str, float] = field(default_factory=dict)

  def mark(self, name: str) -> None:
    now = time.perf_counter()
    self.marks[name] = now
    if hasattr(self, name):
      current = getattr(self, name)
      if current is None:
        setattr(self, name, now)

  def _delta(self, end: float | None, start: float | None) -> float | None:
    if end is None or start is None:
      return None
    return end - start

  def log_summary(self) -> None:
    stt = self._delta(self.stt_complete, self.stt_start)
    ttft = self._delta(self.first_llm_token, self.brain_start)
    sentence = self._delta(self.first_sentence, self.brain_start)
    tts_first = self._delta(self.first_audio, self.tts_start or self.first_sentence)
    total = self._delta(self.complete, self.speech_end or self.stt_start)
    logger.info(
      "[MAIRA VOICE LATENCY] STT={}s LLM_TTFT={}s First_sentence={}s "
      "TTS_first_audio={}s Total={}s",
      f"{stt:.2f}" if stt is not None else "n/a",
      f"{ttft:.2f}" if ttft is not None else "n/a",
      f"{sentence:.2f}" if sentence is not None else "n/a",
      f"{tts_first:.2f}" if tts_first is not None else "n/a",
      f"{total:.2f}" if total is not None else "n/a",
    )
