"""Vector store port — embedding storage and similarity search."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VectorMatch:
  id: str
  score: float
  metadata: dict[str, Any]


class VectorStore(ABC):
  @abstractmethod
  def is_available(self) -> bool:
    """Return True when the vector index can be queried."""

  @abstractmethod
  def upsert(
    self,
    *,
    item_id: str,
    embedding: list[float],
    document: str,
    metadata: dict[str, Any] | None = None,
  ) -> None:
    """Insert or replace a vector by id."""

  @abstractmethod
  def delete(self, item_id: str) -> None:
    """Remove a vector by id (no-op if missing)."""

  @abstractmethod
  def query(
    self,
    embedding: list[float],
    *,
    k: int = 5,
    where: dict[str, Any] | None = None,
  ) -> list[VectorMatch]:
    """Return top-k similar ids with scores (higher is better)."""
