"""Lightweight energy-based VAD helpers."""

from __future__ import annotations

import numpy as np


def is_speech(
  frame,
  *,
  sample_rate: int = 16000,
  silence_threshold: float = 0.01,
) -> bool:
  """Return True when RMS energy suggests speech."""
  data = np.asarray(frame, dtype="float32").reshape(-1)
  if data.size == 0:
    return False
  rms = float(np.sqrt(np.mean(np.square(data))))
  return rms >= silence_threshold


def speech_ended(
  recent_frames: list,
  *,
  silence_timeout: float,
  frame_seconds: float,
  silence_threshold: float = 0.01,
) -> bool:
  """True when trailing silence spans silence_timeout."""
  if frame_seconds <= 0 or silence_timeout <= 0:
    return False
  needed = max(1, int(silence_timeout / frame_seconds))
  if len(recent_frames) < needed:
    return False
  trailing = recent_frames[-needed:]
  return not any(is_speech(f, silence_threshold=silence_threshold) for f in trailing)
