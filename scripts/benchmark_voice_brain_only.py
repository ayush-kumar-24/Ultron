"""Voice brain-only TTFT (fixed transcript, no STT/TTS loaded).

Usage:
  python -m scripts.benchmark_voice_brain_only
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from scripts.benchmark_voice_diagnostics import TRANSCRIPT, _fresh_brain, _fmt, _measure_ttft
from maira.app.settings import load_settings
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.modules.voice.resource_guard import snapshot_resources
from maira.shared.utils.paths import database_path


def main() -> int:
  settings = load_settings()
  llm = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
    keep_alive=settings.ollama.keep_alive,
  )
  list(
    llm.chat_stream(
      [{"role": "user", "content": "Reply: ok"}],
      options={"num_predict": 4, "temperature": 0.0},
    )
  )
  tmp = Path(database_path()).parent / "diag_brain_only.db"
  brain = _fresh_brain(llm, tmp)
  print("VOICE BRAIN ONLY")
  print("================")
  print(f"Transcript: {TRANSCRIPT!r}")
  print(f"Resources: {snapshot_resources()}")
  m = _measure_ttft(brain, TRANSCRIPT, voice=True)
  print(f"LLM TTFT: {_fmt(m['ttft'])}")
  print(f"Total: {_fmt(m['total'])}")
  llm.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
