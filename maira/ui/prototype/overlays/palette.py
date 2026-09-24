"""Command palette (Ctrl+K) and global search overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QPushButton,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class _OverlayBase(QWidget):
  closed = Signal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("OverlayScrim")
    self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    self.hide()
    self._root = QVBoxLayout(self)
    self._root.setContentsMargins(0, 0, 0, 0)
    self._root.addStretch(1)
    self.panel = QFrame()
    self.panel.setObjectName("OverlayPanel")
    self.panel.setFixedWidth(560)
    self._root.addWidget(self.panel, alignment=Qt.AlignmentFlag.AlignHCenter)
    self._root.addStretch(2)

  def open(self) -> None:
    self.show()
    self.raise_()

  def close_overlay(self) -> None:
    self.hide()
    self.closed.emit()

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if not self.panel.geometry().contains(event.position().toPoint()):
      self.close_overlay()
    else:
      super().mousePressEvent(event)


class CommandPalette(_OverlayBase):
  activated = Signal(str)

  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    layout = QVBoxLayout(self.panel)
    layout.setContentsMargins(16, 16, 16, 12)
    layout.setSpacing(10)

    self.input = QLineEdit()
    self.input.setPlaceholderText("Search commands...")
    self.input.textChanged.connect(self._filter)
    self.input.returnPressed.connect(self._activate_current)
    layout.addWidget(self.input)

    self.list = QListWidget()
    self.list.itemActivated.connect(lambda _: self._activate_current())
    self.list.itemClicked.connect(lambda _: self._activate_current())
    layout.addWidget(self.list)

    hint = QLabel("Ctrl + K · Enter to run · Esc to close")
    hint.setObjectName("Muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(hint)
    self._filter("")

  def open(self) -> None:
    super().open()
    self.input.clear()
    self._filter("")
    self.input.setFocus()

  def _filter(self, text: str) -> None:
    self.list.clear()
    q = text.strip().lower()
    for cmd in self.store.commands():
      if q and q not in cmd["label"].lower() and q not in cmd["hint"].lower():
        continue
      item = QListWidgetItem(f"{cmd['label']}    ·  {cmd['hint']}")
      item.setData(Qt.ItemDataRole.UserRole, cmd["id"])
      self.list.addItem(item)
    if self.list.count():
      self.list.setCurrentRow(0)

  def _activate_current(self) -> None:
    item = self.list.currentItem()
    if not item:
      return
    cmd_id = item.data(Qt.ItemDataRole.UserRole)
    self.close_overlay()
    self.activated.emit(cmd_id)

  def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
    if event.key() == Qt.Key.Key_Escape:
      self.close_overlay()
      return
    if event.key() == Qt.Key.Key_Down:
      self.list.setCurrentRow(min(self.list.count() - 1, self.list.currentRow() + 1))
      return
    if event.key() == Qt.Key.Key_Up:
      self.list.setCurrentRow(max(0, self.list.currentRow() - 1))
      return
    super().keyPressEvent(event)


class SearchOverlay(_OverlayBase):
  result_chosen = Signal(str, str)

  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    self.panel.setFixedWidth(640)
    layout = QVBoxLayout(self.panel)
    layout.setContentsMargins(16, 16, 16, 12)
    layout.setSpacing(10)

    self.input = QLineEdit()
    self.input.setPlaceholderText("Search everything...")
    self.input.textChanged.connect(self._filter)
    layout.addWidget(self.input)

    tabs = QHBoxLayout()
    self._category = "Everything"
    self._tab_buttons: list[QPushButton] = []
    for cat in ("Everything", "Conversations", "Memory", "Notes", "Tasks", "Files"):
      btn = QPushButton(cat)
      btn.setObjectName("GhostButton")
      btn.setCursor(Qt.CursorShape.PointingHandCursor)
      btn.clicked.connect(lambda _=False, c=cat: self._set_category(c))
      tabs.addWidget(btn)
      self._tab_buttons.append(btn)
    tabs.addStretch(1)
    layout.addLayout(tabs)

    self.list = QListWidget()
    self.list.itemClicked.connect(self._choose)
    layout.addWidget(self.list)
    hint = QLabel("Esc to close")
    hint.setObjectName("Muted")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(hint)

  def set_categories(self, allowed: list[str]) -> None:
    """Show only the category tabs that have real data behind them."""
    for btn in self._tab_buttons:
      btn.setVisible(btn.text() in allowed)

  def open(self) -> None:
    super().open()
    self.input.clear()
    self._set_category("Everything")
    self.input.setFocus()

  def _set_category(self, category: str) -> None:
    self._category = category
    self._filter(self.input.text())

  def _filter(self, text: str) -> None:
    self.list.clear()
    for result in self.store.search(text, self._category):
      item = QListWidgetItem(f"[{result['category']}]  {result['title']}\n{result['subtitle']}")
      item.setData(Qt.ItemDataRole.UserRole, (result["category"], result["id"]))
      self.list.addItem(item)

  def _choose(self, item: QListWidgetItem) -> None:
    category, _rid = item.data(Qt.ItemDataRole.UserRole)
    self.close_overlay()
    self.result_chosen.emit(category, item.text())

  def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
    if event.key() == Qt.Key.Key_Escape:
      self.close_overlay()
      return
    super().keyPressEvent(event)
