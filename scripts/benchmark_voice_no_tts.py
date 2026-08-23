"""Microphone optional: STT → Brain → LLM (no Kokoro).

Usage:
  python -m scripts.benchmark_voice_no_tts
  python -m scripts.benchmark_voice_no_tts --synthetic
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

from scripts.benchmark_voice_diagnostics import TRANSCRIPT, _fresh_brain, _fmt, _measure_ttft
from maira.app.settings import load_settings
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.whisper.engine import WhisperEngine
from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources
from maira.modules.voice.stt import SpeechToText
from maira.shared.utils.paths import database_path


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--synthetic",
    action="store_true",
    help="Skip mic; run STT on synthetic audio then use fixed transcript for Brain",
  )
  parser.add_argument("--no-guard", action="store_true")
  args = parser.parse_args()

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

  stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    ),
    language=settings.voice.language,
  )
  stt.warm_up()

  print("VOICE NO TTS")
  print("============")
  print(f"Resources after Whisper warm: {snapshot_resources()}")

  if args.synthetic:
    sample = np.zeros(int(16000 * 1.5), dtype="float32")
    sample[2000:14000] = 0.1 * np.sin(2 * np.pi * 200 * np.arange(12000) / 16000)
    t0 = time.perf_counter()
    raw = stt.transcribe(sample).strip()
    stt_s = time.perf_counter() - t0
    transcript = TRANSCRIPT  # fixed text for stable Brain compare
    print(f"STT latency: {_fmt(stt_s)} (raw={raw!r}; using fixed transcript)")
  else:
    audio = AudioStream(sample_rate=settings.voice.sample_rate)
    print("Say a short sentence after the microphone starts.")
    uttered = audio.capture_utterance(silence_seconds=settings.voice.silence_seconds)
    t0 = time.perf_counter()
    transcript = stt.transcribe(uttered).strip()
    stt_s = time.perf_counter() - t0
    print(f"STT: {_fmt(stt_s)} → {transcript!r}")
    if not transcript:
      print("Empty transcript")
      return 1

  tmp = Path(database_path()).parent / "diag_no_tts.db"
  brain = _fresh_brain(llm, tmp)
  if args.no_guard:
    m = _measure_ttft(brain, transcript, voice=True)
  else:
    with llm_cpu_priority():
      m = _measure_ttft(brain, transcript, voice=True)

  print(f"LLM TTFT: {_fmt(m['ttft'])}")
  print(f"Total: {_fmt(m['total'])}")
  print(f"Resources: {snapshot_resources()}")
  llm.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
