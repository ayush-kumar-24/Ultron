"""Microphone input manager — device discovery, buffering, graceful errors."""

from __future__ import annotations

from loguru import logger

from maira.infrastructure.speech.audio.stream import AudioStream


class MicrophoneManager:
  """Thin orchestration over AudioStream for voice pipeline."""

  def __init__(self, audio: AudioStream | None = None, *, sample_rate: int = 16000) -> None:
    self._audio = audio or AudioStream(sample_rate=sample_rate)
    self._sample_rate = sample_rate
    self._last_error = ""

  @property
  def sample_rate(self) -> int:
    return self._sample_rate

  @property
  def last_error(self) -> str:
    return self._last_error

  def is_available(self) -> bool:
    return self._audio.is_available()

  def list_devices(self) -> list[dict]:
    try:
      import sounddevice as sd

      devices = sd.query_devices()
      result = []
      for idx, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
          continue
        result.append(
          {
            "index": idx,
            "name": str(device.get("name", f"Device {idx}")),
            "channels": int(device.get("max_input_channels", 0)),
            "sample_rate": float(device.get("default_samplerate", self._sample_rate)),
          }
        )
      return result
    except Exception as exc:  # noqa: BLE001
      self._last_error = str(exc)
      logger.warning("Microphone device listing failed: {}", exc)
      return []

  def start(self) -> None:
    self._last_error = ""
    try:
      self._audio.start_recording()
    except Exception as exc:  # noqa: BLE001
      self._last_error = "Maira can't access your microphone."
      raise RuntimeError(self._last_error) from exc

  def stop(self):
    return self._audio.stop_recording()

  def capture_utterance(self, **kwargs):
    return self._audio.capture_utterance(**kwargs)

  def request_cancel(self) -> None:
    self._audio.request_cancel()

  def clear_cancel(self) -> None:
    self._audio.clear_cancel()

  @property
  def stream(self) -> AudioStream:
    return self._audio
