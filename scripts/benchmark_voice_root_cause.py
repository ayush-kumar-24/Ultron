"""Phase 2.2 final root-cause suite — prove whether Kokoro affects LLM TTFT.

Usage:
  python -m scripts.benchmark_voice_root_cause
  python -m scripts.benchmark_voice_root_cause --full   # includes mic Test D (3 runs)
  python -m scripts.benchmark_voice_root_cause --skip-g # skip STT+Kokoro mic test

Does NOT download models. Does NOT change llama3.2.
"""

from __future__ import annotations

import argparse
import sys
import threading
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
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN
from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources
from maira.modules.voice.streaming.chunker import TextChunker
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.tts import TextToSpeech
from maira.shared.utils.paths import database_path

TRANSCRIPT = "Hello Maira, what should I focus on today?"


def _fmt(v: float | None) -> str:
  return f"{v:.2f}s" if v is not None else "n/a"


class ResourceMonitor:
  def __init__(self, interval: float = 0.25) -> None:
    self.interval = interval
    self.samples: list[dict] = []
    self._stop = threading.Event()
    self._thread: threading.Thread | None = None
    self._stage = "idle"

  def set_stage(self, stage: str) -> None:
    self._stage = stage

  def start(self) -> None:
    self.samples.clear()
    self._stop.clear()
    self._thread = threading.Thread(target=self._loop, name="maira-res-mon", daemon=True)
    self._thread.start()

  def stop(self) -> None:
    self._stop.set()
    if self._thread:
      self._thread.join(timeout=2.0)

  def _loop(self) -> None:
    try:
      import psutil
    except ImportError:
      return
    t0 = time.perf_counter()
    while not self._stop.is_set():
      py = psutil.Process()
      llama_cpu = llama_rss = None
      for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
        name = (p.info.get("name") or "").lower()
        if "llama-server" in name:
          mem = p.info.get("memory_info")
          llama_rss = round(mem.rss / (1024 * 1024), 1) if mem else None
          try:
            llama_cpu = p.cpu_percent(interval=None)
          except Exception:  # noqa: BLE001
            pass
          break
      self.samples.append(
        {
          "t": round(time.perf_counter() - t0, 2),
          "stage": self._stage,
          "cpu": psutil.cpu_percent(interval=None),
          "ram_mb": round(psutil.virtual_memory().used / (1024 * 1024), 0),
          "py_cpu": py.cpu_percent(interval=None),
          "py_rss": round(py.memory_info().rss / (1024 * 1024), 1),
          "llama_cpu": llama_cpu,
          "llama_rss": llama_rss,
        }
      )
      time.sleep(self.interval)

  def print_timeline(self, limit: int = 40) -> None:
    print("time | stage | CPU% | RAM_MB | py_CPU | py_RSS | llama_CPU | llama_RSS")
    for s in self.samples[:limit]:
      print(
        f"{s['t']:>5} | {s['stage']:<12} | {s['cpu']!s:>5} | {s['ram_mb']!s:>6} | "
        f"{s['py_cpu']!s:>6} | {s['py_rss']!s:>6} | {s['llama_cpu']!s:>9} | {s['llama_rss']!s}"
      )
    if len(self.samples) > limit:
      print(f"... ({len(self.samples) - limit} more samples)")


def _fresh_brain(llm: OllamaClient, tag: str) -> BrainService:
  path = Path(database_path()).parent / f"root_cause_{tag}.db"
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


