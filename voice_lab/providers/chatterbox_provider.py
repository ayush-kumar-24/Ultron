"""Chatterbox TTS — local Resemble AI provider (download opt-in)."""

from __future__ import annotations

import io
import time
import wave
from pathlib import Path

from voice_lab import config
from voice_lab.providers.base import SynthesisResult, TTSProvider


class ChatterboxProvider(TTSProvider):
  def __init__(self) -> None:
    self._latency: float | None = None
    self._model = None
    self._device = config.CHATTERBOX_DEVICE
    self._voice_prompt = config.CHATTERBOX_VOICE_PROMPT
    self._allow_download = config.CHATTERBOX_ALLOW_DOWNLOAD
    self._sample_rate = 24000

  def get_provider_name(self) -> str:
    return "chatterbox"

  def get_latency(self) -> float | None:
    return self._latency

  def is_available(self) -> tuple[bool, str]:
    try:
      import chatterbox  # noqa: F401
      import torch  # noqa: F401
    except ImportError as exc:
      return (
        False,
        "Chatterbox not installed. Run: pip install chatterbox-tts "
        f"(missing: {exc}). GPU recommended; CPU works but is slow.",
      )

    if self._voice_prompt and not Path(self._voice_prompt).exists():
      return False, f"CHATTERBOX_VOICE_PROMPT not found: {self._voice_prompt}"

    cached = _chatterbox_weights_cached()
    if not cached and not self._allow_download:
      return (
        False,
        "Chatterbox model weights not found locally. "
        "First run downloads a multi-GB model from Hugging Face. "
        "Set CHATTERBOX_ALLOW_DOWNLOAD=1 in voice_lab/.env to permit download, "
        "then re-run.",
      )
    detail = "weights cached" if cached else "download permitted"
    prompt = f", voice_prompt={self._voice_prompt}" if self._voice_prompt else " (default voice)"
    return True, f"ready ({detail}, device={self._device}{prompt})"

  def _ensure_model(self):
    if self._model is not None:
      return self._model
    try:
      from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
      raise RuntimeError(
        "chatterbox-tts is not installed. Install with: pip install chatterbox-tts"
      ) from exc

    if not _chatterbox_weights_cached() and self._allow_download:
      print(
        "[chatterbox] Model weights not cached. "
        "Downloading from Hugging Face (multi-GB). This may take a while..."
      )

    try:
      self._model = ChatterboxTTS.from_pretrained(device=self._device)
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(
        f"Failed to load Chatterbox on device '{self._device}': {exc}"
      ) from exc
    self._sample_rate = int(getattr(self._model, "sr", self._sample_rate))
    return self._model

  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    ok, reason = self.is_available()
    if not ok:
      raise RuntimeError(reason)

    import numpy as np

    model = self._ensure_model()
    kwargs = {}
    if self._voice_prompt:
      kwargs["audio_prompt_path"] = self._voice_prompt

    started = time.perf_counter()
    try:
      wav = model.generate(text, **kwargs)
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(f"Chatterbox synthesis failed: {exc}") from exc
    self._latency = time.perf_counter() - started

    tensor = wav
    if hasattr(tensor, "detach"):
      tensor = tensor.detach().cpu().numpy()
    waveform = np.asarray(tensor, dtype="float32").reshape(-1)
    audio_bytes = _float32_to_wav_bytes(waveform, self._sample_rate)
    return SynthesisResult(
      audio_bytes=audio_bytes,
      sample_rate=self._sample_rate,
      format="wav",
      meta={
        "device": self._device,
        "voice_prompt": self._voice_prompt or None,
        "script_id": script_id,
      },
    )

  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = self.synthesize(text, script_id=script_id)
    path.write_bytes(result.audio_bytes)
    return path


def _chatterbox_weights_cached() -> bool:
  """Best-effort check for local Hugging Face cache without downloading."""
  try:
    from huggingface_hub import try_to_load_from_cache
  except ImportError:
    # Without huggingface_hub we cannot detect cache; treat as not cached
    # unless the user explicitly allows download.
    return False

  # Common Chatterbox repo ids used by from_pretrained.
  candidates = [
    ("ResembleAI/chatterbox", "t3_cfg.safetensors"),
    ("ResembleAI/chatterbox", "s3gen.pt"),
    ("ResembleAI/chatterbox", "ve.pt"),
  ]
  for repo_id, filename in candidates:
    try:
      path = try_to_load_from_cache(repo_id, filename)
      if path is not None:
        return True
    except Exception:  # noqa: BLE001
      continue
  return False


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
