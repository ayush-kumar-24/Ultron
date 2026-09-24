"""Faster-Whisper engine wrapper for offline transcription."""

from __future__ import annotations

import importlib.util

import re

from loguru import logger

# Common Whisper hallucinations on silence / noise (especially tiny/base).
_HALLUCINATION_PATTERNS = re.compile(
  r"("
  r"thanks for watching|thank you for watching|subscribe|字幕|字幕志愿者|"
  r"please subscribe|see you next time|bye\.?$|"
  r"^you$|^the end\.?$|^thanks\.?$|^thank you\.?$|"
  r"mbc|시청|구독|다음 영상"
  r")",
  re.I,
)


class WhisperEngine:
  def __init__(
    self,
    model_size: str = "base.en",
    device: str = "cpu",
    compute_type: str = "int8",
    *,
    beam_size: int = 5,
    vad_filter: bool = True,
    no_speech_threshold: float = 0.6,
  ) -> None:
    self._model_size = model_size
    self._device = device
    self._compute_type = compute_type
    self._beam_size = max(1, beam_size)
    self._vad_filter = vad_filter
    self._no_speech_threshold = no_speech_threshold
    self._model = None
    self._failed = False

  def is_available(self) -> bool:
    if self._failed:
      return False
    try:
      # Check the install without importing (the import is slow; warm_up loads it).
      if importlib.util.find_spec("faster_whisper") is None:
        raise ImportError("No module named 'faster_whisper'")
      return True
    except Exception as exc:  # noqa: BLE001
      logger.warning("Whisper unavailable: {}", exc)
      self._failed = True
      return False

  def warm_up(self) -> None:
    """Load model ahead of the first user utterance; run a tiny decode to warm kernels."""
    if not self.is_available():
      return
    model = self._ensure_model()
    try:
      import numpy as np

      # Short tone — avoid silence which triggers hallucinations during warm-up.
      n = int(16000 * 0.4)
      t = np.arange(n, dtype="float32") / 16000.0
      tone = (0.05 * np.sin(2 * np.pi * 220 * t)).astype("float32")
      list(
        model.transcribe(
          tone,
          language="en",
          vad_filter=False,
          beam_size=1,
          best_of=1,
          temperature=0.0,
          without_timestamps=True,
        )[0]
      )
    except Exception as exc:  # noqa: BLE001
      logger.debug("Whisper warm decode skipped: {}", exc)

  def transcribe(self, audio, *, language: str | None = "en") -> str:
    """Transcribe a float32 mono waveform. Returns '' when speech is unclear."""
    import numpy as np

    if audio is None or len(audio) == 0:
      return ""

    model = self._ensure_model()
    waveform = np.asarray(audio, dtype="float32").reshape(-1)
    waveform = self._prepare_waveform(waveform)
    if waveform is None:
      return ""

    # Longer clips: VAD helps; very short PTT clips: skip VAD to avoid dropping speech.
    duration_s = len(waveform) / 16000.0
    use_vad = self._vad_filter and duration_s >= 1.0

    segments, info = model.transcribe(
      waveform,
      language=language,
      vad_filter=use_vad,
      beam_size=self._beam_size,
      best_of=self._beam_size,
      temperature=0.0,
      condition_on_previous_text=False,
      without_timestamps=True,
      no_speech_threshold=self._no_speech_threshold,
      compression_ratio_threshold=2.4,
      log_prob_threshold=-0.8,
    )

    parts: list[str] = []
    for segment in segments:
      text = (segment.text or "").strip()
      if not text:
        continue
      # Drop low-confidence segments when available
      avg_logprob = getattr(segment, "avg_logprob", None)
      no_speech_prob = getattr(segment, "no_speech_prob", None)
      if avg_logprob is not None and avg_logprob < -1.0:
        logger.debug("Dropping low-confidence STT segment: {!r} logprob={}", text, avg_logprob)
        continue
      if no_speech_prob is not None and no_speech_prob > 0.7:
        logger.debug("Dropping no-speech STT segment: {!r}", text)
        continue
      if self._looks_hallucinated(text):
        logger.info("[MAIRA STT] suppressed hallucination: {!r}", text)
        continue
      parts.append(text)

    text = " ".join(parts).strip()
    text = re.sub(r"\s+", " ", text)
    if self._looks_hallucinated(text):
      logger.info("[MAIRA STT] rejected hallucinated transcript: {!r}", text)
      return ""

    language_prob = getattr(info, "language_probability", None)
    if language_prob is not None and language_prob < 0.35 and text:
      logger.info("[MAIRA STT] low language confidence ({:.2f}): {!r}", language_prob, text)

    return text

  def _prepare_waveform(self, waveform):
    import numpy as np

    # Trim leading/trailing near-silence
    if len(waveform) < int(16000 * 0.25):
      return None
    abs_w = np.abs(waveform)
    threshold = max(0.008, float(np.percentile(abs_w, 60)) * 0.15)
    nonzero = np.where(abs_w > threshold)[0]
    if len(nonzero) == 0:
      return None
    start = max(0, int(nonzero[0]) - int(0.05 * 16000))
    end = min(len(waveform), int(nonzero[-1]) + int(0.15 * 16000))
    clipped = waveform[start:end]
    if len(clipped) < int(16000 * 0.2):
      return None

    # Peak normalize (helps quiet mics without clipping)
    peak = float(np.max(np.abs(clipped))) if len(clipped) else 0.0
    if peak < 0.004:
      return None
    if peak > 0 and peak < 0.25:
      clipped = clipped * (0.25 / peak)
    return np.clip(clipped, -1.0, 1.0).astype("float32", copy=False)

  @staticmethod
  def _looks_hallucinated(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
      return True
    if len(cleaned) < 2:
      return True
    if _HALLUCINATION_PATTERNS.search(cleaned):
      return True
    # Repeated character spam
    if len(set(cleaned.lower().replace(" ", ""))) <= 2 and len(cleaned) > 8:
      return True
    return False

  def _ensure_model(self):
    if self._model is not None:
      return self._model
    from faster_whisper import WhisperModel

    logger.info(
      "Loading Whisper model '{}' (device={}, compute={}, beam={})",
      self._model_size,
      self._device,
      self._compute_type,
      self._beam_size,
    )
    self._model = WhisperModel(
      self._model_size,
      device=self._device,
      compute_type=self._compute_type,
    )
    return self._model
