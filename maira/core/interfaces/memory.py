"""Memory port — persistent storage and retrieval of user knowledge."""

from __future__ import annotations

from abc import ABC, abstractmethod

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory


class Memory(ABC):
  @abstractmethod
  def store(
    self,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry:
    """Create a memory entry."""

  @abstractmethod
  def get(self, memory_id: str) -> MemoryEntry | None:
    """Fetch one memory by id."""

  @abstractmethod
  def list_memories(
    self,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    """List memories, optionally filtered by category."""

  @abstractmethod
  def search_keyword(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    """Keyword search over title and body."""

  @abstractmethod
  def recall(
    self,
    query: str,
    *,
    k: int = 5,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    """Semantic recall with keyword fallback."""

  @abstractmethod
  def search(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    """User-facing search (semantic with keyword fallback)."""

  @abstractmethod
  def update(
    self,
    memory_id: str,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry | None:
    """Update an existing memory."""

  @abstractmethod
  def delete(self, memory_id: str) -> None:
    """Delete a memory permanently."""

  @abstractmethod
  def is_semantic_available(self) -> bool:
    """Return True when semantic indexing/search is active."""
