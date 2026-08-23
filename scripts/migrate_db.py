"""Apply pending SQLite schema migrations."""

from __future__ import annotations

import sys

from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations, current_version
from maira.shared.utils.paths import database_path


def main() -> int:
  path = database_path()
  storage = SqliteStorage(path)
  try:
    before = current_version(storage)
    applied = apply_migrations(storage)
    after = current_version(storage)
  finally:
    storage.close()

  print(f"Database: {path}")
  if applied:
    print(f"Applied migrations: {', '.join(str(v) for v in applied)}")
  else:
    print("No pending migrations.")
  print(f"Schema version: {before} -> {after}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
