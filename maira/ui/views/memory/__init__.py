"""Memory view — browse, filter, and edit stored memories."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QComboBox,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QPushButton,
  QSplitter,
  QTextEdit,
  QVBoxLayout,
  QWidget,
)

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory

_CATEGORY_LABELS = {
  MemoryCategory.PREFERENCE: "Preference",
  MemoryCategory.CONVERSATION: "Conversation",
  MemoryCategory.TASK: "Task",
  MemoryCategory.NOTE: "Note",
  MemoryCategory.IDEA: "Idea",
  MemoryCategory.PROJECT: "Project",
}


class MemoryView(QWidget):
  add_requested = Signal()
  save_requested = Signal(str, str, str, str)  # id, category, title, body
  delete_requested = Signal(str)
  memory_selected = Signal(str)
  filter_changed = Signal(str, str)  # category value or "", search text

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self._selected_id: str | None = None
    self._updating = False
    self._build_ui()

  def _build_ui(self) -> None:
    root = QVBoxLayout(self)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)

    title = QLabel("Memory")
    title.setObjectName("memoryTitle")
    root.addWidget(title)

    toolbar = QHBoxLayout()
    self._search = QLineEdit()
    self._search.setPlaceholderText("Search by meaning or keywords…")
    self._search.textChanged.connect(self._emit_filter)
    toolbar.addWidget(self._search, stretch=1)

    self._category_filter = QComboBox()
    self._category_filter.addItem("All categories", "")
    for category, label in _CATEGORY_LABELS.items():
      self._category_filter.addItem(label, category.value)
    self._category_filter.currentIndexChanged.connect(self._emit_filter)
    toolbar.addWidget(self._category_filter)

    add_button = QPushButton("Add memory")
    add_button.clicked.connect(self.add_requested.emit)
    toolbar.addWidget(add_button)
    root.addLayout(toolbar)

    splitter = QSplitter(Qt.Orientation.Horizontal)

    self._list = QListWidget()
    self._list.setObjectName("memoryList")
    self._list.currentItemChanged.connect(self._on_item_changed)
    splitter.addWidget(self._list)

    editor = QWidget()
    editor_layout = QVBoxLayout(editor)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    editor_layout.setSpacing(8)

    self._category = QComboBox()
    for category, label in _CATEGORY_LABELS.items():
      self._category.addItem(label, category.value)
    editor_layout.addWidget(self._category)

    self._title = QLineEdit()
    self._title.setPlaceholderText("Title")
    editor_layout.addWidget(self._title)

    self._body = QTextEdit()
    self._body.setPlaceholderText("What should Ultron remember?")
    editor_layout.addWidget(self._body, stretch=1)

    actions = QHBoxLayout()
    actions.addStretch(1)
    self._delete_button = QPushButton("Delete")
    self._delete_button.clicked.connect(self._emit_delete)
    actions.addWidget(self._delete_button)
    self._save_button = QPushButton("Save")
    self._save_button.clicked.connect(self._emit_save)
    actions.addWidget(self._save_button)
    editor_layout.addLayout(actions)

    splitter.addWidget(editor)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 2)
    root.addWidget(splitter, stretch=1)

    self._set_editor_enabled(False)

  def _emit_filter(self) -> None:
    category = str(self._category_filter.currentData() or "")
    self.filter_changed.emit(category, self._search.text())

  def _emit_save(self) -> None:
    if not self._selected_id:
      return
    self.save_requested.emit(
      self._selected_id,
      str(self._category.currentData()),
      self._title.text(),
      self._body.toPlainText(),
    )

  def _emit_delete(self) -> None:
    if self._selected_id:
      self.delete_requested.emit(self._selected_id)

  def _on_item_changed(
    self,
    current: QListWidgetItem | None,
    _previous: QListWidgetItem | None,
  ) -> None:
    if self._updating or current is None:
      return
    memory_id = current.data(Qt.ItemDataRole.UserRole)
    if memory_id:
      self.memory_selected.emit(str(memory_id))

  def set_memories(
    self,
    memories: list[MemoryEntry],
    selected_id: str | None = None,
  ) -> None:
    self._updating = True
    self._list.clear()
    active_row = -1
    for index, memory in enumerate(memories):
      label = _CATEGORY_LABELS.get(memory.category, memory.category.value)
      item = QListWidgetItem(f"{memory.title}\n{label}")
      item.setData(Qt.ItemDataRole.UserRole, memory.id)
      item.setToolTip(memory.body[:200])
      self._list.addItem(item)
      if memory.id == selected_id:
        active_row = index
    if active_row >= 0:
      self._list.setCurrentRow(active_row)
    self._updating = False

  def show_memory(self, memory: MemoryEntry | None) -> None:
    if memory is None:
      self._selected_id = None
      self._title.clear()
      self._body.clear()
      self._category.setCurrentIndex(0)
      self._set_editor_enabled(False)
      return

    self._selected_id = memory.id
    self._title.setText(memory.title)
    self._body.setPlainText(memory.body)
    index = self._category.findData(memory.category.value)
    if index >= 0:
      self._category.setCurrentIndex(index)
    self._set_editor_enabled(True)

  def _set_editor_enabled(self, enabled: bool) -> None:
    self._category.setEnabled(enabled)
    self._title.setEnabled(enabled)
    self._body.setEnabled(enabled)
    self._save_button.setEnabled(enabled)
    self._delete_button.setEnabled(enabled)