def _measure_ttft(
  brain: BrainService,
  text: str,
  *,
  on_first_chunk=None,
  chunk_min: int = 16,
  chunk_max: int = 100,
) -> dict:
  first_token: list[float] = []
  first_chunk: list[float] = []
  chunker = TextChunker(min_chars=chunk_min, max_chars=chunk_max)
  bus = brain._streamer._event_bus  # noqa: SLF001

  def on_token(payload: dict) -> None:
    token = str(payload.get("token", ""))
    if not token:
      return
    if not first_token:
      first_token.append(time.perf_counter())
    for sentence in chunker.push(token):
      if not first_chunk:
        first_chunk.append(time.perf_counter())
        if on_first_chunk is not None:
          on_first_chunk(sentence)

  def on_complete(payload: dict) -> None:
    del payload
    for sentence in chunker.flush():
      if not first_chunk:
        first_chunk.append(time.perf_counter())
        if on_first_chunk is not None:
          on_first_chunk(sentence)

  bus.subscribe(TOPIC_TOKEN, on_token)
  bus.subscribe(TOPIC_COMPLETE, on_complete)
  t0 = time.perf_counter()
  try:
    brain.send_message(text, voice=True, max_tokens=64)
  finally:
    bus.unsubscribe(TOPIC_TOKEN, on_token)
    bus.unsubscribe(TOPIC_COMPLETE, on_complete)
  done = time.perf_counter()
  return {
    "ttft": (first_token[0] - t0) if first_token else None,
    "chunk": (first_chunk[0] - first_token[0]) if first_token and first_chunk else None,
    "total": done - t0,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Kokoro vs LLM TTFT root-cause suite")
  parser.add_argument("--full", action="store_true", help="Include 3x live mic full pipeline")
  parser.add_argument("--skip-g", action="store_true", help="Skip STT+Kokoro without LLM")
  args = parser.parse_args()

  settings = load_settings()
  llm = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
    keep_alive=settings.ollama.keep_alive,
  )
  assert llm.is_available(), "Ollama not available"
  # Warm llama
  list(
    llm.chat_stream(
      [{"role": "user", "content": "ok"}],
      options={"num_predict": 4, "temperature": 0.0},
    )
  )

  rows: list[tuple[str, float | None, str]] = []
  mon = ResourceMonitor(0.25)

  print("=" * 64)
  print("PHASE 2.2 ROOT-CAUSE EXPERIMENT")
  print("=" * 64)
  print(f"Model: {settings.ollama.model}")
  print(f"Baseline resources: {snapshot_resources()}")
  print()

  # ---------- TEST A ----------
  print("TEST A — Brain baseline (no STT/TTS)")
  mon.start()
  mon.set_stage("brain")
  brain = _fresh_brain(llm, "a")
  m = _measure_ttft(brain, TRANSCRIPT)
  mon.stop()
  print(f"  TTFT={_fmt(m['ttft'])} total={_fmt(m['total'])}")
  rows.append(("A Brain only", m["ttft"], snapshot_resources().__repr__()))
  mon.print_timeline(12)
  print()

  # ---------- TEST B ----------
  print("TEST B — Kokoro loaded + warmed, NOT synthesizing")
  audio = AudioStream(sample_rate=settings.voice.sample_rate)
  tts = TextToSpeech(
    KokoroEngine(voice=settings.voice.tts_voice, lang_code=settings.voice.tts_lang),
    audio,
  )
  tts.warm_up()
  print(f"  resources after Kokoro warm: {snapshot_resources()}")
  mon.start()
  mon.set_stage("llm_kokoro_idle")
  brain = _fresh_brain(llm, "b")
  m = _measure_ttft(brain, TRANSCRIPT)
  mon.stop()
  print(f"  TTFT={_fmt(m['ttft'])} total={_fmt(m['total'])}")
  rows.append(("B Kokoro loaded idle", m["ttft"], ""))
  print()

  # ---------- TEST C ----------
  print("TEST C — TTS starts AFTER first sentence chunk (during stream)")
  synth_started = {"t": None, "done": None}

  def on_chunk(sentence: str) -> None:
    if synth_started["t"] is not None:
      return
    synth_started["t"] = time.perf_counter()
    mon.set_stage("tts_synth")
    # Synthesize in-thread (same as production worker contention)
    _ = tts.synthesize_chunks(sentence)
    synth_started["done"] = time.perf_counter()

  mon.start()
  mon.set_stage("llm_stream")
  brain = _fresh_brain(llm, "c")
  m = _measure_ttft(brain, TRANSCRIPT, on_first_chunk=on_chunk)
  mon.stop()
  print(f"  TTFT={_fmt(m['ttft'])} (TTS must not precede first token)")
  if synth_started["t"] and m["ttft"] is not None:
    # Prove TTS started after first token path
    print(f"  first_chunk_latency={_fmt(m['chunk'])}")
    print(f"  tts_synth_dur={_fmt((synth_started['done'] or 0) - (synth_started['t'] or 0))}")
  rows.append(("C Kokoro after first chunk", m["ttft"], ""))
  mon.print_timeline(16)
  print()

  # ---------- TEST F (limited threads) ----------
  print("TEST F — Brain + Kokoro idle with llm_cpu_priority (limited threads)")
  mon.start()
  mon.set_stage("llm_guarded")
  brain = _fresh_brain(llm, "f")
  with llm_cpu_priority(torch_threads=1, ct2_threads=1):
    m = _measure_ttft(brain, TRANSCRIPT)
  mon.stop()
  print(f"  TTFT={_fmt(m['ttft'])}")
  rows.append(("F Kokoro idle + CPU guard", m["ttft"], ""))
  print()

  # ---------- TEST H ----------
  print("TEST H — Fixed transcript → LLM → Kokoro (no STT)")
  mon.start()
  mon.set_stage("llm")
  brain = _fresh_brain(llm, "h")
  first_sentence: list[str] = []

  def capture(sentence: str) -> None:
    if not first_sentence:
      first_sentence.append(sentence)

  m = _measure_ttft(brain, TRANSCRIPT, on_first_chunk=capture)
  ttft_h = m["ttft"]
  mon.set_stage("tts")
  t0 = time.perf_counter()
  if first_sentence:
    _ = tts.synthesize_chunks(first_sentence[0])
  tts_s = time.perf_counter() - t0
  mon.stop()
  print(f"  TTFT={_fmt(ttft_h)} TTS_first={_fmt(tts_s)}")
  rows.append(("H Brain+Kokoro no STT", ttft_h, ""))
  print()

  # ---------- STT + Brain (no TTS synth) ----------
  print("TEST — STT then Brain (Whisper loaded, Kokoro idle)")
  stt = SpeechToText(
    WhisperEngine(
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    ),
    language=settings.voice.language,
  )
  stt.warm_up()
  sample = np.zeros(int(16000 * 1.2), dtype="float32")
  sample[1000:14000] = 0.08 * np.sin(2 * np.pi * 180 * np.arange(13000) / 16000)
  mon.start()
  mon.set_stage("stt")
  t0 = time.perf_counter()
  _ = stt.transcribe(sample)
  stt_s = time.perf_counter() - t0
  mon.set_stage("llm")
  brain = _fresh_brain(llm, "stt_brain")
  with llm_cpu_priority():
    m = _measure_ttft(brain, TRANSCRIPT)
  mon.stop()
  print(f"  STT={_fmt(stt_s)} TTFT={_fmt(m['ttft'])}")
  rows.append(("STT + Brain", m["ttft"], ""))
  print()

  # ---------- TEST G ----------
  if not args.skip_g:
    print("TEST G — STT + Kokoro, NO LLM")
    mon.start()
    mon.set_stage("stt")
    t0 = time.perf_counter()
    _ = stt.transcribe(sample)
    stt_s = time.perf_counter() - t0
    mon.set_stage("tts")
    t1 = time.perf_counter()
    _ = tts.synthesize_chunks("Good morning. I'm Maira.")
    tts_s = time.perf_counter() - t1
    mon.stop()
    print(f"  STT={_fmt(stt_s)} TTS={_fmt(tts_s)} resources={snapshot_resources()}")
    rows.append(("G STT+Kokoro no LLM", None, f"stt={stt_s:.2f} tts={tts_s:.2f}"))
    mon.print_timeline(20)
    print()

  # ---------- TEST D ----------
  if args.full:
    print("TEST D — Full live pipeline x3 (you must speak)")
    from scripts.benchmark_voice_live import _build_stack, run_live, _print_live

    stack = _build_stack(settings, playback=True)
    stack["stt"].warm_up()
    stack["tts"].warm_up()
    list(
      stack["llm"].chat_stream(
        [{"role": "user", "content": "ok"}],
        options={"num_predict": 2, "temperature": 0.0},
      )
    )
    for i in range(3):
      print(f"\n--- Live run {i + 1}/3 ---")
      print("Say a short sentence after the microphone starts.")
      mon.start()
      mon.set_stage("live")
      try:
        result = run_live(stack, settings, silence=settings.voice.silence_seconds)
        _print_live(result)
        rows.append((f"D Full live #{i + 1}", result.get("llm_ttft_s"), ""))
      except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        rows.append((f"D Full live #{i + 1}", None, str(exc)))
      finally:
        mon.stop()
    try:
      stack["llm"].close()
      stack["storage"].close()
    except Exception:  # noqa: BLE001
      pass

  # ---------- TABLE ----------
  print()
  print("=" * 64)
  print("SUMMARY TABLE")
  print("=" * 64)
  print(f"{'Test':<32} {'TTFT':>8}")
  print("-" * 42)
  for name, ttft, _note in rows:
    print(f"{name:<32} {_fmt(ttft):>8}")

  # Interpretation hint (measurements decide)
  loaded = next((r[1] for r in rows if r[0].startswith("B ")), None)
  active = next((r[1] for r in rows if r[0].startswith("C ")), None)
  baseline = next((r[1] for r in rows if r[0].startswith("A ")), None)
  print()
  print("INTERPRETATION HINT (from this run):")
  if baseline and loaded and active:
    if loaded <= (baseline + 0.4) and active <= (baseline + 0.4):
      print("  Kokoro idle AND synthesizing ≈ baseline → Kokoro NOT the TTFT cause.")
    elif loaded > (baseline + 1.5):
      print("  Kokoro LOADED alone inflated TTFT → resident resource pressure.")
    elif active > (baseline + 1.5) and loaded <= (baseline + 0.4):
      print("  Active Kokoro synth inflated path → TTS CPU contention (post-chunk).")
    else:
      print("  Mixed result — inspect timelines above.")
  print()
  print("Write findings to docs/PHASE2_2_ROOT_CAUSE.md after reviewing numbers.")

  llm.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
