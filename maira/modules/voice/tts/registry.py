"""TTS provider registry — select by config name."""

from __future__ import annotations

import os
from typing import Callable

from maira.core.interfaces.speech_providers import TTSProvider
from maira.modules.voice.download_guard import ModelDownloadBlocked, unavailable_message

_REGISTRY: dict[str, Callable[..., TTSProvider]] = {}

# Approximate download sizes (GB) for policy enforcement.
PROVIDER_SIZE_GB = {
  "kokoro": 0.35,
  "sarvam": 0.0,  # cloud API — no local download
  "indic_parler": 3.75,
  "veena": 7.5,
  "chatterbox": 3.0,
}


def register_tts(name: str, factory: Callable[..., TTSProvider]) -> None:
  _REGISTRY[name] = factory


def available_tts_names() -> list[str]:
  return sorted(_REGISTRY)


def create_tts(name: str, **kwargs) -> TTSProvider:
  if name not in _REGISTRY:
    raise KeyError(f"Unknown TTS provider: {name}. Known: {available_tts_names()}")
  return _REGISTRY[name](**kwargs)


class UnavailableTTS(TTSProvider):
  def __init__(self, name: str, reason: str) -> None:
    self._name = name
    self._reason = reason

  def get_provider_name(self) -> str:
    return self._name

  def is_available(self) -> tuple[bool, str]:
    return False, self._reason

  def synthesize(self, text: str):
    raise RuntimeError(self._reason)


def _build_kokoro(
  *,
  voice: str = "af_heart",
  lang_code: str = "a",
  allow_fallback: bool = False,
  max_model_download_gb: float = 1.0,
  **_kwargs,
) -> TTSProvider:
  from maira.modules.voice.download_guard import assert_download_allowed
  from maira.infrastructure.speech.kokoro.engine import KokoroEngine
  from maira.modules.voice.tts.kokoro_provider import KokoroTTSProvider

  try:
    assert_download_allowed(
      estimated_gb=PROVIDER_SIZE_GB["kokoro"],
      max_gb=max_model_download_gb,
      provider="kokoro",
      allow=False,
    )
    engine = KokoroEngine(voice=voice, lang_code=lang_code, allow_fallback=allow_fallback)
    return KokoroTTSProvider(engine)
  except ModelDownloadBlocked as exc:
    return UnavailableTTS("kokoro", str(exc))
  except Exception as exc:  # noqa: BLE001
    return UnavailableTTS("kokoro", f"Kokoro unavailable: {exc}")


def _build_sarvam(**_kwargs) -> TTSProvider:
  from maira.modules.voice.tts.sarvam_provider import SarvamTTSProvider

  return SarvamTTSProvider(api_key=os.environ.get("SARVAM_API_KEY", ""))


def _blocked_heavy(name: str, max_model_download_gb: float = 1.0, **_kwargs) -> TTSProvider:
  gb = PROVIDER_SIZE_GB.get(name, 3.0)
  return UnavailableTTS(
    name,
    unavailable_message(estimated_gb=gb, max_gb=max_model_download_gb, provider=name),
  )


# Installed with scripts/setup_voice.py into voice_envs/<name>; the user opts in there.
WORKER_DEFAULT_RATES = {"chatterbox": 24000, "indic_parler": 44100}


def _build_worker(
  name: str,
  *,
  device: str = "auto",
  language: str = "auto",
  reference_audio: str = "",
  speaker: str = "Divya",
  exaggeration: float = 0.5,
  **_kwargs,
) -> TTSProvider:
  from maira.infrastructure.speech.worker.engine import WorkerTTSEngine
  from maira.modules.voice.tts.worker_provider import WorkerTTSProvider
  from maira.modules.voice.voice_tools import engine_options

  options = engine_options(
    name,
    {
      "device": device,
      "language": language,
      "reference_audio": reference_audio,
      "speaker": speaker,
      "exaggeration": exaggeration,
    },
  )
  engine = WorkerTTSEngine(name, options=options, default_sample_rate=WORKER_DEFAULT_RATES[name])
  return WorkerTTSProvider(name, engine)


def ensure_default_tts_providers() -> None:
  if "kokoro" not in _REGISTRY:
    register_tts("kokoro", _build_kokoro)
  if "sarvam" not in _REGISTRY:
    register_tts("sarvam", _build_sarvam)
  for name in ("chatterbox", "indic_parler"):
    if name not in _REGISTRY:
      register_tts(name, lambda name=name, **kw: _build_worker(name, **kw))
  for heavy in ("veena",):
    if heavy not in _REGISTRY:
      register_tts(heavy, lambda name=heavy, **kw: _blocked_heavy(name, **kw))


ensure_default_tts_providers()
