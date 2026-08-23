"""Benchmark helpers — latency, duration, size, status."""

from __future__ import annotations

import json
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderRunResult:
  status: str
  latency_seconds: float | None = None
  duration_seconds: float | None = None
  file_size_mb: float | None = None
  sample_rate: int | None = None
  model: str | None = None
  output_file: str | None = None
  error: str | None = None
  meta: dict[str, Any] = field(default_factory=dict)


def wav_duration_seconds(path: Path) -> float | None:
  try:
    with wave.open(str(path), "rb") as wav:
      frames = wav.getnframes()
      rate = wav.getframerate()
      if rate <= 0:
        return None
      return frames / float(rate)
  except Exception:  # noqa: BLE001
    return None


def wav_sample_rate(path: Path) -> int | None:
  try:
    with wave.open(str(path), "rb") as wav:
      return int(wav.getframerate())
  except Exception:  # noqa: BLE001
    return None


def file_size_mb(path: Path) -> float:
  return round(path.stat().st_size / (1024 * 1024), 4)


def write_results(path: Path, results: dict[str, Any]) -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(results, indent=2), encoding="utf-8")
  return path


def load_results(path: Path) -> dict[str, Any]:
  if not path.exists():
    return {}
  return json.loads(path.read_text(encoding="utf-8"))


def result_to_dict(result: ProviderRunResult) -> dict[str, Any]:
  data = asdict(result)
  return data
