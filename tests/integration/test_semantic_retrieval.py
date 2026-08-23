"""Integration tests for real sentence-transformers + ChromaDB retrieval."""

from pathlib import Path

import pytest

from maira.core.domain.value_objects import MemoryCategory
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import MemoryRepository
from maira.modules.memory.service import MemoryService

pytest.importorskip("sentence_transformers")
pytest.importorskip("chromadb")

from maira.infrastructure.embeddings.sentence_transformers.encoder import (  # noqa: E402
  SentenceTransformerEncoder,
)
from maira.infrastructure.vector.chromadb.collections import ChromaVectorStore  # noqa: E402


@pytest.mark.integration
def test_semantic_retrieval_round_trip(tmp_path: Path) -> None:
  storage = SqliteStorage(tmp_path / "mem.db")
  apply_migrations(storage)
  encoder = SentenceTransformerEncoder("sentence-transformers/all-MiniLM-L6-v2")
  vectors = ChromaVectorStore(tmp_path / "chroma")
  if not encoder.is_available() or not vectors.is_available():
    pytest.skip("Semantic dependencies unavailable")

  memory = MemoryService(
    MemoryRepository(storage),
    encoder=encoder,
    vector_store=vectors,
  )
  memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Editor choice",
    body="I use VS Code for almost all coding work",
  )
  memory.store(
    category=MemoryCategory.IDEA,
    title="Lunch",
    body="I like pasta on Fridays",
  )

  hits = memory.recall("coding editor", k=2)
  assert hits
  assert "VS Code" in hits[0].body or hits[0].title == "Editor choice"
