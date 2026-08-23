"""Kokoro TTS — local/offline provider (no silent fallback)."""

from __future__ import annotations

import io
import time
import wave
from pathlib import Path

from voice_lab import config
from voice_lab.providers.base import SynthesisResult, TTSProvider


class KokoroProvider(TTSProvider):
  def __init__(self) -> None:
    self._latency: float | None = None
    self._pipeline = None
    self._voice = config.KOKORO_VOICE
    self._lang = config.KOKORO_LANG
    self._sample_rate = 24000

  def get_provider_name(self) -> str:
    return "kokoro"

  def get_latency(self) -> float | None:
    return self._latency

  def is_available(self) -> tuple[bool, str]:
    try:
      import kokoro  # noqa: F401
      import numpy  # noqa: F401
    except ImportError as exc:
      return (
        False,
        "Kokoro not installed. Run: pip install -e \".[voice-lab]\" "
        f"(missing: {exc})",
      )
    return True, f"ready (voice={self._voice}, offline)"

  def _ensure_pipeline(self):
    if self._pipeline is not None:
      return self._pipeline
    try:
      from kokoro import KPipeline
    except ImportError as exc:
      raise RuntimeError(
        "Kokoro package is not installed. Install with: pip install kokoro soundfile"
      ) from exc
    try:
      self._pipeline = KPipeline(lang_code=self._lang, repo_id="hexgrad/Kokoro-82M")
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(
        f"Kokoro model/pipeline failed to load for voice '{self._voice}': {exc}. "
        "Install/update kokoro and required model assets; "
        "this lab does not fall back to another TTS engine."
      ) from exc
    return self._pipeline

  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    ok, reason = self.is_available()
    if not ok:
      raise RuntimeError(reason)

    import numpy as np

    pipeline = self._ensure_pipeline()
    started = time.perf_counter()
    try:
      chunks: list = []
      for _gs, _ps, audio in pipeline(text, voice=self._voice):
        chunks.append(np.asarray(audio, dtype="float32"))
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(
        f"Kokoro synthesis failed for voice '{self._voice}': {exc}. "
        "No fallback provider will be used."
      ) from exc
    self._latency = time.perf_counter() - started

    if not chunks:
      raise RuntimeError("Kokoro returned empty audio")

    waveform = np.concatenate(chunks)
    audio_bytes = _float32_to_wav_bytes(waveform, self._sample_rate)
    return SynthesisResult(
      audio_bytes=audio_bytes,
      sample_rate=self._sample_rate,
      format="wav",
      meta={"voice": self._voice, "lang": self._lang, "script_id": script_id},
    )

  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = self.synthesize(text, script_id=script_id)
    path.write_bytes(result.audio_bytes)
    return path


def _float32_to_wav_bytes(waveform, sample_rate: int) -> bytes:
  import numpy as np

  clipped = np.clip(waveform, -1.0, 1.0)
  pcm = (clipped * 32767.0).astype(np.int16)
  buffer = io.BytesIO()
  with wave.open(buffer, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(pcm.tobytes())
  return buffer.getvalue()
