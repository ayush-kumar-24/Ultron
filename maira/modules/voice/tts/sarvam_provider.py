"""Optional Sarvam cloud TTS — never required; no hardcoded API key."""

from __future__ import annotations

from typing import Any

from maira.core.interfaces.speech_providers import TTSProvider


class SarvamTTSProvider(TTSProvider):
  def __init__(self, api_key: str = "") -> None:
    self._api_key = (api_key or "").strip()

  def get_provider_name(self) -> str:
    return "sarvam"

  def is_available(self) -> tuple[bool, str]:
    if not self._api_key:
      return False, "SARVAM_API_KEY not configured (optional cloud provider)"
    return True, "configured (optional)"

  def synthesize(self, text: str) -> tuple[Any, int]:
    raise RuntimeError(
      "Sarvam TTS is optional and not wired for offline Ultron. "
      "Use Kokoro for local speech."
    )
