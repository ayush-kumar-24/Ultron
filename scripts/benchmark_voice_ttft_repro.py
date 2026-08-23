"""Reproduce live-bench TTFT inflation from cold-warm model loads."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import numpy as np

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

TEXT = "Hello Maira, what should I focus on today?"


def measure(brain: BrainService) -> float | None:
  first: list[float] = []
  bus = brain._streamer._event_bus  # noqa: SLF001

  def on_tok(_p: dict) -> None:
    if not first:
      first.append(time.perf_counter())

  bus.subscribe(TOPIC_TOKEN, on_tok)
  t0 = time.perf_counter()
  try:
    brain.send_message(TEXT, voice=True, max_tokens=64)
  finally:
    bus.unsubscribe(TOPIC_TOKEN, on_tok)
  return (first[0] - t0) if first else None


def fresh_brain(llm: OllamaClient, tag: str) -> BrainService:
  path = Path(database_path()).parent / f"diag_repro_{tag}.db"
  storage = SqliteStorage(path)
  apply_migrations(storage)
  brain = BrainService(
    llm,
    EventBus(),
    ConversationRepository(storage),
    ConversationSession(),
    memory=None,
    log_latency=False,
  )
  brain.new_conversation()
  return brain


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
      [{"role": "user", "content": "hi"}],
      options={"num_predict": 4, "temperature": 0.0},
    )
  )

  print("1) baseline empty brain", flush=True)
  print("   resources", snapshot_resources(), flush=True)
  b = fresh_brain(llm, "1")
  print(f"   TTFT={measure(b):.2f}s", flush=True)

  print("2) warm whisper+kokoro once", flush=True)
  stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    ),
    language=settings.voice.language,
  )
  tts = TextToSpeech(
    KokoroEngine(voice=settings.voice.tts_voice, lang_code=settings.voice.tts_lang),
    AudioStream(16000),
  )
  stt.warm_up()
  tts.warm_up()
  print("   resources", snapshot_resources(), flush=True)
  b = fresh_brain(llm, "2")
  print(f"   TTFT={measure(b):.2f}s", flush=True)

  print("3) simulate live bench cold-warm (extra cold loads)", flush=True)
  cold_tts = TextToSpeech(
    KokoroEngine(voice=settings.voice.tts_voice, lang_code=settings.voice.tts_lang),
    AudioStream(16000),
  )
  cold_stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    )
  )
  _ = cold_tts.synthesize_chunks("Good morning. I'm Maira.")
  sample = np.zeros(16000, dtype="float32")
  sample[2000:12000] = 0.05
  _ = cold_stt.transcribe(sample)
  print("   resources", snapshot_resources(), flush=True)
  b = fresh_brain(llm, "3")
  print(f"   TTFT no-guard={measure(b):.2f}s", flush=True)

  print("4) after STT on warm model, no-guard vs guard", flush=True)
  _ = stt.transcribe(sample)
  b = fresh_brain(llm, "4a")
  print(f"   TTFT no-guard={measure(b):.2f}s", flush=True)
  _ = stt.transcribe(sample)
  b = fresh_brain(llm, "4b")
  with llm_cpu_priority():
    print(f"   TTFT with-guard={measure(b):.2f}s", flush=True)

  llm.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
