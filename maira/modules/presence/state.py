"""Orb / tray visual states from the Ultron vision."""

from enum import Enum


class PresenceState(str, Enum):
  READY = "ready"
  LISTENING = "listening"
  THINKING = "thinking"
  WORKING = "working"
  RECORDING = "recording"
  WAITING_PERMISSION = "waiting_permission"
  ERROR = "error"
