"""Tasks screen — mock or live Planner tasks."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QInputDialog,
  QLabel,
  QPushButton,
  QScrollArea,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.primitives import EmptyState, PageHeader, SectionHeader
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class TaskRow(QFrame):
  def __init__(self, task: dict, on_toggle, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("Card")
    layout = QHBoxLayout(self)
    layout.setContentsMargins(14, 10, 14, 10)

    check = QPushButton("✓" if task["done"] else "")
    check.setFixedSize(28, 28)
    check.setCursor(Qt.CursorShape.PointingHandCursor)
    check.setStyleSheet(
      f"""
      QPushButton {{
        border: 1px solid {t.BORDER_HOVER};
        border-radius: 14px;
        background: {'rgba(255,255,255,0.08)' if task['done'] else 'transparent'};
        color: {t.TEXT_PRIMARY};
        font-size: 12px;
      }}
      QPushButton:hover {{ border-color: {t.BORDER_ACTIVE}; }}
      """
    )
    check.clicked.connect(lambda: on_toggle(task["id"]))
    layout.addWidget(check)

    col = QVBoxLayout()
    title = QLabel(task["title"])
    color = t.TEXT_MUTED if task["done"] else t.TEXT_PRIMARY
    deco = "text-decoration: line-through;" if task["done"] else ""
    title.setStyleSheet(f"color: {color}; font-size: 14px; {deco}")
    meta = QLabel(f"{task.get('time', '')} · {task.get('priority', '')}")
    meta.setObjectName("Muted")
    col.addWidget(title)
    col.addWidget(meta)
    layout.addLayout(col, stretch=1)


class TasksScreen(QWidget):
  add_requested = Signal(str)
  toggle_requested = Signal(str)

  def __init__(self, store: MockStore | None = None, parent=None) -> None:
    super().__init__(parent)
    self.store = store or MockStore()
    self._live = False
    self._tasks: list[dict] = []

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)

    top = QHBoxLayout()
    top.addWidget(PageHeader("Tasks", "Today, upcoming, and done"))
    top.addStretch(1)
    add = QPushButton("+ New Task")
    add.setObjectName("GhostButton")
    add.clicked.connect(self._add)
    top.addWidget(add)
    root.addLayout(top)

    self.scroll = QScrollArea()
    self.scroll.setWidgetResizable(True)
    self.host = QWidget()
    self.host_layout = QVBoxLayout(self.host)
    self.host_layout.setSpacing(8)
    self.scroll.setWidget(self.host)
    root.addWidget(self.scroll, stretch=1)

    self.empty = EmptyState("Nothing here yet.", "Create a task to start shaping your day.")
    root.addWidget(self.empty)
    self.empty.hide()

    if not self._live:
      store = self.store
      store.changed.connect(lambda k: k == "tasks" and self.reload_from_store())
      self.reload_from_store()

  def set_live_mode(self, enabled: bool) -> None:
    self._live = enabled

  def set_tasks(self, tasks: list[dict]) -> None:
    self._tasks = tasks
    self._render(tasks)

  def reload_from_store(self) -> None:
    sections = self.store.tasks_by_section()
    flat = []
    for name in ("Today", "Upcoming", "Completed"):
      for task in sections.get(name, []):
        flat.append(task)
    self.set_tasks(flat)

  def _render(self, tasks: list[dict]) -> None:
    while self.host_layout.count():
      item = self.host_layout.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    buckets = {"Today": [], "Upcoming": [], "Completed": []}
    for task in tasks:
      section = "Completed" if task.get("done") else task.get("section", "Today")
      if section not in buckets:
        section = "Today"
      buckets[section].append(task)
    any_items = False
    for name in ("Today", "Upcoming", "Completed"):
      items = buckets[name]
      if not items:
        continue
      any_items = True
      self.host_layout.addWidget(SectionHeader(name))
      for task in items:
        self.host_layout.addWidget(TaskRow(task, self._toggle))
    self.host_layout.addStretch(1)
    self.empty.setVisible(not any_items)
    self.scroll.setVisible(any_items)

  def _add(self) -> None:
    text, ok = QInputDialog.getText(self, "New Task", "Task title:")
    if not ok or not text.strip():
      return
    if self._live:
      self.add_requested.emit(text.strip())
    else:
      self.store.add_task(text.strip())

  def _toggle(self, task_id: str) -> None:
    if self._live:
      self.toggle_requested.emit(task_id)
    else:
      self.store.toggle_task(task_id)
