"""STT provider registry — select by config name."""

from __future__ import annotations

from typing import Callable

from maira.core.interfaces.speech_providers import STTProvider
from maira.modules.voice.download_guard import ModelDownloadBlocked

_REGISTRY: dict[str, Callable[..., STTProvider]] = {}


def register_stt(name: str, factory: Callable[..., STTProvider]) -> None:
  _REGISTRY[name] = factory


def available_stt_names() -> list[str]:
  return sorted(_REGISTRY)


def create_stt(name: str, **kwargs) -> STTProvider:
  if name not in _REGISTRY:
    raise KeyError(f"Unknown STT provider: {name}. Known: {available_stt_names()}")
  return _REGISTRY[name](**kwargs)


class UnavailableSTT(STTProvider):
  def __init__(self, name: str, reason: str) -> None:
    self._name = name
    self._reason = reason

  def get_provider_name(self) -> str:
    return self._name

  def is_available(self) -> tuple[bool, str]:
    return False, self._reason

  def transcribe(self, audio) -> str:
    raise RuntimeError(self._reason)


def _build_faster_whisper(
  *,
  model_size: str = "base",
  device: str = "cpu",
  compute_type: str = "int8",
  language: str | None = None,
  max_model_download_gb: float = 1.0,
  beam_size: int = 5,
  vad_filter: bool = True,
  **_kwargs,
) -> STTProvider:
  # tiny/base/small are within typical 1GB policy; larger sizes refused unless already local.
  size_estimates = {
    "tiny": 0.08,
    "tiny.en": 0.08,
    "base": 0.15,
    "base.en": 0.15,
    "small": 0.5,
    "small.en": 0.5,
    "medium": 1.5,
    "medium.en": 1.5,
    "large-v3": 3.0,
    "large-v2": 3.0,
  }
  estimated = size_estimates.get(model_size, 1.5)
  try:
    from maira.modules.voice.download_guard import assert_download_allowed
    from maira.infrastructure.speech.whisper.engine import WhisperEngine
    from maira.modules.voice.stt.faster_whisper_provider import FasterWhisperSTT

    # Allow if already loadable; WhisperEngine doesn't auto-download huge models in our setup.
    if estimated > max_model_download_gb and model_size.startswith("large"):
      assert_download_allowed(
        estimated_gb=estimated,
        max_gb=max_model_download_gb,
        provider=f"faster_whisper/{model_size}",
        allow=False,
      )
    engine = WhisperEngine(
      model_size=model_size,
      device=device,
      compute_type=compute_type,
      beam_size=beam_size,
      vad_filter=vad_filter,
    )
    return FasterWhisperSTT(engine, language=language)
  except ModelDownloadBlocked as exc:
    return UnavailableSTT("faster_whisper", str(exc))
  except Exception as exc:  # noqa: BLE001
    return UnavailableSTT("faster_whisper", f"STT unavailable: {exc}")


def ensure_default_stt_providers() -> None:
  if "faster_whisper" not in _REGISTRY:
    register_stt("faster_whisper", _build_faster_whisper)
  if "whisper" not in _REGISTRY:
    register_stt("whisper", _build_faster_whisper)


ensure_default_stt_providers()
