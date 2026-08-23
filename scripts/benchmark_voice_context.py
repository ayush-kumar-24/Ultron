"""Compare voice TTFT: production conversation vs empty."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import psutil

from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_TOKEN
from maira.shared.utils.paths import database_path


def measure(brain: BrainService, text: str) -> float | None:
  first: list[float] = []
  bus = brain._streamer._event_bus  # noqa: SLF001

  def on_tok(_p: dict) -> None:
    if not first:
      first.append(time.perf_counter())

  bus.subscribe(TOPIC_TOKEN, on_tok)
  t0 = time.perf_counter()
  try:
    brain.send_message(text, voice=True, max_tokens=64)
  finally:
    bus.unsubscribe(TOPIC_TOKEN, on_tok)
  return (first[0] - t0) if first else None


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
      [{"role": "user", "content": "ok"}],
      options={"num_predict": 4, "temperature": 0.0},
    )
  )

  print("Processes:")
  for p in psutil.process_iter(["pid", "name", "memory_info"]):
    name = (p.info["name"] or "").lower()
    if "ollama" in name or "llama" in name:
      rss = p.info["memory_info"].rss / (1024 * 1024) if p.info["memory_info"] else 0
      print(f"  {p.info['pid']} {p.info['name']} rss={rss:.0f}MB")

  storage = SqliteStorage(database_path())
  apply_migrations(storage)
  repo = ConversationRepository(storage)
  brain = BrainService(
    llm, EventBus(), repo, ConversationSession(), memory=None, log_latency=False
  )
  msgs = brain.get_history()
  chars = sum(len(m.content) for m in msgs)
  payload = brain._session.to_llm_payload()  # noqa: SLF001
  recent = payload[-6:] if len(payload) > 6 else payload
  print(f"prod history messages={len(msgs)} chars={chars}")
  print(
    "voice window msgs="
    f"{len(recent)} chars={sum(len(m['content']) for m in recent)}"
  )

  text = "Hello Maira, what should I focus on today?"
  ttft = measure(brain, text)
  print(f"PROD_DB voice TTFT={ttft:.2f}s" if ttft else "PROD_DB failed")

  brain.new_conversation()
  ttft2 = measure(brain, text)
  print(f"EMPTY voice TTFT={ttft2:.2f}s" if ttft2 else "EMPTY failed")

  llm.close()
  storage.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
