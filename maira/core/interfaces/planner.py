"""Planner port — todos, notes, and later reminders/briefing."""

from abc import ABC, abstractmethod
from datetime import datetime

from maira.core.domain.entities import Note, Task
from maira.core.domain.value_objects import Priority, TaskStatus


class Planner(ABC):
  @abstractmethod
  def list_tasks(self) -> list[Task]:
    """Return tasks ordered for daily use."""

  @abstractmethod
  def add_task(
    self,
    title: str,
    *,
    priority: Priority = Priority.MEDIUM,
    due_at: datetime | None = None,
  ) -> Task:
    """Create a new open task."""

  @abstractmethod
  def set_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
    """Mark a task open or done."""

  @abstractmethod
  def set_task_priority(self, task_id: str, priority: Priority) -> Task | None:
    """Update task priority."""

  @abstractmethod
  def delete_task(self, task_id: str) -> None:
    """Delete a task permanently."""

  @abstractmethod
  def list_notes(self) -> list[Note]:
    """Return notes newest first."""

  @abstractmethod
  def add_note(self, title: str, body: str = "") -> Note:
    """Create a note."""

  @abstractmethod
  def update_note(self, note_id: str, *, title: str, body: str) -> Note | None:
    """Update note title and body."""

  @abstractmethod
  def delete_note(self, note_id: str) -> None:
    """Delete a note permanently."""

  @abstractmethod
  def get_note(self, note_id: str) -> Note | None:
    """Fetch a single note."""
