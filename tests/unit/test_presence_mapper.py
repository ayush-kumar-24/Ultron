"""Presence event mapping — no Qt required."""

from maira.modules.presence.mapper import apply_presence_event
from maira.modules.presence.state import PresenceState


def test_voice_listening_maps_to_listening() -> None:
  state = apply_presence_event(
    "voice.status", {"status": "listening"}, PresenceState.READY
  )
  assert state is PresenceState.LISTENING


def test_brain_token_maps_to_thinking() -> None:
  state = apply_presence_event("brain.token", {"token": "Hi"}, PresenceState.READY)
  assert state is PresenceState.THINKING


def test_brain_complete_returns_to_ready() -> None:
  state = apply_presence_event(
    "brain.complete", {"content": "done"}, PresenceState.THINKING
  )
  assert state is PresenceState.READY


def test_voice_error_maps_to_error() -> None:
  state = apply_presence_event(
    "voice.error", {"message": "mic"}, PresenceState.LISTENING
  )
  assert state is PresenceState.ERROR


def test_desktop_failure_maps_to_error() -> None:
  state = apply_presence_event("desktop.ran", {"ok": False}, PresenceState.READY)
  assert state is PresenceState.ERROR


def test_unknown_topic_keeps_current_state() -> None:
  state = apply_presence_event("unrelated", {}, PresenceState.WORKING)
  assert state is PresenceState.WORKING


def test_screen_reading_maps_to_working() -> None:
  state = apply_presence_event("screen.reading", {}, PresenceState.READY)
  assert state is PresenceState.WORKING


def test_screen_read_returns_to_ready() -> None:
  state = apply_presence_event("screen.read", {"ok": True}, PresenceState.WORKING)
  assert state is PresenceState.READY


def test_screen_error_maps_to_error() -> None:
  state = apply_presence_event("screen.error", {"message": "no display"}, PresenceState.WORKING)
  assert state is PresenceState.ERROR
