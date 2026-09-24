"""Voice helpers for the Settings screen: install status, preview and system checks."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from loguru import logger

from maira.infrastructure.speech.worker.engine import WorkerTTSEngine, voice_env_python

INSTALLABLE = ("chatterbox", "indic_parler")
PREVIEW_TEXT = "Hello Ayush, main Ultron hoon. Aaj aapke do tasks hain."


def is_installed(provider: str) -> bool:
  if provider == "kokoro":
    import importlib.util  # noqa: PLC0415

    return importlib.util.find_spec("kokoro") is not None
  return voice_env_python(provider).exists()


def install_command(provider: str) -> list[str]:
  """Command the Settings screen runs (in the background) to install a voice."""
  return [sys.executable, "-u", "-m", "scripts.setup_voice", provider]


def engine_options(provider: str, values: dict) -> dict:
  """Options for WorkerTTSEngine from Settings values (voice.tts.*)."""
  options = {"device": values.get("device") or "auto"}
  if provider == "chatterbox":
    options["language"] = values.get("language") or "auto"
    options["exaggeration"] = float(values.get("exaggeration") or 0.5)
    if values.get("reference_audio"):
      options["reference_audio"] = values["reference_audio"]
  elif provider == "indic_parler":
    options["speaker"] = values.get("speaker") or "Divya"
  return options


@dataclass(frozen=True)
class PreviewResult:
  ok: bool
  message: str


class VoicePreviewer:
  """Speaks a sample with any voice without changing Ultron's current voice.

  Engines stay loaded between previews (the first load is slow) and are
  closed when Ultron quits.
  """

  def __init__(self) -> None:
    self._lock = threading.Lock()
    self._engines: dict[tuple, object] = {}

  def preview(self, provider: str, values: dict, text: str = PREVIEW_TEXT) -> PreviewResult:
    with self._lock:
      try:
        engine = self._engine(provider, values)
        started = time.time()
        chunks = [c for c in engine.synthesize_stream(text) if c is not None and len(c)]
        took = time.time() - started
        if not chunks:
          return PreviewResult(False, "The voice produced no audio for this text.")
        import numpy as np  # noqa: PLC0415
        import sounddevice as sd  # noqa: PLC0415

        audio = np.concatenate(chunks)
        sd.play(audio, samplerate=engine.sample_rate)
        sd.wait()
        seconds = len(audio) / engine.sample_rate
        where = getattr(engine, "device", "")
        speed = f"{seconds / took:.1f}x real time" if took > 0 else ""
        return PreviewResult(True, f"Played {seconds:.1f}s of audio{f' on {where}' if where and where != '?' else ''} · {speed}")
      except Exception as exc:  # noqa: BLE001
        logger.exception("Voice preview failed")
        return PreviewResult(False, f"Preview failed: {exc}")

  def _engine(self, provider: str, values: dict):
    if provider == "kokoro":
      if not is_installed("kokoro"):
        raise RuntimeError('Kokoro is not installed. Run: pip install -e ".[voice]"')
      voice = values.get("voice") or "af_heart"
      key = ("kokoro", voice)
      if key not in self._engines:
        from maira.infrastructure.speech.kokoro.engine import KokoroEngine  # noqa: PLC0415

        self._engines[key] = KokoroEngine(voice=voice, sample_rate=24000, lang_code=voice[:1] or "a")
      return self._engines[key]
    if not is_installed(provider):
      raise RuntimeError(f"{provider} is not installed yet — click Install first.")
    options = engine_options(provider, values)
    key = (provider, tuple(sorted(options.items())))
    if key not in self._engines:
      # One worker per voice: drop the previous engine of this provider.
      for old_key in [k for k in self._engines if k[0] == provider]:
        self._close(self._engines.pop(old_key))
      self._engines[key] = WorkerTTSEngine(provider, options=options)
    return self._engines[key]

  def close(self) -> None:
    with self._lock:
      for engine in self._engines.values():
        self._close(engine)
      self._engines.clear()

  @staticmethod
  def _close(engine) -> None:
    close = getattr(engine, "close", None)
    if callable(close):
      close()


def ollama_models(host: str, timeout: float = 2.0) -> list[str] | None:
  """Installed Ollama models, or None if Ollama is not reachable."""
  try:
    import httpx  # noqa: PLC0415

    response = httpx.get(host.rstrip("/") + "/api/tags", timeout=timeout)
    response.raise_for_status()
    return sorted(m.get("name", "") for m in response.json().get("models", []) if m.get("name"))
  except Exception:  # noqa: BLE001
    return None
