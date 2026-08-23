"""Semantic memory retrieval over the vector index."""

from __future__ import annotations

from loguru import logger

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.embeddings import EmbeddingEncoder
from maira.core.interfaces.vector_store import VectorStore
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository


def memory_document(entry: MemoryEntry) -> str:
  return f"{entry.title}\n{entry.body}".strip()


class MemoryRetrieval:
  def __init__(
    self,
    repository: MemoryRepository,
    encoder: EmbeddingEncoder | None = None,
    vector_store: VectorStore | None = None,
  ) -> None:
    self._repo = repository
    self._encoder = encoder
    self._vectors = vector_store

  def is_semantic_available(self) -> bool:
    return bool(
      self._encoder
      and self._vectors
      and self._encoder.is_available()
      and self._vectors.is_available()
    )

  def index(self, entry: MemoryEntry) -> None:
    if not self.is_semantic_available():
      return
    assert self._encoder is not None
    assert self._vectors is not None
    try:
      embedding = self._encoder.encode(memory_document(entry))
      self._vectors.upsert(
        item_id=entry.id,
        embedding=embedding,
        document=memory_document(entry),
        metadata={"category": entry.category.value, "title": entry.title},
      )
    except Exception as exc:  # noqa: BLE001
      logger.warning("Failed to index memory {}: {}", entry.id, exc)

  def remove(self, memory_id: str) -> None:
    if not self._vectors or not self._vectors.is_available():
      return
    try:
      self._vectors.delete(memory_id)
    except Exception as exc:  # noqa: BLE001
      logger.warning("Failed to remove memory vector {}: {}", memory_id, exc)

  def recall(
    self,
    query: str,
    *,
    k: int = 5,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    cleaned = query.strip()
    if not cleaned:
      return []

    if self.is_semantic_available():
      try:
        return self._semantic_recall(cleaned, k=k, category=category)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Semantic recall failed, falling back to keyword: {}", exc)

    return self._repo.search_keyword(cleaned, category=category)[:k]

  def _semantic_recall(
    self,
    query: str,
    *,
    k: int,
    category: MemoryCategory | None,
  ) -> list[MemoryEntry]:
    assert self._encoder is not None
    assert self._vectors is not None

    embedding = self._encoder.encode(query)
    where = {"category": category.value} if category is not None else None
    matches = self._vectors.query(embedding, k=k, where=where)

    entries: list[MemoryEntry] = []
    for match in matches:
      entry = self._repo.get(match.id)
      if entry is None:
        continue
      if category is not None and entry.category != category:
        continue
      entries.append(entry)
    return entries
