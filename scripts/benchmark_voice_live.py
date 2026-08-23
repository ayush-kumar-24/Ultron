"""Live microphone → STT → Ollama → Kokoro → speaker latency benchmark.

Usage:
  python -m scripts.benchmark_voice_live
  python -m scripts.benchmark_voice_live --cold-warm-only
  python -m scripts.benchmark_voice_live --no-playback

Uses REAL mic/STT/Ollama/TTS. Does not download models.
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
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN
from maira.modules.voice.latency import VoiceLatencyTrace
from maira.modules.voice.streaming.chunker import TextChunker
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.tts import TextToSpeech
from maira.shared.utils.paths import database_path


def _delta(a: float | None, b: float | None) -> float | None:
  if a is None or b is None:
    return None
  return a - b


def _fmt(v: float | None) -> str:
  return f"{v:.2f}s" if v is not None else "n/a"


def _resources() -> tuple[str, str]:
  try:
    import psutil

    p = psutil.Process()
    return f"{psutil.cpu_percent(interval=0.2):.0f}%", f"{p.memory_info().rss / (1024 * 1024):.0f} MB"
  except Exception:  # noqa: BLE001
    return "n/a", "n/a"


def _build_stack(settings, *, playback: bool):
  audio = AudioStream(sample_rate=settings.voice.sample_rate)
  stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    ),
    language=settings.voice.language,
  )
  tts_engine = KokoroEngine(
    voice=settings.voice.tts_voice,
    lang_code=settings.voice.tts_lang,
    allow_fallback=False,
  )
  tts = TextToSpeech(tts_engine, audio)
  bus = EventBus()
  storage = SqliteStorage(database_path())
  apply_migrations(storage)
  repo = ConversationRepository(storage)
  llm = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
    keep_alive=settings.ollama.keep_alive,
  )
  brain = BrainService(
    llm=llm,
    event_bus=bus,
    repository=repo,
    session=ConversationSession(),
    memory=None,
    log_latency=True,
    recall_mode="keyword",
  )
  # Isolate from production chat history unless explicitly requested later.
  brain.new_conversation()
  return {
    "audio": audio,
    "stt": stt,
    "tts": tts,
    "tts_engine": tts_engine,
    "bus": bus,
    "llm": llm,
    "brain": brain,
    "storage": storage,
    "playback": playback,
  }


def bench_cold_warm(stack, phrase: str = "Good morning. I'm Maira.") -> dict:
  """Measure cold vs warm TTS and STT (no microphone)."""
  stt: SpeechToText = stack["stt"]
  tts: TextToSpeech = stack["tts"]
  engine: KokoroEngine = stack["tts_engine"]

  # Fresh engine for true cold TTS
  cold_engine = KokoroEngine(
    voice=engine._voice,  # noqa: SLF001
    lang_code=engine._lang_code,  # noqa: SLF001
  )
  cold_tts = TextToSpeech(cold_engine, stack["audio"])

  t0 = time.perf_counter()
  chunks_cold = cold_tts.synthesize_chunks(phrase)
  t1 = time.perf_counter()
  cold_first = t1 - t0  # full synth as first-audio proxy when single stream batch

  # Warm path (already used cold_engine once — also warm primary)
  tts.warm_up()
  t2 = time.perf_counter()
  chunks_warm = tts.synthesize_chunks(phrase)
  t3 = time.perf_counter()
  warm_first = t3 - t2

  # STT cold vs warm
  sample = np.zeros(int(16000 * 1.0), dtype="float32")
  sample[2000:12000] = 0.05 * np.sin(2 * np.pi * 220 * np.arange(10000) / 16000)

  fresh_stt = SpeechToText(
    WhisperEngine(
      model_size=stt._engine._model_size if hasattr(stt._engine, "_model_size") else "tiny.en",  # noqa: SLF001
      device=getattr(stt._engine, "_device", "cpu"),  # noqa: SLF001
      compute_type=getattr(stt._engine, "_compute_type", "int8"),  # noqa: SLF001
    )
  )
  s0 = time.perf_counter()
  fresh_stt.transcribe(sample)
  s1 = time.perf_counter()
  stt_cold = s1 - s0

  stt.warm_up()
  s2 = time.perf_counter()
  stt.transcribe(sample)
  s3 = time.perf_counter()
  stt_warm = s3 - s2

  cpu, ram = _resources()
  return {
    "tts_cold_s": cold_first,
    "tts_warm_s": warm_first,
    "tts_cold_chunks": len(chunks_cold),
    "tts_warm_chunks": len(chunks_warm),
    "stt_cold_s": stt_cold,
    "stt_warm_s": stt_warm,
    "cpu": cpu,
    "ram": ram,
  }


def run_live(stack, settings, *, silence: float) -> dict:
  audio: AudioStream = stack["audio"]
  stt: SpeechToText = stack["stt"]
  tts: TextToSpeech = stack["tts"]
  brain: BrainService = stack["brain"]
  bus: EventBus = stack["bus"]
  playback: bool = stack["playback"]

  if not audio.is_available():
    raise RuntimeError("Microphone/audio backend unavailable")
  if not stt.is_available():
    raise RuntimeError("STT unavailable")
  if not tts.is_available():
    raise RuntimeError("TTS unavailable")
  if not stack["llm"].is_available():
    raise RuntimeError("Ollama unavailable")

  print()
  print("Say a short sentence after the microphone starts.")
  print(f"(silence_timeout={silence}s — stop speaking and wait)")
  print()

  marks: dict[str, float] = {}
  marks["mic_start"] = time.perf_counter()
  print("[mic] listening...")

  speech_detected = {"t": None}

  # Lightweight wrapper: capture_utterance already does VAD; we approximate speech_start
  # by polling RMS while a parallel capture runs — use capture_utterance directly and
  # mark speech_end when it returns.
  uttered = audio.capture_utterance(
    silence_seconds=silence,
    speech_threshold=0.015,
    min_speech_seconds=0.3,
    max_wait_for_speech=15.0,
    max_seconds=20.0,
  )
  marks["speech_end"] = time.perf_counter()

  if uttered is None or len(uttered) < 800:
    raise RuntimeError("No speech captured — try again closer to the mic")

  # Approximate speech duration from sample count
  speech_dur = len(uttered) / float(audio.sample_rate)
  marks["speech_start"] = marks["speech_end"] - speech_dur  # approx including trailing silence

  marks["stt_start"] = time.perf_counter()
  transcript = stt.transcribe(uttered).strip()
  marks["stt_complete"] = time.perf_counter()
  print(f"[stt] {transcript!r}")
  if not transcript:
    raise RuntimeError("Empty transcript")

  chunker = TextChunker(
    min_chars=settings.voice.chunk_min_chars,
    max_chars=settings.voice.chunk_max_chars,
  )
  first_token = {"t": None}
  first_chunk = {"t": None}
  first_audio = {"t": None}
  playback_start = {"t": None}
  playback_end = {"t": None}
  sentences: list[str] = []

  def on_token(payload: dict) -> None:
    token = str(payload.get("token", ""))
    if not token:
      return
    if first_token["t"] is None:
      first_token["t"] = time.perf_counter()
    for sentence in chunker.push(token):
      if first_chunk["t"] is None:
        first_chunk["t"] = time.perf_counter()
      sentences.append(sentence)

  def on_complete(payload: dict) -> None:
    del payload
    for sentence in chunker.flush():
      if first_chunk["t"] is None:
        first_chunk["t"] = time.perf_counter()
      sentences.append(sentence)

  bus.subscribe(TOPIC_TOKEN, on_token)
  bus.subscribe(TOPIC_COMPLETE, on_complete)

  marks["brain_start"] = time.perf_counter()
  from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources

  print(f"[resources pre-llm] {snapshot_resources()}")
  try:
    with llm_cpu_priority():
      marks["ollama_request"] = time.perf_counter()
      brain.send_message(transcript, voice=True, max_tokens=settings.voice.max_reply_tokens)
  finally:
    bus.unsubscribe(TOPIC_TOKEN, on_token)
    bus.unsubscribe(TOPIC_COMPLETE, on_complete)

  marks["brain_complete"] = time.perf_counter()
  if first_token["t"]:
    marks["first_llm_token"] = first_token["t"]
  if first_chunk["t"]:
    marks["first_sentence"] = first_chunk["t"]

  if not sentences:
    # Fallback: whole reply
    history = brain.get_history()
    reply = history[-1].content if history else ""
    if reply:
      sentences = [reply]

  print(f"[chunks] {sentences}")

  # TTS first sentence (critical path for first audible)
  if sentences:
    marks["tts_start"] = time.perf_counter()
    chunks = tts.synthesize_chunks(sentences[0])
    marks["first_audio"] = time.perf_counter()
    first_audio["t"] = marks["first_audio"]
    if playback and chunks:
      marks["playback_start"] = time.perf_counter()
      playback_start["t"] = marks["playback_start"]
      tts.play_chunks(chunks)
      marks["playback_end"] = time.perf_counter()
      playback_end["t"] = marks["playback_end"]
    # Pipeline remaining sentences after first audible measurement
    for sentence in sentences[1:]:
      more = tts.synthesize_chunks(sentence)
      if playback and more:
        tts.play_chunks(more)

  marks["complete"] = time.perf_counter()
  cpu, ram = _resources()

  speech_end = marks["speech_end"]
  stt_s = _delta(marks.get("stt_complete"), marks.get("stt_start"))
  # Prefer ollama_request→first token when available (excludes brain setup).
  ttft = _delta(marks.get("first_llm_token"), marks.get("ollama_request") or marks.get("brain_start"))
  brain_setup = _delta(marks.get("ollama_request"), marks.get("brain_start"))
  chunk_s = _delta(marks.get("first_sentence"), marks.get("first_llm_token"))
  tts_fa = _delta(marks.get("first_audio"), marks.get("tts_start"))
  play_s = _delta(marks.get("playback_start"), marks.get("first_audio"))
  first_audible = _delta(
    marks.get("playback_start") or marks.get("first_audio"),
    speech_end,
  )
  total = _delta(marks.get("complete"), speech_end)

  logger.info(
    "[MAIRA LIVE VOICE LATENCY] speech_end={} stt={} llm_ttft={} chunk={} "
    "tts_first_audio={} playback={} first_audible={} total={}",
    _fmt(0.0),
    _fmt(stt_s),
    _fmt(ttft),
    _fmt(chunk_s),
    _fmt(tts_fa),
    _fmt(play_s),
    _fmt(first_audible),
    _fmt(total),
  )

  return {
    "transcript": transcript,
    "sentences": sentences,
    "speech_duration_s": speech_dur,
    "stt_s": stt_s,
    "brain_setup_s": brain_setup,
    "llm_ttft_s": ttft,
    "chunk_s": chunk_s,
    "tts_first_audio_s": tts_fa,
    "playback_latency_s": play_s,
    "first_audible_s": first_audible,
    "total_s": total,
    "cpu": cpu,
    "ram": ram,
    "marks": marks,
  }


def _print_live(result: dict) -> None:
  print()
  print("MAIRA LIVE VOICE LATENCY")
  print("========================")
  print(f"Transcript: {result['transcript']!r}")
  print(f"Speech duration: {_fmt(result['speech_duration_s'])}")
  print(f"STT: {_fmt(result['stt_s'])}")
  print(f"Brain setup: {_fmt(result.get('brain_setup_s'))}")
  print(f"LLM TTFT: {_fmt(result['llm_ttft_s'])}")
  print(f"Chunk: {_fmt(result['chunk_s'])}")
  print(f"TTS first audio: {_fmt(result['tts_first_audio_s'])}")
  print(f"Playback start latency: {_fmt(result['playback_latency_s'])}")
  print(f"speech_end → first audible: {_fmt(result['first_audible_s'])}")
  print(f"Total after speech_end: {_fmt(result['total_s'])}")
  print(f"CPU: {result['cpu']}  RAM: {result['ram']}")

  # Bottleneck share of first_audible
  parts = {
    "STT": result["stt_s"] or 0.0,
    "LLM TTFT": result["llm_ttft_s"] or 0.0,
    "Chunk": result["chunk_s"] or 0.0,
    "TTS": result["tts_first_audio_s"] or 0.0,
    "Playback": result["playback_latency_s"] or 0.0,
  }
  total_parts = sum(parts.values()) or 1.0
  print()
  print("Contribution to first audible path:")
  for name, val in parts.items():
    pct = 100.0 * val / total_parts
    print(f"  {name}: {_fmt(val)} ({pct:.0f}%)")
  dominant = max(parts, key=parts.get)
  print()
  print(f"Bottleneck: {dominant}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Live Maira voice latency benchmark")
  parser.add_argument(
    "--cold-warm-only",
    action="store_true",
    help="Only measure cold vs warm STT/TTS (no microphone)",
  )
  parser.add_argument(
    "--with-cold-warm",
    action="store_true",
    help="Run cold/warm component bench BEFORE live (loads extra models; skews TTFT)",
  )
  parser.add_argument("--no-playback", action="store_true", help="Skip speaker playback")
  parser.add_argument("--silence", type=float, default=None, help="Silence timeout seconds")
  args = parser.parse_args()

  settings = load_settings()
  silence = args.silence if args.silence is not None else settings.voice.silence_seconds
  stack = _build_stack(settings, playback=not args.no_playback)

  try:
    print("Warming STT/TTS once (no duplicate cold loads)...")
    stack["stt"].warm_up()
    if not args.cold_warm_only:
      # Prefer STT warm before live; TTS warm is optional for TTFT purity.
      stack["tts"].warm_up()

    if args.cold_warm_only or args.with_cold_warm:
      print()
      print("COLD vs WARM (component) — warning: extra model loads use ~+1GB RAM")
      print("------------------------")
      cw = bench_cold_warm(stack)
      print(f"TTS cold: {_fmt(cw['tts_cold_s'])}")
      print(f"TTS warm: {_fmt(cw['tts_warm_s'])}")
      print(f"STT cold: {_fmt(cw['stt_cold_s'])}")
      print(f"STT warm: {_fmt(cw['stt_warm_s'])}")
      print(f"CPU/RAM: {cw['cpu']} / {cw['ram']}")

    if args.cold_warm_only:
      return 0

    # Tiny Ollama keep-alive ping so llama-server is hot before the timed turn.
    list(
      stack["llm"].chat_stream(
        [{"role": "user", "content": "ok"}],
        options={"num_predict": 2, "temperature": 0.0},
      )
    )

    result = run_live(stack, settings, silence=silence)
    _print_live(result)
    return 0
  except KeyboardInterrupt:
    print("\nCancelled.")
    return 130
  except Exception as exc:  # noqa: BLE001
    print(f"ERROR: {exc}")
    return 1
  finally:
    try:
      stack["llm"].close()
    except Exception:  # noqa: BLE001
      pass
    try:
      stack["storage"].close()
    except Exception:  # noqa: BLE001
      pass


if __name__ == "__main__":
  raise SystemExit(main())
