"""App side of the TTS worker: same interface as KokoroEngine, audio from a child process."""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from maira.shared.utils.paths import project_root

WORKER_SCRIPT = Path(__file__).with_name("tts_worker.py")
# First start downloads the model (GBs) and loads it; generous on purpose.
READY_TIMEOUT_S = 30 * 60
SYNTH_TIMEOUT_S = 180
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+|\n+")
_MAX_CHARS = 220  # long text is split so the first audio arrives sooner


def voice_env_dir(name: str) -> Path:
  return project_root() / "voice_envs" / name


def voice_env_python(name: str, *, windows: bool | None = None) -> Path:
  base = voice_env_dir(name)
  windows = os.name == "nt" if windows is None else windows
  return base / "Scripts" / "python.exe" if windows else base / "bin" / "python"


def split_sentences(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
  parts: list[str] = []
  for sentence in _SENTENCE_END.split(text.strip()):
    sentence = sentence.strip()
    while len(sentence) > max_chars:
      cut = sentence.rfind(" ", 0, max_chars)
      cut = cut if cut > max_chars // 2 else max_chars
      parts.append(sentence[:cut].strip())
      sentence = sentence[cut:].strip()
    if sentence:
      parts.append(sentence)
  return parts


class WorkerTTSEngine:
  """Kokoro-compatible engine (is_available / warm_up / synthesize_stream / sample_rate)."""

  def __init__(
    self,
    engine: str,
    *,
    options: dict | None = None,
    python: Path | str | None = None,
    default_sample_rate: int = 24000,
  ) -> None:
    self._engine = engine
    self._options = dict(options or {})
    self._python = Path(python) if python else voice_env_python(engine)
    self._sample_rate = default_sample_rate
    self._process: subprocess.Popen | None = None
    self._ready = threading.Event()
    self._error: str | None = None
    self._start_lock = threading.Lock()
    self._request_lock = threading.Lock()
    self._responses: queue.Queue = queue.Queue()
    self._next_id = 0
    self._failed = False
    self.device = "?"

  @property
  def sample_rate(self) -> int:
    return self._sample_rate

  @property
  def backend(self) -> str:
    return self._engine

  def is_available(self) -> bool:
    return not self._failed and self._python.exists()

  def warm_up(self, *, synthesize: bool = True) -> None:
    del synthesize
    self._ensure_started()

  def synthesize(self, text: str):
    import numpy as np  # noqa: PLC0415

    chunks = list(self.synthesize_stream(text))
    if not chunks:
      return np.zeros(0, dtype="float32"), self._sample_rate
    return np.concatenate(chunks), self._sample_rate

  def synthesize_stream(self, text: str) -> Iterator:
    for sentence in split_sentences(text):
      audio = self._request(sentence)
      if audio is not None and len(audio):
        yield audio

  def close(self) -> None:
    process = self._process
    self._process = None
    if process is None:
      return
    try:
      if process.stdin:
        process.stdin.close()
      process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
      process.kill()

  # --- internals -------------------------------------------------------------------

  def _ensure_started(self) -> None:
    with self._start_lock:
      if self._process is not None and self._process.poll() is None and self._ready.is_set():
        return
      if self._failed:
        raise RuntimeError(self._error or f"{self._engine} voice failed to start")
      if not self._python.exists():
        self._failed = True
        raise RuntimeError(
          f"{self._engine} voice is not installed. Run: python -m scripts.setup_voice {self._engine}"
        )
      self._start()

  def _start(self) -> None:
    self._ready.clear()
    self._error = None
    logger.info("Starting {} voice (first start downloads and loads the model)...", self._engine)
    self._process = subprocess.Popen(  # noqa: S603
      [str(self._python), str(WORKER_SCRIPT)],
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,
      text=True,
      encoding="utf-8",
      bufsize=1,
      cwd=str(project_root()),
      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    threading.Thread(target=self._read_loop, args=(self._process,), name=f"ultron-tts-{self._engine}", daemon=True).start()
    self._send({"type": "init", "engine": self._engine, **self._options})
    if not self._ready.wait(READY_TIMEOUT_S) or self._error:
      self._failed = True
      reason = self._error or "timed out while loading"
      self.close()
      raise RuntimeError(f"{self._engine} voice failed to start: {reason}")
    logger.info("{} voice ready on {} ({} Hz)", self._engine, self.device, self._sample_rate)

  def _read_loop(self, process: subprocess.Popen) -> None:
    assert process.stdout is not None
    for line in process.stdout:
      try:
        message = json.loads(line)
      except json.JSONDecodeError:
        continue
      kind = message.get("type")
      if kind == "ready":
        self._sample_rate = int(message.get("sample_rate") or self._sample_rate)
        self.device = str(message.get("device") or "?")
        self._ready.set()
      elif kind == "error" and message.get("id") is None:
        self._error = str(message.get("message"))
        self._ready.set()
      else:
        self._responses.put(message)
    # Worker exited: wake anyone waiting.
    if not self._ready.is_set():
      self._error = self._error or "voice worker exited"
      self._ready.set()
    self._responses.put({"type": "error", "id": "*", "message": "voice worker exited"})

  def _send(self, message: dict) -> None:
    process = self._process
    if process is None or process.stdin is None:
      raise RuntimeError("voice worker not running")
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()

  def _request(self, text: str):
    import numpy as np  # noqa: PLC0415

    self._ensure_started()
    with self._request_lock:
      self._next_id += 1
      request_id = self._next_id
      self._send({"type": "synth", "id": request_id, "text": text})
      while True:
        try:
          message = self._responses.get(timeout=SYNTH_TIMEOUT_S)
        except queue.Empty as exc:
          raise RuntimeError(f"{self._engine} voice took too long") from exc
        if message.get("id") not in (request_id, "*"):
          continue  # stale reply from a cancelled request
        if message.get("type") == "audio":
          self._sample_rate = int(message.get("sample_rate") or self._sample_rate)
          return np.frombuffer(base64.b64decode(message["data"]), dtype="float32").copy()
        raise RuntimeError(str(message.get("message")))
