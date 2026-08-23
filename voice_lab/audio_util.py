"""Shared audio helpers for voice lab providers."""

from __future__ import annotations

import io
import wave


def float32_to_wav_bytes(waveform, sample_rate: int) -> bytes:
  import numpy as np

  clipped = np.clip(np.asarray(waveform, dtype="float32").reshape(-1), -1.0, 1.0)
  pcm = (clipped * 32767.0).astype(np.int16)
  buffer = io.BytesIO()
  with wave.open(buffer, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(pcm.tobytes())
  return buffer.getvalue()


def hf_cached(repo_id: str, filename: str) -> bool:
  try:
    from huggingface_hub import try_to_load_from_cache
  except ImportError:
    return False
  try:
    path = try_to_load_from_cache(repo_id, filename)
    return path is not None
  except Exception:  # noqa: BLE001
    return False
