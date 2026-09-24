"""Planner facade — task and note operations."""

from datetime import datetime

from maira.core.domain.entities import Note, Task
from maira.core.domain.value_objects import Priority, TaskStatus
from maira.core.interfaces.planner import Planner
from maira.infrastructure.persistence.sqlite.repositories import NoteRepository, TaskRepository
from maira.modules.planner.notes import NotesService
from maira.modules.planner.todos import TodoService


class PlannerService(Planner):
  def __init__(
    self,
    task_repository: TaskRepository,
    note_repository: NoteRepository,
  ) -> None:
    self._todos = TodoService(task_repository)
    self._notes = NotesService(note_repository)

  def list_tasks(self) -> list[Task]:
    return self._todos.list_tasks()

  def add_task(
    self,
    title: str,
    *,
    priority: Priority = Priority.MEDIUM,
    due_at: datetime | None = None,
  ) -> Task:
    return self._todos.add_task(title, priority=priority, due_at=due_at)

  def get_task(self, task_id: str) -> Task | None:
    return self._todos.get(task_id)

  def set_task_due(self, task_id: str, due_at: datetime | None) -> Task | None:
    return self._todos.set_due(task_id, due_at)

  def set_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
    return self._todos.set_status(task_id, status)

  def set_task_priority(self, task_id: str, priority: Priority) -> Task | None:
    return self._todos.set_priority(task_id, priority)

  def delete_task(self, task_id: str) -> None:
    self._todos.delete(task_id)

  def list_notes(self) -> list[Note]:
    return self._notes.list_notes()

  def add_note(self, title: str, body: str = "") -> Note:
    return self._notes.add_note(title, body)

  def update_note(self, note_id: str, *, title: str, body: str) -> Note | None:
    return self._notes.update_note(note_id, title=title, body=body)

  def delete_note(self, note_id: str) -> None:
    self._notes.delete_note(note_id)

  def get_note(self, note_id: str) -> Note | None:
    return self._notes.get_note(note_id)
