"""Low-level audio stream capture and playback for voice pipeline."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from loguru import logger


class AudioStream:
  """Microphone capture and speaker playback via sounddevice."""

  def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
    self._sample_rate = sample_rate
    self._channels = channels
    self._frames: list = []
    self._stream = None
    self._lock = threading.Lock()
    self._recording = False
    self._cancel = threading.Event()

  @property
  def sample_rate(self) -> int:
    return self._sample_rate

  def is_available(self) -> bool:
    try:
      import sounddevice  # noqa: F401

      return True
    except Exception as exc:  # noqa: BLE001
      logger.warning("Audio backend unavailable: {}", exc)
      return False

  def request_cancel(self) -> None:
    """Signal an in-progress capture_utterance to abort."""
    self._cancel.set()

  def clear_cancel(self) -> None:
    self._cancel.clear()

  def start_recording(self) -> None:
    import sounddevice as sd

    with self._lock:
      if self._recording:
        return
      self._frames = []
      self._recording = True
      self._cancel.clear()

      def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001, ARG001
        if status:
          logger.debug("Audio input status: {}", status)
        if self._recording:
          self._frames.append(indata.copy())

      self._stream = sd.InputStream(
        samplerate=self._sample_rate,
        channels=self._channels,
        dtype="float32",
        callback=callback,
      )
      self._stream.start()

  def stop_recording(self):
    """Stop recording and return a float32 numpy waveform (mono)."""
    import numpy as np

    with self._lock:
      self._recording = False
      stream = self._stream
      self._stream = None
      frames = list(self._frames)
      self._frames = []

    if stream is not None:
      stream.stop()
      stream.close()

    if not frames:
      return np.zeros(0, dtype="float32")
    audio = np.concatenate(frames, axis=0)
    if audio.ndim > 1:
      audio = audio.mean(axis=1)
    return audio.astype("float32", copy=False)

  def capture_utterance(
    self,
    *,
    silence_seconds: float = 1.15,
    speech_threshold: float = 0.018,
    min_speech_seconds: float = 0.35,
    max_wait_for_speech: float = 12.0,
    max_seconds: float = 45.0,
    should_stop: Callable[[], bool] | None = None,
  ):
    """
    Record one spoken utterance and stop automatically after trailing silence.

    Flow:
    1. Wait for speech energy above threshold
    2. Keep recording while user talks
    3. After ~silence_seconds of quiet, stop and return audio
    """
    import numpy as np

    self.clear_cancel()
    self.start_recording()
    started = time.monotonic()
    speech_started_at: float | None = None
    silence_started_at: float | None = None
    poll = 0.05

    try:
      while True:
        if self._cancel.is_set() or (should_stop is not None and should_stop()):
          return np.zeros(0, dtype="float32")

        now = time.monotonic()
        elapsed = now - started
        if elapsed > max_seconds:
          break

        with self._lock:
          frames = list(self._frames)

        if frames:
          chunk = np.concatenate(frames[-8:], axis=0)
          if chunk.ndim > 1:
            chunk = chunk.mean(axis=1)
          rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
        else:
          rms = 0.0

        speaking = rms >= speech_threshold

        if speaking:
          if speech_started_at is None:
            speech_started_at = now
          silence_started_at = None
        elif speech_started_at is not None:
          spoken_for = now - speech_started_at
          if spoken_for >= min_speech_seconds:
            if silence_started_at is None:
              silence_started_at = now
            elif now - silence_started_at >= silence_seconds:
              break
        elif elapsed >= max_wait_for_speech:
          # No speech detected in time
          break

        time.sleep(poll)
    finally:
      audio = self.stop_recording()

    return audio

  def play(self, audio, sample_rate: int | None = None) -> None:
    import sounddevice as sd

    rate = sample_rate or self._sample_rate
    if not getattr(self, "_logged_output", False):
      self._logged_output = True
      try:
        device = sd.query_devices(kind="output")
        logger.info("Playing voice on speaker: {}", device.get("name", device))
      except Exception as exc:  # noqa: BLE001
        logger.warning("No speaker found: {}", exc)
    sd.play(audio, samplerate=rate)
    sd.wait()

  def stop_playback(self) -> None:
    try:
      import sounddevice as sd

      sd.stop()
    except Exception:  # noqa: BLE001
      return
