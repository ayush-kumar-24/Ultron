"""Named ChromaDB collections for memories and later document indexes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from maira.core.interfaces.vector_store import VectorMatch, VectorStore
from maira.infrastructure.vector.chromadb.client import create_chroma_client


class ChromaVectorStore(VectorStore):
  def __init__(self, path: str | Path, collection_name: str = "memories") -> None:
    self._path = Path(path)
    self._collection_name = collection_name
    self._collection = None
    self._failed = False

  def is_available(self) -> bool:
    if self._failed:
      return False
    try:
      self._ensure_collection()
      return self._collection is not None
    except Exception as exc:  # noqa: BLE001
      logger.warning("Vector store unavailable: {}", exc)
      self._failed = True
      return False

  def upsert(
    self,
    *,
    item_id: str,
    embedding: list[float],
    document: str,
    metadata: dict[str, Any] | None = None,
  ) -> None:
    collection = self._ensure_collection()
    collection.upsert(
      ids=[item_id],
      embeddings=[embedding],
      documents=[document],
      metadatas=[metadata or {}],
    )

  def delete(self, item_id: str) -> None:
    collection = self._ensure_collection()
    try:
      collection.delete(ids=[item_id])
    except Exception:  # noqa: BLE001 — missing ids are fine
      return

  def query(
    self,
    embedding: list[float],
    *,
    k: int = 5,
    where: dict[str, Any] | None = None,
  ) -> list[VectorMatch]:
    collection = self._ensure_collection()
    kwargs: dict[str, Any] = {
      "query_embeddings": [embedding],
      "n_results": max(1, k),
      "include": ["distances", "metadatas"],
    }
    if where:
      kwargs["where"] = where

    result = collection.query(**kwargs)
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]

    matches: list[VectorMatch] = []
    for item_id, distance, metadata in zip(ids, distances, metadatas):
      score = 1.0 - float(distance)
      matches.append(
        VectorMatch(
          id=str(item_id),
          score=score,
          metadata=dict(metadata or {}),
        )
      )
    return matches

  def _ensure_collection(self):
    if self._collection is not None:
      return self._collection
    client = create_chroma_client(self._path)
    self._collection = client.get_or_create_collection(
      name=self._collection_name,
      metadata={"hnsw:space": "cosine"},
    )
    return self._collection
