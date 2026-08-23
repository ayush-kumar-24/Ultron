"""Memory facade — store, query, and forget operations."""

from __future__ import annotations

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.embeddings import EmbeddingEncoder
from maira.core.interfaces.memory import Memory
from maira.core.interfaces.vector_store import VectorStore
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository
from maira.modules.memory.retrieval import MemoryRetrieval
from maira.modules.memory.store import MemoryStore


class MemoryService(Memory):
  def __init__(
    self,
    repository: MemoryRepository,
    encoder: EmbeddingEncoder | None = None,
    vector_store: VectorStore | None = None,
  ) -> None:
    self._store = MemoryStore(repository)
    self._retrieval = MemoryRetrieval(repository, encoder=encoder, vector_store=vector_store)

  def store(
    self,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry:
    entry = self._store.store(category=category, title=title, body=body)
    self._retrieval.index(entry)
    return entry

  def get(self, memory_id: str) -> MemoryEntry | None:
    return self._store.get(memory_id)

  def list_memories(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
    return self._store.list_memories(category)

  def search_keyword(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    return self._store.search_keyword(query, category=category)

  def recall(
    self,
    query: str,
    *,
    k: int = 5,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    return self._retrieval.recall(query, k=k, category=category)

  def search(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    """Semantic search with keyword fallback."""
    return self.recall(query, k=20, category=category)

  def update(
    self,
    memory_id: str,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry | None:
    entry = self._store.update(memory_id, category=category, title=title, body=body)
    if entry is not None:
      self._retrieval.index(entry)
    return entry

  def delete(self, memory_id: str) -> None:
    self._store.delete(memory_id)
    self._retrieval.remove(memory_id)

  def is_semantic_available(self) -> bool:
    return self._retrieval.is_semantic_available()
