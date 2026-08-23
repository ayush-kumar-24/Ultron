"""Shared small UI primitives."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QPushButton,
  QSizePolicy,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.theme import tokens as t


class EmptyState(QWidget):
  def __init__(self, title: str, body: str, parent=None) -> None:
    super().__init__(parent)
    layout = QVBoxLayout(self)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("EmptyTitle")
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    body_lbl = QLabel(body)
    body_lbl.setObjectName("EmptyBody")
    body_lbl.setWordWrap(True)
    body_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    body_lbl.setMaximumWidth(360)
    layout.addWidget(title_lbl)
    layout.addWidget(body_lbl)


class ErrorBanner(QFrame):
  retry = Signal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("Card")
    layout = QVBoxLayout(self)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    self.title = QLabel()
    self.title.setObjectName("ErrorBanner")
    self.title.setWordWrap(True)
    self.body = QLabel()
    self.body.setObjectName("Muted")
    self.body.setWordWrap(True)
    self.retry_btn = QPushButton("Retry")
    self.retry_btn.setObjectName("GhostButton")
    self.retry_btn.setFixedWidth(100)
    self.retry_btn.clicked.connect(self.retry.emit)
    layout.addWidget(self.title)
    layout.addWidget(self.body)
    layout.addWidget(self.retry_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    self.hide()

  def show_error(self, title: str, body: str) -> None:
    self.title.setText(title)
    self.body.setText(body)
    self.show()


class ToggleSwitch(QWidget):
  toggled = Signal(bool)

  def __init__(self, checked: bool = False, parent=None) -> None:
    super().__init__(parent)
    self._checked = checked
    self.setFixedSize(42, 24)
    self.setCursor(Qt.CursorShape.PointingHandCursor)

  def isChecked(self) -> bool:  # noqa: N802
    return self._checked

  def setChecked(self, checked: bool) -> None:  # noqa: N802
    self._checked = checked
    self.update()

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self._checked = not self._checked
      self.toggled.emit(self._checked)
      self.update()
    super().mousePressEvent(event)

  def paintEvent(self, event) -> None:  # noqa: N802
    from PySide6.QtGui import QColor, QPainter

    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor("#3F3F46") if not self._checked else QColor("#4ADE80")
    if self._checked:
      bg.setAlphaF(0.85)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
    knob_x = self.width() - 20 if self._checked else 4
    painter.setBrush(QColor(t.CTA_FILL))
    painter.drawEllipse(knob_x, 4, 16, 16)
    painter.end()


class SectionHeader(QWidget):
  def __init__(self, text: str, parent=None) -> None:
    super().__init__(parent)
    layout = QHBoxLayout(self)
    layout.setContentsMargins(0, 8, 0, 8)
    label = QLabel(text.upper())
    label.setObjectName("SectionLabel")
    layout.addWidget(label)
    layout.addStretch(1)


class PageHeader(QWidget):
  def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
    super().__init__(parent)
    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("PageTitle")
    layout.addWidget(title_lbl)
    if subtitle:
      sub = QLabel(subtitle)
      sub.setObjectName("PageSubtitle")
      layout.addWidget(sub)


class ToastHost(QWidget):
  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    self._label = QLabel(self)
    self._label.setObjectName("Toast")
    self._label.hide()
    from PySide6.QtCore import QTimer

    self._timer = QTimer(self)
    self._timer.setSingleShot(True)
    self._timer.timeout.connect(self._label.hide)

  def show_toast(self, text: str) -> None:
    self._label.setText(text)
    self._label.adjustSize()
    self._label.move(max(0, (self.width() - self._label.width()) // 2), 24)
    self._label.show()
    self._timer.start(2200)

  def resizeEvent(self, event) -> None:  # noqa: N802
    super().resizeEvent(event)
    if self._label.isVisible():
      self._label.move(max(0, (self.width() - self._label.width()) // 2), 24)
