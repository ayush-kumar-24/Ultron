"""Benchmark Maira chat latency against the configured local Ollama model.

Usage:
  python -m scripts.benchmark_chat
  python scripts/benchmark_chat.py

Does not pull models. Uses config/default.yaml (+ user overrides).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

# Allow running as `python scripts/benchmark_chat.py`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from maira.app.settings import load_settings
from maira.infrastructure.llm.ollama.client import OllamaClient


PROMPT = "Reply in exactly one short sentence: What is Maira?"


def _run_once(client: OllamaClient) -> dict:
  messages = [
    {
      "role": "system",
      "content": (
        "You are Maira, the user's personal AI assistant. "
        "Be concise. Never identify as Llama, Meta, or Ollama."
      ),
    },
    {"role": "user", "content": PROMPT},
  ]
  start = time.perf_counter()
  first_token_at: float | None = None
  tokens: list[str] = []
  for token in client.chat_stream(messages, options={"temperature": 0.3, "num_predict": 64}):
    if first_token_at is None:
      first_token_at = time.perf_counter()
    tokens.append(token)
  end = time.perf_counter()
  text = "".join(tokens)
  ttft = (first_token_at - start) if first_token_at is not None else None
  total = end - start
  gen = (end - first_token_at) if first_token_at is not None else None
  tps = (len(tokens) / gen) if gen and gen > 0 else None
  return {
    "ttft": ttft,
    "total": total,
    "tokens": len(tokens),
    "chars": len(text),
    "tokens_per_second": tps,
    "text": text.strip(),
  }


def _optional_resource_snapshot() -> str:
  try:
    import psutil
  except ImportError:
    return "Resource diagnostics: install psutil for RAM/CPU (optional)"

  process = psutil.Process()
  mem = process.memory_info().rss / (1024 * 1024)
  cpu = psutil.cpu_percent(interval=0.2)
  return f"Process RSS: {mem:.0f} MB | CPU (sample): {cpu:.0f}%"


def main() -> int:
  parser = argparse.ArgumentParser(description="Maira chat latency benchmark")
  parser.add_argument("--runs", type=int, default=5, help="Number of timed runs")
  parser.add_argument(
    "--warmup",
    action="store_true",
    help="Run one untimed warm-up request first (loads model into RAM)",
  )
  parser.add_argument(
    "--resources",
    action="store_true",
    help="Print optional process RAM/CPU diagnostics (requires psutil)",
  )
  args = parser.parse_args()

  settings = load_settings()
  client = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
    keep_alive=settings.ollama.keep_alive,
  )

  print("MAIRA CHAT BENCHMARK")
  print("=" * 20)
  print(f"Model: {settings.ollama.model}")
  print(f"Host:  {settings.ollama.host}")
  print()

  if not client.is_available(force=True):
    print("FAIL: Maira can't reach the local AI model.")
    print("Start Ollama and ensure llama3.2:latest is installed.")
    client.close()
    return 1

  try:
    if args.warmup:
      print("Warm-up run (untimed)...")
      _run_once(client)
      print("Warm-up complete.\n")

    results = []
    for index in range(1, args.runs + 1):
      result = _run_once(client)
      results.append(result)
      ttft = result["ttft"]
      total = result["total"]
      tps = result["tokens_per_second"]
      print(f"Run {index}:")
      print(f"TTFT: {ttft:.2f} s" if ttft is not None else "TTFT: n/a")
      print(f"Total: {total:.2f} s")
      if tps is not None:
        print(f"Tokens/sec: {tps:.1f}")
      print(f"Response: {result['text'][:120]}")
      print()

    ttfts = [r["ttft"] for r in results if r["ttft"] is not None]
    totals = [r["total"] for r in results]
    print("Summary")
    print("-------")
    if ttfts:
      print(f"Average TTFT: {statistics.mean(ttfts):.2f} s")
      print(f"Min TTFT: {min(ttfts):.2f} s")
      print(f"Max TTFT: {max(ttfts):.2f} s")
    print(f"Average Total: {statistics.mean(totals):.2f} s")
    print(f"Min Total: {min(totals):.2f} s")
    print(f"Max Total: {max(totals):.2f} s")
    if args.resources:
      print()
      print(_optional_resource_snapshot())
    return 0
  finally:
    client.close()


if __name__ == "__main__":
  raise SystemExit(main())
