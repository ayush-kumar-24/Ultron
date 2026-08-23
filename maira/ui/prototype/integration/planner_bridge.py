"""Bridge: prototype Tasks + Notes ↔ PlannerService."""

from __future__ import annotations

from PySide6.QtCore import QObject

from maira.core.domain.value_objects import Priority, TaskStatus
from maira.core.interfaces.planner import Planner
from maira.ui.prototype.screens.notes import NotesScreen
from maira.ui.prototype.screens.tasks import TasksScreen


def _task_section(status: TaskStatus) -> str:
  return "Completed" if status == TaskStatus.DONE else "Today"


class ProtoPlannerBridge(QObject):
  def __init__(self, planner: Planner, tasks: TasksScreen, notes: NotesScreen) -> None:
    super().__init__()
    self._planner = planner
    self._tasks = tasks
    self._notes = notes

    tasks.set_live_mode(True)
    notes.set_live_mode(True)

    tasks.add_requested.connect(self.add_task)
    tasks.toggle_requested.connect(self.toggle_task)
    notes.add_requested.connect(self.add_note)
    notes.save_requested.connect(self.save_note)
    notes.select_requested.connect(self.select_note)

    self.refresh()

  def refresh(self) -> None:
    task_rows = []
    for task in self._planner.list_tasks():
      task_rows.append(
        {
          "id": task.id,
          "title": task.title,
          "section": _task_section(task.status),
          "time": task.priority.value.title(),
          "done": task.status == TaskStatus.DONE,
          "priority": task.priority.value.title(),
        }
      )
    self._tasks.set_tasks(task_rows)

    note_rows = []
    for note in self._planner.list_notes():
      note_rows.append(
        {
          "id": note.id,
          "title": note.title,
          "updated": note.updated_at.strftime("%b %d"),
          "body": note.body,
        }
      )
    selected = note_rows[0]["id"] if note_rows else None
    self._notes.set_notes(note_rows, selected)

  def add_task(self, title: str) -> None:
    self._planner.add_task(title, priority=Priority.MEDIUM)
    self.refresh()

  def toggle_task(self, task_id: str) -> None:
    for task in self._planner.list_tasks():
      if task.id == task_id:
        new_status = TaskStatus.OPEN if task.status == TaskStatus.DONE else TaskStatus.DONE
        self._planner.set_task_status(task_id, new_status)
        break
    self.refresh()

  def add_note(self) -> None:
    note = self._planner.add_note("Untitled", "")
    self.refresh()
    self._notes.select_note(note.id)

  def save_note(self, note_id: str, title: str, body: str) -> None:
    self._planner.update_note(note_id, title=title, body=body)

  def select_note(self, note_id: str) -> None:
    note = self._planner.get_note(note_id)
    if note is None:
      return
    self._notes.show_note(
      {
        "id": note.id,
        "title": note.title,
        "updated": note.updated_at.strftime("%b %d"),
        "body": note.body,
      }
    )
