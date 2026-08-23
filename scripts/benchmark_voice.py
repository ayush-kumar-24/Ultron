"""Voice provider latency benchmark (no automatic multi-GB downloads).

Usage:
  python -m scripts.benchmark_voice
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from maira.app.settings import load_settings
from maira.modules.voice.download_guard import unavailable_message
from maira.modules.voice.tts.registry import (
  PROVIDER_SIZE_GB,
  available_tts_names,
  create_tts,
  ensure_default_tts_providers,
)

PHRASE = "Good morning. I'm Maira. How can I help you today?"


def _resources() -> tuple[str, str]:
  try:
    import psutil

    proc = psutil.Process()
    ram = f"{proc.memory_info().rss / (1024 * 1024):.0f} MB"
    cpu = f"{psutil.cpu_percent(interval=0.2):.0f}%"
    return cpu, ram
  except Exception:  # noqa: BLE001
    return "n/a", "n/a"


def _benchmark_provider(name: str, *, max_gb: float, voice: str) -> dict:
  ensure_default_tts_providers()
  estimated = PROVIDER_SIZE_GB.get(name, 1.0)
  if estimated > max_gb and name not in {"kokoro", "sarvam"}:
    return {
      "provider": name,
      "status": "UNAVAILABLE",
      "detail": unavailable_message(estimated_gb=estimated, max_gb=max_gb, provider=name),
    }

  t0 = time.perf_counter()
  provider = create_tts(
    name,
    voice=voice,
    max_model_download_gb=max_gb,
  )
  init_s = time.perf_counter() - t0
  ok, detail = provider.is_available()
  if not ok:
    return {
      "provider": name,
      "status": "UNAVAILABLE",
      "detail": detail,
      "init_s": init_s,
    }

  try:
    provider.warm_up()
  except Exception as exc:  # noqa: BLE001
    return {
      "provider": name,
      "status": "UNAVAILABLE",
      "detail": str(exc),
      "init_s": init_s,
    }

  first_audio = None
  t_synth = time.perf_counter()
  chunks = []
  try:
    for chunk in provider.synthesize_stream(PHRASE):
      if first_audio is None:
        first_audio = time.perf_counter()
      chunks.append(chunk)
  except Exception as exc:  # noqa: BLE001
    return {
      "provider": name,
      "status": "ERROR",
      "detail": str(exc),
      "init_s": init_s,
    }
  complete = time.perf_counter()
  import numpy as np

  audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")
  rate = getattr(provider, "sample_rate", 24000)
  duration = float(len(audio) / rate) if rate else 0.0
  cpu, ram = _resources()
  return {
    "provider": name,
    "status": "SUCCESS",
    "init_s": init_s,
    "first_audio_s": (first_audio - t_synth) if first_audio else None,
    "complete_s": complete - t_synth,
    "audio_duration_s": duration,
    "samples": int(len(audio)),
    "cpu": cpu,
    "ram": ram,
    "detail": detail,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Maira voice TTS provider benchmark")
  parser.add_argument(
    "--provider",
    default="kokoro",
    help="Provider to benchmark (default: kokoro). Use 'all' for registry scan.",
  )
  args = parser.parse_args()
  settings = load_settings()
  max_gb = settings.voice.max_model_download_gb
  voice = settings.voice.tts_voice

  names = available_tts_names() if args.provider == "all" else [args.provider]
  print("VOICE BENCHMARK")
  print("===============")
  print(f"Phrase: {PHRASE}")
  print(f"max_model_download_gb: {max_gb}")
  print()

  for name in names:
    result = _benchmark_provider(name, max_gb=max_gb, voice=voice)
    print(f"Provider:\n{result['provider']}")
    print()
    print("Latency:")
    if result.get("init_s") is not None:
      print(f"  init: {result['init_s']:.2f}s")
    if result.get("first_audio_s") is not None:
      print(f"  first_audio: {result['first_audio_s']:.2f}s")
    if result.get("complete_s") is not None:
      print(f"  complete: {result['complete_s']:.2f}s")
    print()
    if result.get("audio_duration_s") is not None:
      print(f"Audio duration:\n{result['audio_duration_s']:.2f}s")
      print()
    if result.get("cpu"):
      print(f"CPU:\n{result['cpu']}")
      print()
      print(f"RAM:\n{result['ram']}")
      print()
    print(f"Status:\n{result['status']}")
    if result.get("detail"):
      print(f"Detail: {result['detail']}")
    print()
    print("---")
    print()

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
