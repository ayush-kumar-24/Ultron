"""Unit tests for memory store."""

from pathlib import Path

import pytest

from maira.core.domain.value_objects import MemoryCategory
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations, current_version
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository
from maira.modules.memory.service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> MemoryService:
  storage = SqliteStorage(tmp_path / "memory.db")
  apply_migrations(storage)
  assert current_version(storage) >= 3
  return MemoryService(MemoryRepository(storage))


def test_store_list_and_filter(memory: MemoryService) -> None:
  memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Dark mode",
    body="I prefer dark mode",
  )
  memory.store(
    category=MemoryCategory.IDEA,
    title="Side project",
    body="Build a local AI OS",
  )

  all_items = memory.list_memories()
  prefs = memory.list_memories(MemoryCategory.PREFERENCE)
  assert len(all_items) == 2
  assert len(prefs) == 1
  assert prefs[0].title == "Dark mode"


def test_keyword_search(memory: MemoryService) -> None:
  memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Editor",
    body="I use VS Code daily",
  )
  memory.store(
    category=MemoryCategory.PROJECT,
    title="Maira",
    body="Offline personal AI",
  )

  hits = memory.search_keyword("VS Code")
  assert len(hits) == 1
  assert hits[0].title == "Editor"

  filtered = memory.search_keyword("offline", category=MemoryCategory.PROJECT)
  assert len(filtered) == 1
  assert filtered[0].title == "Maira"


def test_update_and_delete(memory: MemoryService) -> None:
  entry = memory.store(
    category=MemoryCategory.IDEA,
    title="Draft",
    body="v1",
  )
  updated = memory.update(
    entry.id,
    category=MemoryCategory.PROJECT,
    title="Draft v2",
    body="v2",
  )
  assert updated is not None
  assert updated.category == MemoryCategory.PROJECT
  assert updated.title == "Draft v2"

  memory.delete(entry.id)
  assert memory.get(entry.id) is None
  assert memory.list_memories() == []


def test_empty_memory_rejected(memory: MemoryService) -> None:
  with pytest.raises(ValueError):
    memory.store(category=MemoryCategory.IDEA, title="  ", body="  ")


def test_migration_three_on_fresh_db(tmp_path: Path) -> None:
  storage = SqliteStorage(tmp_path / "fresh.db")
  applied = apply_migrations(storage)
  assert applied == [1, 2, 3, 4, 5]
  assert current_version(storage) == 5
  storage.close()
