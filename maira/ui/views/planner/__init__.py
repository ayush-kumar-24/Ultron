"""Planner view — todos and notes tabs."""

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
  QTabWidget,
  QTextEdit,
  QVBoxLayout,
  QWidget,
)

from maira.core.domain.entities import Note, Task
from maira.core.domain.value_objects import Priority, TaskStatus


class PlannerView(QWidget):
  add_task_requested = Signal(str, str)  # title, priority
  toggle_task_requested = Signal(str, bool)  # task_id, done
  delete_task_requested = Signal(str)
  change_priority_requested = Signal(str, str)  # task_id, priority

  add_note_requested = Signal()
  save_note_requested = Signal(str, str, str)  # note_id, title, body
  delete_note_requested = Signal(str)
  note_selected = Signal(str)
  save_note_to_memory_requested = Signal(str, str)  # title, body

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self._selected_note_id: str | None = None
    self._updating_notes = False
    self._build_ui()

  def _build_ui(self) -> None:
    root = QVBoxLayout(self)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)

    title = QLabel("Planner")
    title.setObjectName("plannerTitle")
    root.addWidget(title)

    tabs = QTabWidget()
    tabs.addTab(self._build_todos_tab(), "Todos")
    tabs.addTab(self._build_notes_tab(), "Notes")
    root.addWidget(tabs, stretch=1)

  def _build_todos_tab(self) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(10)

    add_row = QHBoxLayout()
    self._task_input = QLineEdit()
    self._task_input.setPlaceholderText("Add a todo…")
    self._task_input.returnPressed.connect(self._emit_add_task)
    add_row.addWidget(self._task_input, stretch=1)

    self._task_priority = QComboBox()
    self._task_priority.addItem("Low", Priority.LOW.value)
    self._task_priority.addItem("Medium", Priority.MEDIUM.value)
    self._task_priority.addItem("High", Priority.HIGH.value)
    self._task_priority.setCurrentIndex(1)
    add_row.addWidget(self._task_priority)

    add_button = QPushButton("Add")
    add_button.clicked.connect(self._emit_add_task)
    add_row.addWidget(add_button)
    layout.addLayout(add_row)

    self._task_list = QListWidget()
    self._task_list.setObjectName("todoList")
    layout.addWidget(self._task_list, stretch=1)
    return page

  def _build_notes_tab(self) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(10)

    toolbar = QHBoxLayout()
    add_note = QPushButton("New note")
    add_note.clicked.connect(self.add_note_requested.emit)
    toolbar.addWidget(add_note)
    toolbar.addStretch(1)
    self._delete_note_button = QPushButton("Delete")
    self._delete_note_button.clicked.connect(self._emit_delete_note)
    toolbar.addWidget(self._delete_note_button)
    self._save_to_memory_button = QPushButton("Save to memory")
    self._save_to_memory_button.clicked.connect(self._emit_save_note_to_memory)
    toolbar.addWidget(self._save_to_memory_button)
    self._save_note_button = QPushButton("Save")
    self._save_note_button.clicked.connect(self._emit_save_note)
    toolbar.addWidget(self._save_note_button)
    layout.addLayout(toolbar)

    splitter = QSplitter(Qt.Orientation.Horizontal)

    self._note_list = QListWidget()
    self._note_list.setObjectName("noteList")
    self._note_list.currentItemChanged.connect(self._on_note_item_changed)
    splitter.addWidget(self._note_list)

    editor = QWidget()
    editor_layout = QVBoxLayout(editor)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    editor_layout.setSpacing(8)
    self._note_title = QLineEdit()
    self._note_title.setPlaceholderText("Note title")
    editor_layout.addWidget(self._note_title)
    self._note_body = QTextEdit()
    self._note_body.setPlaceholderText("Write your note…")
    editor_layout.addWidget(self._note_body, stretch=1)
    splitter.addWidget(editor)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 2)

    layout.addWidget(splitter, stretch=1)
    self._set_note_editor_enabled(False)
    return page

  def _emit_add_task(self) -> None:
    title = self._task_input.text().strip()
    if not title:
      return
    priority = str(self._task_priority.currentData())
    self._task_input.clear()
    self.add_task_requested.emit(title, priority)

  def _emit_save_note(self) -> None:
    if not self._selected_note_id:
      return
    self.save_note_requested.emit(
      self._selected_note_id,
      self._note_title.text(),
      self._note_body.toPlainText(),
    )

  def _emit_delete_note(self) -> None:
    if self._selected_note_id:
      self.delete_note_requested.emit(self._selected_note_id)

  def _emit_save_note_to_memory(self) -> None:
    if not self._selected_note_id:
      return
    self.save_note_to_memory_requested.emit(
      self._note_title.text(),
      self._note_body.toPlainText(),
    )

  def _on_note_item_changed(
    self,
    current: QListWidgetItem | None,
    _previous: QListWidgetItem | None,
  ) -> None:
    if self._updating_notes or current is None:
      return
    note_id = current.data(Qt.ItemDataRole.UserRole)
    if note_id:
      self.note_selected.emit(str(note_id))

  def set_tasks(self, tasks: list[Task]) -> None:
    self._task_list.clear()
    for task in tasks:
      row = QWidget()
      row_layout = QHBoxLayout(row)
      row_layout.setContentsMargins(8, 4, 8, 4)
      row_layout.setSpacing(8)

      checkbox = QPushButton("✓" if task.status == TaskStatus.DONE else "○")
      checkbox.setObjectName("todoCheck")
      checkbox.setFixedWidth(32)
      checkbox.clicked.connect(
        lambda _=False, task_id=task.id, done=(task.status != TaskStatus.DONE): (
          self.toggle_task_requested.emit(task_id, done)
        )
      )
      row_layout.addWidget(checkbox)

      title = QLabel(task.title)
      if task.status == TaskStatus.DONE:
        title.setObjectName("todoDoneLabel")
      else:
        title.setObjectName("todoOpenLabel")
      title.setWordWrap(True)
      row_layout.addWidget(title, stretch=1)

      priority = QComboBox()
      for label, value in (
        ("Low", Priority.LOW.value),
        ("Medium", Priority.MEDIUM.value),
        ("High", Priority.HIGH.value),
      ):
        priority.addItem(label, value)
      priority.blockSignals(True)
      priority.setCurrentIndex(
        {Priority.LOW: 0, Priority.MEDIUM: 1, Priority.HIGH: 2}[task.priority]
      )
      priority.blockSignals(False)
      priority.currentIndexChanged.connect(
        lambda _index, task_id=task.id, box=priority: self.change_priority_requested.emit(
          task_id, str(box.currentData())
        )
      )
      row_layout.addWidget(priority)

      delete = QPushButton("Delete")
      delete.clicked.connect(lambda _=False, task_id=task.id: self.delete_task_requested.emit(task_id))
      row_layout.addWidget(delete)

      item = QListWidgetItem()
      item.setSizeHint(row.sizeHint())
      self._task_list.addItem(item)
      self._task_list.setItemWidget(item, row)

  def set_notes(self, notes: list[Note], selected_id: str | None = None) -> None:
    self._updating_notes = True
    self._note_list.clear()
    active_row = -1
    for index, note in enumerate(notes):
      item = QListWidgetItem(note.title)
      item.setData(Qt.ItemDataRole.UserRole, note.id)
      self._note_list.addItem(item)
      if note.id == selected_id:
        active_row = index
    if active_row >= 0:
      self._note_list.setCurrentRow(active_row)
    elif notes and selected_id is None:
      self._note_list.setCurrentRow(0)
    self._updating_notes = False

  def show_note(self, note: Note | None) -> None:
    if note is None:
      self._selected_note_id = None
      self._note_title.clear()
      self._note_body.clear()
      self._set_note_editor_enabled(False)
      return
    self._selected_note_id = note.id
    self._note_title.setText(note.title)
    self._note_body.setPlainText(note.body)
    self._set_note_editor_enabled(True)

  def _set_note_editor_enabled(self, enabled: bool) -> None:
    self._note_title.setEnabled(enabled)
    self._note_body.setEnabled(enabled)
    self._save_note_button.setEnabled(enabled)
    self._delete_note_button.setEnabled(enabled)
    self._save_to_memory_button.setEnabled(enabled)
