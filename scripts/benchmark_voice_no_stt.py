"""Fixed transcript → Brain → LLM → TTS (no microphone / no Whisper).

Usage:
  python -m scripts.benchmark_voice_no_stt
  python -m scripts.benchmark_voice_no_stt --no-tts
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from scripts.benchmark_voice_diagnostics import TRANSCRIPT, _fresh_brain, _fmt, _measure_ttft
from maira.app.settings import load_settings
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.kokoro.engine import KokoroEngine
from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources
from maira.modules.voice.tts import TextToSpeech
from maira.shared.utils.paths import database_path


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--no-tts", action="store_true")
  parser.add_argument("--guard", action="store_true", default=True)
  parser.add_argument("--no-guard", action="store_true")
  args = parser.parse_args()
  use_guard = args.guard and not args.no_guard

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

  tts = None
  if not args.no_tts:
    tts = TextToSpeech(
      KokoroEngine(voice=settings.voice.tts_voice, lang_code=settings.voice.tts_lang),
      AudioStream(sample_rate=settings.voice.sample_rate),
    )
    tts.warm_up()

  tmp = Path(database_path()).parent / "diag_no_stt.db"
  brain = _fresh_brain(llm, tmp)
  print("VOICE NO STT")
  print("============")
  print(f"Transcript: {TRANSCRIPT!r}")
  print(f"TTS loaded: {tts is not None}")
  print(f"Guard: {use_guard}")
  print(f"Resources: {snapshot_resources()}")

  if use_guard:
    with llm_cpu_priority():
      m = _measure_ttft(brain, TRANSCRIPT, voice=True)
  else:
    m = _measure_ttft(brain, TRANSCRIPT, voice=True)

  print(f"LLM TTFT: {_fmt(m['ttft'])}")
  print(f"Total: {_fmt(m['total'])}")

  if tts is not None:
    history = brain.get_history()
    reply = history[-1].content if history else "Hello."
    t0 = time.perf_counter()
    chunks = tts.synthesize_chunks(reply.split(".")[0] + "." if "." in reply else reply[:80])
    print(f"TTS first-audio: {_fmt(time.perf_counter() - t0)} ({len(chunks)} chunks)")

  llm.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
