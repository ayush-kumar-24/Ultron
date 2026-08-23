"""Todo submodule — task CRUD helpers."""

from datetime import datetime

from maira.core.domain.entities import Task
from maira.core.domain.value_objects import Priority, TaskStatus
from maira.infrastructure.persistence.sqlite.repositories import TaskRepository


class TodoService:
  def __init__(self, repository: TaskRepository) -> None:
    self._repo = repository

  def list_tasks(self) -> list[Task]:
    return self._repo.list_tasks()

  def add_task(
    self,
    title: str,
    *,
    priority: Priority = Priority.MEDIUM,
    due_at: datetime | None = None,
  ) -> Task:
    cleaned = title.strip()
    if not cleaned:
      raise ValueError("Task title cannot be empty")
    return self._repo.create(cleaned, priority=priority, due_at=due_at)

  def set_status(self, task_id: str, status: TaskStatus) -> Task | None:
    return self._repo.set_status(task_id, status)

  def set_priority(self, task_id: str, priority: Priority) -> Task | None:
    return self._repo.set_priority(task_id, priority)

  def delete(self, task_id: str) -> None:
    self._repo.delete(task_id)
