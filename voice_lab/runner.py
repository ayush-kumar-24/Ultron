"""CLI runner — synthesize comparison clips for all available providers."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from voice_lab import config
from voice_lab.benchmark import (
  ProviderRunResult,
  file_size_mb,
  result_to_dict,
  wav_duration_seconds,
  wav_sample_rate,
  write_results,
)
from voice_lab.providers import all_providers


def detect_providers() -> list[tuple[object, bool, str]]:
  rows = []
  for provider in all_providers():
    ok, reason = provider.is_available()
    rows.append((provider, ok, reason))
  return rows


def run_comparison(*, scripts: list[str] | None = None) -> dict:
  config.ensure_output_dir()
  script_ids = scripts or list(config.SCRIPTS.keys())
  detections = detect_providers()

  print("Maira Voice Comparison Lab")
  print("=" * 40)
  for provider, ok, reason in detections:
    mark = "AVAILABLE" if ok else "UNAVAILABLE"
    print(f"  [{mark}] {provider.get_provider_name()}: {reason}")
  print()

  results: dict = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "scripts": {},
    "providers": {},
  }

  for provider, ok, reason in detections:
    name = provider.get_provider_name()
    results["providers"][name] = {
      "available": ok,
      "detail": reason,
    }

  for script_id in script_ids:
    text = config.SCRIPTS[script_id]
    results["scripts"][script_id] = {}
    print(f"Script: {script_id}")
    print("-" * 40)

    for provider, ok, reason in detections:
      name = provider.get_provider_name()
      out_path = config.OUTPUT_DIR / f"{name}_{script_id}.wav"

      if not ok:
        run = ProviderRunResult(status="unavailable", error=reason, model=name)
        results["scripts"][script_id][name] = result_to_dict(run)
        print(f"  {name}: SKIPPED — {reason}")
        continue

      try:
        provider.save_audio(text, out_path, script_id=script_id)
        latency = provider.get_latency()
        duration = wav_duration_seconds(out_path)
        rate = wav_sample_rate(out_path)
        size = file_size_mb(out_path)
        run = ProviderRunResult(
          status="success",
          latency_seconds=round(latency, 4) if latency is not None else None,
          duration_seconds=round(duration, 4) if duration is not None else None,
          file_size_mb=size,
          sample_rate=rate,
          model=name,
          output_file=str(out_path.name),
        )
        results["scripts"][script_id][name] = result_to_dict(run)
        print(
          f"  {name}: SUCCESS  latency={run.latency_seconds}s  "
          f"duration={run.duration_seconds}s  file={out_path.name}"
        )
      except Exception as exc:  # noqa: BLE001
        run = ProviderRunResult(status="error", error=str(exc), model=name)
        results["scripts"][script_id][name] = result_to_dict(run)
        print(f"  {name}: ERROR — {exc}")

    print()

  # Flat summary for the first script (UI-friendly), plus nested detail.
  primary = script_ids[0]
  flat = {}
  for name, payload in results["scripts"].get(primary, {}).items():
    flat[name] = {
      "status": payload.get("status"),
      "latency_seconds": payload.get("latency_seconds"),
      "duration_seconds": payload.get("duration_seconds"),
      "file_size_mb": payload.get("file_size_mb"),
      "sample_rate": payload.get("sample_rate"),
      "model": payload.get("model"),
      "output_file": payload.get("output_file"),
      "error": payload.get("error"),
    }
  results.update(flat)

  write_results(config.RESULTS_PATH, results)
  print(f"Wrote results: {config.RESULTS_PATH}")
  return results


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description="Maira Voice Comparison Lab runner")
  parser.add_argument(
    "--script",
    choices=["english", "hindi", "hinglish", "all"],
    default="all",
    help="Which test script(s) to generate",
  )
  parser.add_argument(
    "--ui",
    action="store_true",
    help="Launch the side-by-side evaluation UI instead of generating",
  )
  args = parser.parse_args(argv)

  if args.ui:
    from voice_lab.ui import launch_ui

    return launch_ui()

  scripts = list(config.SCRIPTS.keys()) if args.script == "all" else [args.script]
  run_comparison(scripts=scripts)
  return 0


if __name__ == "__main__":
  sys.exit(main())
