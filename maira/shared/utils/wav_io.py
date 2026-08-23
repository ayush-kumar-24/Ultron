"""Minimal WAV helpers."""

from __future__ import annotations

import wave
from pathlib import Path


def write_wav_float32(path: Path, audio, sample_rate: int) -> None:
  import numpy as np

  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  clipped = np.clip(np.asarray(audio, dtype="float32").reshape(-1), -1.0, 1.0)
  pcm = (clipped * 32767.0).astype("int16")
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(pcm.tobytes())
