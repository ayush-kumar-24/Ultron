"""Always-on-top floating Ultron orb — nested diamond, state-colored bloom."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
  QColor,
  QMouseEvent,
  QPainter,
  QPainterPath,
  QPaintEvent,
  QPen,
  QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from maira.modules.presence.state import PresenceState

_STATE_COLOR = {
  PresenceState.READY: QColor("#C8C8D4"),
  PresenceState.LISTENING: QColor("#6AA6F8"),
  PresenceState.THINKING: QColor("#A78BFA"),
  PresenceState.WORKING: QColor("#F0A35E"),
  PresenceState.RECORDING: QColor("#F87171"),
  PresenceState.WAITING_PERMISSION: QColor("#EAC35B"),
  PresenceState.ERROR: QColor("#E0655F"),
}

_SIZE = 72
_DRAG_THRESHOLD = 6


def _diamond(cx: float, cy: float, half: float) -> QPainterPath:
  path = QPainterPath()
  path.moveTo(cx, cy - half)
  path.lineTo(cx + half, cy)
  path.lineTo(cx, cy + half)
  path.lineTo(cx - half, cy)
  path.closeSubpath()
  return path


class OrbWidget(QWidget):
  clicked = Signal()

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self._state = PresenceState.READY
    self._press_pos = QPoint()
    self._dragged = False
    self.setFixedSize(_SIZE, _SIZE)
    self.setWindowFlags(
      Qt.WindowType.FramelessWindowHint
      | Qt.WindowType.WindowStaysOnTopHint
      | Qt.WindowType.Tool
      | Qt.WindowType.NoDropShadowWindowHint
    )
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    self.setCursor(Qt.CursorShape.OpenHandCursor)
    self.setToolTip("Ultron")

  def presence_state(self) -> PresenceState:
    return self._state

  def set_presence_state(self, state: PresenceState) -> None:
    if state is self._state:
      return
    self._state = state
    self.setToolTip(f"Ultron — {state.value.replace('_', ' ')}")
    self.update()

  def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = self.width() / 2
    cy = self.height() / 2
    color = _STATE_COLOR[self._state]

    bloom = QRadialGradient(cx, cy, _SIZE * 0.48)
    glow = QColor(color)
    glow.setAlpha(70)
    bloom.setColorAt(0.0, glow)
    bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bloom)
    painter.drawEllipse(QPoint(int(cx), int(cy)), int(_SIZE * 0.46), int(_SIZE * 0.46))

    outer = _diamond(cx, cy, 22)
    fill = QColor(12, 12, 16, 210)
    painter.setBrush(fill)
    edge = QPen(color)
    edge.setWidthF(1.8)
    painter.setPen(edge)
    painter.drawPath(outer)

    inner = _diamond(cx, cy, 11)
    inner_pen = QPen(QColor(color.red(), color.green(), color.blue(), 170))
    inner_pen.setWidthF(1.2)
    painter.setPen(inner_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(inner)

    core = QColor(color)
    core.setAlpha(220)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(core)
    painter.drawEllipse(QPoint(int(cx), int(cy)), 3, 3)

  def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self._press_pos = event.globalPosition().toPoint()
      self._dragged = False
      self.setCursor(Qt.CursorShape.ClosedHandCursor)
    super().mousePressEvent(event)

  def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
    if event.buttons() & Qt.MouseButton.LeftButton:
      now = event.globalPosition().toPoint()
      delta = now - self._press_pos
      if delta.manhattanLength() >= _DRAG_THRESHOLD:
        self._dragged = True
        self.move(self.pos() + delta)
        self._press_pos = now
    super().mouseMoveEvent(event)

  def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
    self.setCursor(Qt.CursorShape.OpenHandCursor)
    if event.button() == Qt.MouseButton.LeftButton and not self._dragged:
      self.clicked.emit()
    super().mouseReleaseEvent(event)
