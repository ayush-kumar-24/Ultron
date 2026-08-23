"""Domain events for cross-module notifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
  return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ContextAssembled:
  query: str
  memory_ids: tuple[str, ...]
  memory_titles: tuple[str, ...]
  char_count: int
  timestamp: datetime = field(default_factory=_utc_now)
