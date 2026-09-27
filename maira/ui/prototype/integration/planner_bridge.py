"""Bridge: prototype Tasks + Notes ↔ PlannerService."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Signal

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Task
from maira.core.domain.value_objects import Priority, TaskStatus
from maira.core.interfaces.planner import Planner
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.chat import format_due, is_overdue
from maira.ui.prototype.screens.notes import NotesScreen
from maira.ui.prototype.screens.tasks import TasksScreen


def _task_section(task: Task, now: datetime) -> str:
  if task.status == TaskStatus.DONE:
    return "Completed"
  if task.due_at is not None and task.due_at.astimezone(LOCAL_TZ).date() > now.date():
    return "Upcoming"
  return "Today"  # due today, overdue, or no date


def _task_meta(task: Task, now: datetime) -> str:
  parts = []
  if task.due_at is not None:
    due = format_due(task.due_at, now)
    parts.append(f"{due[:1].upper()}{due[1:]}")
  if is_overdue(task, now):
    parts.append("Overdue")
  return " · ".join(parts) or "No date"


class ProtoPlannerBridge(QObject):
  # Chat changes tasks on a worker thread; refresh the screens on the UI thread.
  _changed = Signal()

  def __init__(
    self,
    planner: Planner,
    tasks: TasksScreen,
    notes: NotesScreen,
    event_bus: EventBus | None = None,
  ) -> None:
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

    self._changed.connect(self.refresh)
    if event_bus is not None:
      event_bus.subscribe("planner.changed", lambda _p: self._changed.emit())

    self.refresh()

  def refresh(self) -> None:
    now = datetime.now(LOCAL_TZ)
    task_rows = []
    for task in self._planner.list_tasks():
      task_rows.append(
        {
          "id": task.id,
          "title": task.title,
          "section": _task_section(task, now),
          "time": _task_meta(task, now),
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
