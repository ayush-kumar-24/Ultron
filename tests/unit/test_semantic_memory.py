"""Unit tests for semantic memory recall with fake encoder/vector store."""

from pathlib import Path
from typing import Any

import pytest

from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.embeddings import EmbeddingEncoder
from maira.core.interfaces.vector_store import VectorMatch, VectorStore
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository
from maira.modules.memory.service import MemoryService


class FakeEncoder(EmbeddingEncoder):
  def __init__(self) -> None:
    self.calls: list[str] = []

  def is_available(self) -> bool:
    return True

  def encode(self, text: str) -> list[float]:
    self.calls.append(text)
    lowered = text.lower()
    # crude bag-of-words style vector for tests
    return [
      float("vscode" in lowered or "editor" in lowered or "coding" in lowered),
      float("dark" in lowered or "theme" in lowered),
      float(len(lowered.split())),
    ]

  def encode_batch(self, texts: list[str]) -> list[list[float]]:
    return [self.encode(text) for text in texts]


class FakeVectorStore(VectorStore):
  def __init__(self) -> None:
    self.items: dict[str, tuple[list[float], dict[str, Any]]] = {}

  def is_available(self) -> bool:
    return True

  def upsert(
    self,
    *,
    item_id: str,
    embedding: list[float],
    document: str,
    metadata: dict[str, Any] | None = None,
  ) -> None:
    self.items[item_id] = (embedding, metadata or {})

  def delete(self, item_id: str) -> None:
    self.items.pop(item_id, None)

  def query(
    self,
    embedding: list[float],
    *,
    k: int = 5,
    where: dict[str, Any] | None = None,
  ) -> list[VectorMatch]:
    scored: list[VectorMatch] = []
    for item_id, (vector, metadata) in self.items.items():
      if where:
        skip = False
        for key, value in where.items():
          if metadata.get(key) != value:
            skip = True
            break
        if skip:
          continue
      score = sum(a * b for a, b in zip(embedding, vector))
      scored.append(VectorMatch(id=item_id, score=float(score), metadata=metadata))
    scored.sort(key=lambda match: match.score, reverse=True)
    return scored[:k]


@pytest.fixture
def memory(tmp_path: Path) -> MemoryService:
  storage = SqliteStorage(tmp_path / "semantic.db")
  apply_migrations(storage)
  return MemoryService(
    MemoryRepository(storage),
    encoder=FakeEncoder(),
    vector_store=FakeVectorStore(),
  )


def test_store_indexes_and_semantic_recall(memory: MemoryService) -> None:
  memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Editor",
    body="I use VS Code every day",
  )
  memory.store(
    category=MemoryCategory.IDEA,
    title="Theme",
    body="I prefer dark mode",
  )

  hits = memory.recall("coding editor", k=2)
  assert hits
  assert hits[0].title == "Editor"


def test_delete_removes_vector(memory: MemoryService) -> None:
  entry = memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Editor",
    body="I use VS Code",
  )
  memory.delete(entry.id)
  assert memory.recall("coding editor", k=5) == []


def test_falls_back_to_keyword_without_semantic(tmp_path: Path) -> None:
  storage = SqliteStorage(tmp_path / "keyword.db")
  apply_migrations(storage)
  service = MemoryService(MemoryRepository(storage))
  service.store(
    category=MemoryCategory.PREFERENCE,
    title="Editor",
    body="I use VS Code",
  )
  assert service.is_semantic_available() is False
  hits = service.search("VS Code")
  assert len(hits) == 1
  assert hits[0].title == "Editor"
