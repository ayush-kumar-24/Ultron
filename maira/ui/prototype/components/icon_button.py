"""Reusable icon button with hover/active glow."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from maira.ui.prototype.components.icons import draw_icon
from maira.ui.prototype.theme import tokens as t


class IconButton(QWidget):
  clicked = Signal()

  def __init__(
    self,
    icon: str,
    tooltip: str = "",
    size: int = 40,
    parent=None,
  ) -> None:
    super().__init__(parent)
    self._icon = icon
    self._active = False
    self._hovered = False
    self.setFixedSize(size, size)
    self.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
      self.setToolTip(tooltip)
    self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

  def set_active(self, active: bool) -> None:
    self._active = active
    self.update()

  def set_icon(self, icon: str) -> None:
    self._icon = icon
    self.update()

  def enterEvent(self, event) -> None:  # noqa: N802
    self._hovered = True
    self.update()
    super().enterEvent(event)

  def leaveEvent(self, event) -> None:  # noqa: N802
    self._hovered = False
    self.update()
    super().leaveEvent(event)

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self.clicked.emit()
    super().mousePressEvent(event)

  def paintEvent(self, event) -> None:  # noqa: N802
    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(4, 4, self.width() - 8, self.height() - 8)

    if self._active or self._hovered:
      bg = QColor(255, 255, 255)
      bg.setAlphaF(0.06 if self._hovered and not self._active else 0.09)
      painter.setPen(Qt.PenStyle.NoPen)
      painter.setBrush(bg)
      painter.drawRoundedRect(rect, 10, 10)

    if self._active:
      color = QColor(t.TEXT_PRIMARY)
    elif self._hovered:
      color = QColor(t.TEXT_SECONDARY)
    else:
      color = QColor(t.TEXT_MUTED)

    draw_icon(painter, self._icon, QRectF(0, 0, self.width(), self.height()), color)
    painter.end()
