"""Structured memory persistence — SQLite-backed records."""

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository


class MemoryStore:
  def __init__(self, repository: MemoryRepository) -> None:
    self._repo = repository

  def store(
    self,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry:
    cleaned_title = title.strip()
    if not cleaned_title and not body.strip():
      raise ValueError("Memory title or body is required")
    return self._repo.create(category=category, title=cleaned_title or "Untitled", body=body)

  def get(self, memory_id: str) -> MemoryEntry | None:
    return self._repo.get(memory_id)

  def list_memories(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
    return self._repo.list_memories(category)

  def search_keyword(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    return self._repo.search_keyword(query, category=category)

  def update(
    self,
    memory_id: str,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry | None:
    cleaned_title = title.strip()
    if not cleaned_title and not body.strip():
      raise ValueError("Memory title or body is required")
    return self._repo.update(
      memory_id,
      category=category,
      title=cleaned_title or "Untitled",
      body=body,
    )

  def delete(self, memory_id: str) -> None:
    self._repo.delete(memory_id)
