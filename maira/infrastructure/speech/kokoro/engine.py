"""Offline TTS engine — Kokoro is the shipped default for Maira on PC."""

from __future__ import annotations

import tempfile
import wave
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

KOKORO_REPO_ID = "hexgrad/Kokoro-82M"
_WARMUP_PHRASE = "Ready."


class KokoroEngine:
  """Kokoro TTS (default). Optional pyttsx3 only when allow_fallback=True."""

  def __init__(
    self,
    voice: str = "af_heart",
    sample_rate: int = 24000,
    *,
    lang_code: str = "a",
    allow_fallback: bool = False,
  ) -> None:
    self._voice = voice
    self._sample_rate = sample_rate
    self._lang_code = lang_code
    self._allow_fallback = allow_fallback
    self._kokoro = None
    self._pyttsx3 = None
    self._backend = "none"
    self._failed = False
    self._voice_warmed = False

  @property
  def sample_rate(self) -> int:
    return self._sample_rate

  @property
  def backend(self) -> str:
    return self._backend

  def is_available(self) -> bool:
    if self._failed:
      return False
    try:
      import kokoro  # noqa: F401

      return True
    except Exception as exc:  # noqa: BLE001
      if self._allow_fallback:
        try:
          import pyttsx3  # noqa: F401

          return True
        except Exception:
          pass
      logger.warning(
        "Kokoro TTS unavailable ({}). Install with: pip install -e \".[voice]\"",
        exc,
      )
      self._failed = True
      return False

  def warm_up(self, *, synthesize: bool = True) -> None:
    """Load pipeline once; optionally synth a tiny phrase to warm the voice pack."""
    if not self.is_available():
      return
    self._ensure_backend()
    if not synthesize or self._voice_warmed or self._backend != "kokoro":
      return
    # Discarded warm synthesis — loads voice pack into KPipeline.voices cache.
    for _ in self._stream_kokoro(_WARMUP_PHRASE):
      pass
    self._voice_warmed = True
    logger.info("Kokoro voice '{}' warmed", self._voice)

  def synthesize(self, text: str):
    """Return (audio_float32_numpy, sample_rate)."""
    import numpy as np

    chunks = list(self.synthesize_stream(text))
    if not chunks:
      return np.zeros(0, dtype="float32"), self._sample_rate
    return np.concatenate(chunks), self._sample_rate

  def synthesize_stream(self, text: str) -> Iterator:
    """Yield audio chunks as soon as each is ready (faster perceived TTS)."""
    cleaned = text.strip()
    if not cleaned:
      return

    self._ensure_backend()
    if self._backend == "kokoro":
      yield from self._stream_kokoro(cleaned)
      return
    if self._backend == "pyttsx3":
      audio, _rate = self._synthesize_pyttsx3(cleaned)
      if len(audio):
        yield audio
      return
    raise RuntimeError("No TTS backend available")

  def _ensure_backend(self) -> None:
    if self._backend != "none":
      return
    try:
      from kokoro import KPipeline  # type: ignore

      self._kokoro = KPipeline(lang_code=self._lang_code, repo_id=KOKORO_REPO_ID)
      self._backend = "kokoro"
      logger.info("Using Kokoro TTS voice '{}' (PC default)", self._voice)
      return
    except Exception as exc:  # noqa: BLE001
      if not self._allow_fallback:
        self._failed = True
        raise RuntimeError(
          f"Kokoro TTS is required but failed to load: {exc}. "
          'Install with: pip install -e ".[voice]"'
        ) from exc
      logger.warning("Kokoro not available ({}); using emergency system TTS", exc)

    try:
      import pyttsx3

      self._pyttsx3 = pyttsx3.init()
      self._backend = "pyttsx3"
      logger.warning("Using emergency system TTS (pyttsx3) — not the Maira default voice")
    except Exception as exc:  # noqa: BLE001
      self._failed = True
      raise RuntimeError("No TTS backend available") from exc

  def _stream_kokoro(self, text: str):
    import numpy as np

    assert self._kokoro is not None
    # Preload voice once so subsequent calls hit KPipeline.voices cache.
    if hasattr(self._kokoro, "load_voice"):
      try:
        self._kokoro.load_voice(self._voice)
      except Exception:  # noqa: BLE001
        pass
    for _graphemes, _phonemes, audio in self._kokoro(text, voice=self._voice):
      yield np.asarray(audio, dtype="float32")

  def _synthesize_pyttsx3(self, text: str):
    import numpy as np

    if self._pyttsx3 is None:
      import pyttsx3

      self._pyttsx3 = pyttsx3.init()

    engine = self._pyttsx3
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "maira_tts.wav"
      engine.save_to_file(text, str(path))
      engine.runAndWait()
      with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()

    if sample_width == 2:
      audio = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
    else:
      audio = np.frombuffer(frames, dtype=np.uint8).astype("float32")
      audio = (audio - 128.0) / 128.0

    if channels > 1:
      audio = audio.reshape(-1, channels).mean(axis=1)
    self._sample_rate = rate
    return audio.astype("float32", copy=False), rate
