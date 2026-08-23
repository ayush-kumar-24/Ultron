"""Collapsible minimal sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from maira.ui.prototype.components.icon_button import IconButton
from maira.ui.prototype.components.maira_logo import MairaLogo
from maira.ui.prototype.theme import tokens as t

NAV_ITEMS = [
  ("home", "Home", "Home"),
  ("chat", "Chat", "Chat"),
  ("memory", "Memory", "Memory"),
  ("tasks", "Tasks", "Tasks"),
  ("notes", "Notes", "Notes"),
  ("activity", "Activity", "Activity"),
  ("automations", "Automations", "Automations"),
]


class _NavRow(QWidget):
  clicked = Signal(str)

  def __init__(self, key: str, icon: str, label: str, parent=None) -> None:
    super().__init__(parent)
    self.key = key
    self._active = False
    self.setCursor(Qt.CursorShape.PointingHandCursor)
    self.setToolTip(label)
    self.setFixedHeight(44)
    layout = QHBoxLayout(self)
    layout.setContentsMargins(12, 0, 12, 0)
    layout.setSpacing(12)
    self.btn = IconButton(icon, label, size=36)
    self.btn.clicked.connect(lambda: self.clicked.emit(self.key))
    self.label = QLabel(label)
    self.label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 13px;")
    layout.addWidget(self.btn)
    layout.addWidget(self.label)
    layout.addStretch(1)

  def set_expanded(self, expanded: bool) -> None:
    self.label.setVisible(expanded)

  def set_active(self, active: bool) -> None:
    self._active = active
    self.btn.set_active(active)
    color = t.TEXT_PRIMARY if active else t.TEXT_MUTED
    self.label.setStyleSheet(f"color: {color}; font-size: 13px;")

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self.clicked.emit(self.key)
    super().mousePressEvent(event)


class _Avatar(QWidget):
  clicked = Signal()

  def __init__(self, initials: str = "A", parent=None) -> None:
    super().__init__(parent)
    self._initials = initials[:1].upper()
    self.setFixedSize(36, 36)
    self.setCursor(Qt.CursorShape.PointingHandCursor)
    self.setToolTip("Profile")

  def set_initials(self, initials: str) -> None:
    self._initials = (initials or "A")[:1].upper()
    self.update()

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self.clicked.emit()
    super().mousePressEvent(event)

  def paintEvent(self, event) -> None:  # noqa: N802
    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(255, 255, 255, 28))
    painter.setBrush(QColor(t.BG_ELEVATED))
    painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)
    painter.setPen(QColor(t.TEXT_PRIMARY))
    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._initials)
    painter.end()


class Sidebar(QWidget):
  navigate = Signal(str)
  toggle_expand = Signal(bool)

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("Sidebar")
    self._expanded = False
    self.setFixedWidth(t.SIDEBAR_COLLAPSED)
    self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 16, 0, 16)
    root.setSpacing(4)

    top = QHBoxLayout()
    top.setContentsMargins(16, 0, 8, 12)
    self.logo = MairaLogo(size="small", glowing=True)
    self.logo.setCursor(Qt.CursorShape.PointingHandCursor)
    self.logo.setToolTip("Expand / collapse")
    self.wordmark = QLabel("MAIRA")
    self.wordmark.setObjectName("BrandWordmark")
    self.wordmark.hide()
    top.addWidget(self.logo)
    top.addWidget(self.wordmark)
    top.addStretch(1)
    root.addLayout(top)

    self._rows: dict[str, _NavRow] = {}
    for key, icon, label in NAV_ITEMS:
      row = _NavRow(key, icon, label)
      row.set_expanded(False)
      row.clicked.connect(self.navigate.emit)
      self._rows[key] = row
      root.addWidget(row)

    root.addStretch(1)

    self.settings_row = _NavRow("settings", "settings", "Settings")
    self.settings_row.set_expanded(False)
    self.settings_row.clicked.connect(self.navigate.emit)
    root.addWidget(self.settings_row)

    bottom = QHBoxLayout()
    bottom.setContentsMargins(16, 8, 12, 0)
    self.avatar = _Avatar("A")
    self.avatar.clicked.connect(lambda: self.navigate.emit("settings"))
    bottom.addWidget(self.avatar)
    bottom.addStretch(1)
    root.addLayout(bottom)

    self.set_active("home")

  def mousePressEvent(self, event) -> None:  # noqa: N802
    # Click logo area to toggle expand
    if event.button() == Qt.MouseButton.LeftButton and self.logo.geometry().contains(event.position().toPoint()):
      self.set_expanded(not self._expanded)
      return
    super().mousePressEvent(event)

  def set_expanded(self, expanded: bool) -> None:
    self._expanded = expanded
    width = t.SIDEBAR_EXPANDED if expanded else t.SIDEBAR_COLLAPSED
    self.setFixedWidth(width)
    self.wordmark.setVisible(expanded)
    for row in self._rows.values():
      row.set_expanded(expanded)
    self.settings_row.set_expanded(expanded)
    self.toggle_expand.emit(expanded)

  def set_active(self, key: str) -> None:
    for k, row in self._rows.items():
      row.set_active(k == key)
    self.settings_row.set_active(key == "settings")

  def set_profile_initial(self, name: str) -> None:
    self.avatar.set_initials(name)
