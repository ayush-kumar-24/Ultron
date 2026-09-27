"""Unit tests for memory store."""

from pathlib import Path

import pytest

from maira.core.domain.value_objects import MemoryCategory
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import (
  apply_migrations,
  current_version,
  discover_migrations,
)
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
  assert applied == [v for v, _ in discover_migrations()]
  assert current_version(storage) == discover_migrations()[-1][0]
  storage.close()


def test_legacy_plural_categories_load_after_migration(tmp_path) -> None:
  """Old builds stored e.g. 'conversations'; startup must not crash on them."""
  from maira.core.domain.value_objects import MemoryCategory
  from maira.infrastructure.persistence.sqlite.migrations import MIGRATIONS_DIR
  from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository

  storage = SqliteStorage(tmp_path / "legacy.db")
  # Database as an older build left it: migrations 1-4 only.
  legacy_dir = tmp_path / "legacy_migrations"
  legacy_dir.mkdir()
  for version, path in discover_migrations():
    if version <= 4:
      (legacy_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
  apply_migrations(storage, legacy_dir)
  for i, category in enumerate(["conversations", "Projects", " preference ", "weird"]):
    storage.execute(
      "INSERT INTO memories (id, category, title, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
      (f"m{i}", category, "t", "b", "2026-09-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00"),
    )

  apply_migrations(storage)

  rows = dict(storage.fetchall("SELECT id, category FROM memories"))
  assert rows == {"m0": "conversation", "m1": "project", "m2": "preference", "m3": "note"}
  categories = {m.id: m.category for m in MemoryRepository(storage).list_memories()}
  assert categories["m0"] == MemoryCategory.CONVERSATION
  storage.close()


def test_unknown_category_never_crashes_loading() -> None:
  from maira.core.domain.value_objects import MemoryCategory
  from maira.infrastructure.persistence.sqlite.repositories import parse_memory_category

  assert parse_memory_category("conversations") == MemoryCategory.CONVERSATION
  assert parse_memory_category("Ideas") == MemoryCategory.IDEA
  assert parse_memory_category("task") == MemoryCategory.TASK
  assert parse_memory_category("???") == MemoryCategory.NOTE
  assert parse_memory_category(None) == MemoryCategory.NOTE
