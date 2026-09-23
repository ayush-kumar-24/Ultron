"""When to show the daily briefing, and remembering that it was shown."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

from loguru import logger


def parse_clock(value: str, default: time) -> time:
  try:
    hour, minute = str(value).strip().split(":")
    return time(int(hour), int(minute))
  except (ValueError, TypeError):
    logger.warning("Invalid briefing time {!r}; using {}", value, default.strftime("%H:%M"))
    return default


class BriefingSchedule:
  """Once a day, at ``at`` or the first time Ultron runs after it (until ``until``).

  If the PC was off at 8:00 and starts at 9:30, the briefing still shows;
  after ``until`` it waits for tomorrow ("plan my day" works any time).
  """

  def __init__(self, state_path: Path, *, at: time, until: time) -> None:
    self._path = state_path
    self._at = at
    self._until = until if until > at else time(23, 59)

  def is_due(self, now: datetime) -> bool:
    local = now.time()
    if local < self._at or local > self._until:
      return False
    return self.last_shown() != now.date()

  def last_shown(self) -> date | None:
    try:
      data = json.loads(self._path.read_text(encoding="utf-8"))
      return date.fromisoformat(str(data.get("last_shown")))
    except (OSError, ValueError, TypeError, AttributeError):
      return None

  def mark_shown(self, day: date) -> None:
    try:
      self._path.parent.mkdir(parents=True, exist_ok=True)
      self._path.write_text(json.dumps({"last_shown": day.isoformat()}), encoding="utf-8")
    except OSError:
      logger.exception("Could not save briefing state")
