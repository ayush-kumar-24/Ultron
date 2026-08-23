"""SQLite connection factory and transaction helpers."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from maira.core.interfaces.storage import Storage


class SqliteStorage(Storage):
  """Thread-safe SQLite storage using a single connection and a lock."""

  def __init__(self, db_path: Path | str) -> None:
    self._path = Path(db_path)
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.RLock()
    self._conn = sqlite3.connect(
      self._path,
      check_same_thread=False,
      isolation_level=None,
    )
    self._conn.row_factory = sqlite3.Row
    self._conn.execute("PRAGMA foreign_keys = ON")
    self._conn.execute("PRAGMA journal_mode = WAL")

  @property
  def path(self) -> Path:
    return self._path

  def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
    with self._lock:
      self._conn.execute(sql, params)

  def executescript(self, sql: str) -> None:
    with self._lock:
      self._conn.executescript(sql)

  def fetchone(self, sql: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
    with self._lock:
      cursor = self._conn.execute(sql, params)
      row = cursor.fetchone()
      return tuple(row) if row is not None else None

  def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
    with self._lock:
      cursor = self._conn.execute(sql, params)
      return [tuple(row) for row in cursor.fetchall()]

  @contextmanager
  def transaction(self) -> Iterator[None]:
    with self._lock:
      self._conn.execute("BEGIN")
      try:
        yield
        self._conn.execute("COMMIT")
      except Exception:
        self._conn.execute("ROLLBACK")
        raise

  def close(self) -> None:
    with self._lock:
      self._conn.close()
