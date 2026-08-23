"""Async-friendly audio playback wrapper (non-UI-blocking when used off Qt thread)."""

from __future__ import annotations

import threading

from maira.infrastructure.speech.audio.stream import AudioStream


class AudioPlayer:
  def __init__(self, audio: AudioStream, *, volume: float = 1.0) -> None:
    self._audio = audio
    self._volume = max(0.0, min(1.0, volume))
    self._lock = threading.Lock()
    self._playing = False

  @property
  def playing(self) -> bool:
    return self._playing

  def set_volume(self, volume: float) -> None:
    self._volume = max(0.0, min(1.0, volume))

  def play(self, audio, *, sample_rate: int | None = None) -> None:
    import numpy as np

    with self._lock:
      self._playing = True
      try:
        data = np.asarray(audio, dtype="float32")
        if self._volume != 1.0:
          data = data * self._volume
        self._audio.play(data, sample_rate=sample_rate)
      finally:
        self._playing = False

  def stop(self) -> None:
    self._playing = False
    self._audio.stop_playback()

  def flush(self) -> None:
    self.stop()
