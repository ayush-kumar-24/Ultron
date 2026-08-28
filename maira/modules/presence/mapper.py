"""Map event-bus topics onto PresenceState. Pure logic — no Qt."""

from __future__ import annotations

from typing import Any

from maira.modules.presence.state import PresenceState

_VOICE_STATUS_MAP = {
  "idle": PresenceState.READY,
  "listening": PresenceState.LISTENING,
  "transcribing": PresenceState.THINKING,
  "thinking": PresenceState.THINKING,
  "processing": PresenceState.THINKING,
  "speaking": PresenceState.WORKING,
  "interrupted": PresenceState.READY,
  "error": PresenceState.ERROR,
  "recording": PresenceState.RECORDING,
}


def apply_presence_event(
  topic: str,
  payload: Any,
  current: PresenceState,
) -> PresenceState:
  data = payload if isinstance(payload, dict) else {}

  if topic == "voice.status":
    status = str(data.get("status", "")).lower()
    return _VOICE_STATUS_MAP.get(status, current)

  if topic in {"voice.error", "brain.error"}:
    return PresenceState.ERROR

  if topic == "brain.token":
    return PresenceState.THINKING

  if topic == "brain.complete":
    return PresenceState.READY

  if topic == "desktop.ran":
    if data.get("ok") is False:
      return PresenceState.ERROR
    return PresenceState.READY

  # Screen vision: looking is work, and the user should see that it happened.
  if topic == "screen.reading":
    return PresenceState.WORKING

  if topic == "screen.read":
    if data.get("ok") is False:
      return PresenceState.ERROR
    return PresenceState.READY

  if topic == "screen.error":
    return PresenceState.ERROR

  return current
