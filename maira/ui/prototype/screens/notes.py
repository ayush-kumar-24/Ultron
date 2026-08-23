"""Notes screen — mock or live Planner notes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QPushButton,
  QPlainTextEdit,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.primitives import EmptyState, PageHeader
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class NotesScreen(QWidget):
  add_requested = Signal()
  save_requested = Signal(str, str, str)
  select_requested = Signal(str)

  def __init__(self, store: MockStore | None = None, parent=None) -> None:
    super().__init__(parent)
    self.store = store or MockStore()
    self._live = False
    self._loading = False
    self._selected_id: str | None = None
    self._notes: list[dict] = []

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)

    top = QHBoxLayout()
    top.addWidget(PageHeader("Notes", "Distraction-free writing"))
    top.addStretch(1)
    add = QPushButton("+ New Note")
    add.setObjectName("GhostButton")
    add.clicked.connect(self._add)
    top.addWidget(add)
    root.addLayout(top)

    body = QHBoxLayout()
    body.setSpacing(16)

    left = QFrame()
    left.setObjectName("Card")
    left.setFixedWidth(280)
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(8, 8, 8, 8)
    self.list = QListWidget()
    self.list.currentItemChanged.connect(self._on_select)
    left_layout.addWidget(self.list)
    body.addWidget(left)

    right = QFrame()
    right.setObjectName("Card")
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(20, 20, 20, 20)
    right_layout.setSpacing(12)
    self.title = QLineEdit()
    self.title.setPlaceholderText("Note title")
    self.title.setStyleSheet(
      f"QLineEdit {{ background: transparent; border: none; font-size: 20px; color: {t.TEXT_PRIMARY}; padding: 4px 0; }}"
    )
    self.title.textChanged.connect(self._save)
    self.body = QPlainTextEdit()
    self.body.setPlaceholderText("Start writing...")
    self.body.setStyleSheet(
      f"QPlainTextEdit {{ background: transparent; border: none; color: {t.TEXT_PRIMARY}; font-size: 14px; }}"
    )
    self.body.textChanged.connect(self._save)
    self.meta = QLabel()
    self.meta.setObjectName("Muted")
    right_layout.addWidget(self.title)
    right_layout.addWidget(self.meta)
    right_layout.addWidget(self.body, stretch=1)
    body.addWidget(right, stretch=1)
    root.addLayout(body, stretch=1)

    self.empty = EmptyState("Nothing here yet.", "Capture an idea with + New Note.")
    root.addWidget(self.empty)
    self.empty.hide()

    if not self._live:
      self.store.changed.connect(lambda k: k == "notes" and self.reload_from_store())
      self.reload_from_store()

  def set_live_mode(self, enabled: bool) -> None:
    self._live = enabled

  def set_notes(self, notes: list[dict], selected_id: str | None) -> None:
    self._notes = notes
    self._selected_id = selected_id
    self._loading = True
    self.list.clear()
    for note in notes:
      item = QListWidgetItem(f"{note['title']}\n{note.get('updated', '')}")
      item.setData(Qt.ItemDataRole.UserRole, note["id"])
      self.list.addItem(item)
      if note["id"] == selected_id:
        self.list.setCurrentItem(item)
    has = bool(notes)
    self.empty.setVisible(not has)
    self.list.setVisible(has)
    self.title.setEnabled(has)
    self.body.setEnabled(has)
    if has and self.list.currentItem() is None and self.list.count():
      self.list.setCurrentRow(0)
    self._loading = False
    if selected_id:
      self.select_note(selected_id)

  def select_note(self, note_id: str) -> None:
    self._selected_id = note_id
    for i in range(self.list.count()):
      item = self.list.item(i)
      if item.data(Qt.ItemDataRole.UserRole) == note_id:
        self.list.setCurrentItem(item)
        break

  def show_note(self, note: dict | None) -> None:
    if not note:
      return
    self._loading = True
    self._selected_id = note["id"]
    self.title.setText(note["title"])
    self.body.setPlainText(note.get("body", ""))
    self.meta.setText(f"Updated {note.get('updated', '')}")
    self._loading = False

  def reload_from_store(self) -> None:
    notes = list(self.store.notes)
    selected = self.store.selected_note_id
    self.set_notes(notes, selected)

  def _add(self) -> None:
    if self._live:
      self.add_requested.emit()
    else:
      self.store.add_note("Untitled")

  def _on_select(self, current, _previous) -> None:
    if current is None:
      return
    note_id = current.data(Qt.ItemDataRole.UserRole)
    self._selected_id = note_id
    if self._live:
      self.select_requested.emit(note_id)
    else:
      note = self.store.get_note(note_id)
      if note:
        self.show_note(note)

  def _save(self) -> None:
    if self._loading or not self._selected_id:
      return
    title = self.title.text()
    body = self.body.toPlainText()
    if self._live:
      self.save_requested.emit(self._selected_id, title, body)
    else:
      self.store.update_note(self._selected_id, title, body)
