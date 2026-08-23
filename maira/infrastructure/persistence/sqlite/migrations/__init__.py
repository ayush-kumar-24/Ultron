"""Schema migration scripts and version tracking for SQLite."""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from maira.infrastructure.persistence.sqlite.connection import SqliteStorage

MIGRATIONS_DIR = Path(__file__).resolve().parent
_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")


def _ensure_migrations_table(storage: SqliteStorage) -> None:
  storage.execute(
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """
  )


def _applied_versions(storage: SqliteStorage) -> set[int]:
  rows = storage.fetchall("SELECT version FROM schema_migrations")
  return {int(row[0]) for row in rows}


def discover_migrations(directory: Path | None = None) -> list[tuple[int, Path]]:
  root = directory or MIGRATIONS_DIR
  found: list[tuple[int, Path]] = []
  for path in sorted(root.glob("*.sql")):
    match = _VERSION_RE.match(path.name)
    if not match:
      continue
    found.append((int(match.group(1)), path))
  return found


def current_version(storage: SqliteStorage) -> int:
  _ensure_migrations_table(storage)
  row = storage.fetchone("SELECT MAX(version) FROM schema_migrations")
  if row is None or row[0] is None:
    return 0
  return int(row[0])


def apply_migrations(
  storage: SqliteStorage,
  directory: Path | None = None,
) -> list[int]:
  """Apply pending ``NNN_name.sql`` migrations. Returns applied version numbers."""
  _ensure_migrations_table(storage)
  applied = _applied_versions(storage)
  newly_applied: list[int] = []

  for version, path in discover_migrations(directory):
    if version in applied:
      continue

    sql = path.read_text(encoding="utf-8")
    logger.info("Applying migration {} ({})", version, path.name)

    with storage.transaction():
      # executescript issues implicit commits; run statements individually instead.
      for statement in _split_sql_statements(sql):
        storage.execute(statement)
      storage.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)",
        (version,),
      )

    newly_applied.append(version)

  return newly_applied


def _split_sql_statements(sql: str) -> list[str]:
  """Split a SQL file into individual statements, skipping empty / comment-only chunks."""
  statements: list[str] = []
  for chunk in sql.split(";"):
    cleaned_lines = [
      line
      for line in chunk.splitlines()
      if line.strip() and not line.strip().startswith("--")
    ]
    statement = "\n".join(cleaned_lines).strip()
    if statement:
      statements.append(statement)
  return statements
