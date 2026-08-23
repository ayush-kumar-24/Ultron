"""Provider registry for the Voice Comparison Lab."""

from __future__ import annotations

from voice_lab.providers.base import TTSProvider
from voice_lab.providers.chatterbox_provider import ChatterboxProvider
from voice_lab.providers.indic_parler_provider import IndicParlerProvider
from voice_lab.providers.kokoro_provider import KokoroProvider
from voice_lab.providers.veena_provider import VeenaProvider


def all_providers() -> list[TTSProvider]:
  """Kokoro default, then Indic open voices, then optional Chatterbox."""
  return [
    KokoroProvider(),
    IndicParlerProvider(),
    VeenaProvider(),
    ChatterboxProvider(),
  ]


__all__ = [
  "TTSProvider",
  "KokoroProvider",
  "IndicParlerProvider",
  "VeenaProvider",
  "ChatterboxProvider",
  "all_providers",
]
