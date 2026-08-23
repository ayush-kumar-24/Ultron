"""Relational storage port — SQLite-backed CRUD and transactional access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any, Sequence


class Storage(ABC):
  @abstractmethod
  def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
    """Execute a write statement."""

  @abstractmethod
  def fetchone(self, sql: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
    """Fetch a single row."""

  @abstractmethod
  def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
    """Fetch all matching rows."""

  @abstractmethod
  def transaction(self) -> AbstractContextManager[None]:
    """Context manager wrapping a commit/rollback transaction."""

  @abstractmethod
  def close(self) -> None:
    """Close the underlying connection."""
