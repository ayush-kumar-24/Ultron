"""Voice LLM TTFT isolation benchmarks (no microphone required).

Usage:
  python -m scripts.benchmark_voice_diagnostics
  python -m scripts.benchmark_voice_brain_only
  python -m scripts.benchmark_voice_no_stt
  python -m scripts.benchmark_voice_no_tts

Proves why voice TTFT diverges from chat TTFT without changing llama3.2.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import numpy as np
from loguru import logger

from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.kokoro.engine import KokoroEngine
from maira.infrastructure.speech.whisper.engine import WhisperEngine
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_TOKEN
from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.tts import TextToSpeech
from maira.shared.utils.paths import database_path

TRANSCRIPT = "Hello Maira, what should I focus on today?"


def _fmt(v: float | None) -> str:
  return f"{v:.2f}s" if v is not None else "n/a"


def _fresh_brain(llm: OllamaClient, tmp_db: Path) -> BrainService:
  if tmp_db.exists():
    try:
      tmp_db.unlink()
    except OSError:
      pass
  storage = SqliteStorage(tmp_db)
  apply_migrations(storage)
  repo = ConversationRepository(storage)
  brain = BrainService(
    llm=llm,
    event_bus=EventBus(),
    repository=repo,
    session=ConversationSession(),
    memory=None,
    log_latency=False,
    history_messages=6,
  )
  brain.new_conversation()
  return brain


def _measure_ttft(brain: BrainService, text: str, *, voice: bool = True) -> dict:
  first: list[float] = []
  bus = brain._streamer._event_bus  # noqa: SLF001

  def on_token(payload: dict) -> None:
    if not first:
      first.append(time.perf_counter())

  bus.subscribe(TOPIC_TOKEN, on_token)
  marks: dict[str, float] = {}
  marks["brain_start"] = time.perf_counter()
  try:
    brain.send_message(text, voice=voice, max_tokens=64)
  finally:
    bus.unsubscribe(TOPIC_TOKEN, on_token)
  marks["complete"] = time.perf_counter()
  ttft = (first[0] - marks["brain_start"]) if first else None
  total = marks["complete"] - marks["brain_start"]
  history = brain.get_history()
  reply = history[-1].content if history else ""
  return {
    "ttft": ttft,
    "total": total,
    "reply_chars": len(reply),
    "prompt_estimate": sum(len(m.content) for m in history),
  }


def run_suite(*, use_guard: bool) -> list[dict]:
  settings = load_settings()
  llm = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
    keep_alive=settings.ollama.keep_alive,
  )
  assert llm.is_available(), "Ollama unavailable"
  # Warm Ollama like chat benchmark
  list(
    llm.chat_stream(
      [{"role": "user", "content": "Reply with one word: ok"}],
      options={"num_predict": 8, "temperature": 0.0},
    )
  )

  tmp = Path(database_path()).parent / "diag_voice.db"
  if tmp.exists():
    tmp.unlink()

  rows: list[dict] = []

  def row(name: str, **extra) -> None:
    res = snapshot_resources()
    print(f"\n=== {name} ===")
    print(f"resources before: {res}")
    brain = _fresh_brain(llm, tmp)
    if use_guard and name not in {"A_brain_only", "chat_style"}:
      with llm_cpu_priority():
        m = _measure_ttft(brain, TRANSCRIPT, voice=True)
    else:
      m = _measure_ttft(brain, TRANSCRIPT, voice=True)
    print(f"TTFT={_fmt(m['ttft'])} total={_fmt(m['total'])}")
    rows.append({"test": name, **m, **res, **extra})
    try:
      brain._repo._storage.close()  # noqa: SLF001
    except Exception:  # noqa: BLE001
      pass

  # A: brain only (no STT/TTS in process)
  row("A_brain_only", stt="-", tts="-")

  # B: load Whisper only, no STT call
  stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    ),
    language=settings.voice.language,
  )
  stt.warm_up()
  row("B_whisper_loaded", stt="loaded", tts="-")

  # C: run STT then LLM (no TTS)
  sample = np.zeros(int(16000 * 1.2), dtype="float32")
  sample[1000:14000] = 0.08 * np.sin(2 * np.pi * 180 * np.arange(13000) / 16000)
  t0 = time.perf_counter()
  _ = stt.transcribe(sample)
  stt_s = time.perf_counter() - t0
  row("C_after_stt", stt=f"ran:{stt_s:.2f}s", tts="-")

  # D: load Kokoro too
  audio = AudioStream(sample_rate=settings.voice.sample_rate)
  tts = TextToSpeech(
    KokoroEngine(voice=settings.voice.tts_voice, lang_code=settings.voice.tts_lang),
    audio,
  )
  tts.warm_up()
  row("D_whisper+kokoro", stt="loaded", tts="loaded")

  # E: STT again then LLM with both loaded
  _ = stt.transcribe(sample)
  row("E_after_stt_both", stt="ran", tts="loaded")

  llm.close()
  return rows


def print_table(rows: list[dict]) -> None:
  print()
  print("Test                  TTFT     Total    PyRSS     OllamaRSS")
  print("-" * 64)
  for r in rows:
    print(
      f"{r['test']:<22} {_fmt(r.get('ttft')):<8} {_fmt(r.get('total')):<8} "
      f"{str(r.get('python_rss_mb')):<9} {str(r.get('ollama_rss_mb'))}"
    )


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--guard", action="store_true", help="Apply llm_cpu_priority during LLM")
  parser.add_argument("--compare-guard", action="store_true", help="Run suite twice")
  args = parser.parse_args()

  if args.compare_guard:
    print("WITHOUT guard")
    a = run_suite(use_guard=False)
    print_table(a)
    print("\nWITH guard")
    b = run_suite(use_guard=True)
    print_table(b)
    return 0

  rows = run_suite(use_guard=args.guard)
  print_table(rows)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
