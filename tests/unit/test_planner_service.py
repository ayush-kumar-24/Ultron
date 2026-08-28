"""Unit tests for planner service (todos + notes)."""

from pathlib import Path

import pytest

from maira.core.domain.value_objects import Priority, TaskStatus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations, current_version
from maira.infrastructure.persistence.sqlite.repositories import NoteRepository, TaskRepository
from maira.modules.planner.service import PlannerService


@pytest.fixture
def planner(tmp_path: Path) -> PlannerService:
  storage = SqliteStorage(tmp_path / "planner.db")
  apply_migrations(storage)
  assert current_version(storage) >= 2
  return PlannerService(TaskRepository(storage), NoteRepository(storage))


def test_task_crud_and_complete(planner: PlannerService) -> None:
  first = planner.add_task("Buy milk", priority=Priority.HIGH)
  second = planner.add_task("Write docs", priority=Priority.LOW)
  assert first.status == TaskStatus.OPEN

  planner.set_task_status(first.id, TaskStatus.DONE)
  planner.delete_task(second.id)

  tasks = planner.list_tasks()
  assert len(tasks) == 1
  assert tasks[0].id == first.id
  assert tasks[0].status == TaskStatus.DONE
  assert tasks[0].priority == Priority.HIGH


def test_task_priority_update(planner: PlannerService) -> None:
  task = planner.add_task("Ship feature")
  updated = planner.set_task_priority(task.id, Priority.HIGH)
  assert updated is not None
  assert updated.priority == Priority.HIGH


def test_empty_task_title_rejected(planner: PlannerService) -> None:
  with pytest.raises(ValueError):
    planner.add_task("   ")


def test_note_crud(planner: PlannerService) -> None:
  note = planner.add_note("Ideas", "first draft")
  saved = planner.update_note(note.id, title="Ideas v2", body="revised")
  assert saved is not None
  assert saved.title == "Ideas v2"
  assert saved.body == "revised"

  notes = planner.list_notes()
  assert len(notes) == 1
  assert notes[0].title == "Ideas v2"

  planner.delete_note(note.id)
  assert planner.list_notes() == []
  assert planner.get_note(note.id) is None


def test_migration_two_applies_on_fresh_db(tmp_path: Path) -> None:
  storage = SqliteStorage(tmp_path / "fresh.db")
  applied = apply_migrations(storage)
  assert 1 in applied
  assert 2 in applied
  assert 3 in applied
  assert 4 in applied
  assert 5 in applied
  assert current_version(storage) == 5
  storage.close()
