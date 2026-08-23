"""Deprecated popup voice overlay — voice now lives inline in Chat.

Kept as a no-op stub so old imports do not break during prototype iteration.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class VoiceOverlay(QWidget):
  closed = Signal()

  def open(self, start: str = "Listening...") -> None:
    del start
    # No popup — intentionally empty

  def close_overlay(self) -> None:
    self.closed.emit()

  def set_state(self, state: str) -> None:
    del state

  def isVisible(self) -> bool:  # noqa: N802
    return False
