"""Turn a typed line into a task — the server side of `POST /tasks/parse`.

Mirrors the behaviour the frontend's mock parser established, so the same
sentence produces the same task whether the UI runs against mock or live data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

_WEEKDAYS = (
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
)

_RECURRENCE_RE = re.compile(
  r"every (day|morning|evening|week|" + "|".join(_WEEKDAYS) + r")",
  re.I,
)
_TIME_RE = re.compile(r"\b(?:at )?(\d{1,2})(?::(\d{2}))?\s?(am|pm)\b", re.I)
_WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.I)
_HIGH_RE = re.compile(r"urgent|asap|important|high priority", re.I)
_LOW_RE = re.compile(r"low priority|whenever|someday", re.I)
_RELATIVE_RE = re.compile(r"tomorrow|next week|today|tonight", re.I)
_EVENING_RE = re.compile(r"tonight|evening", re.I)
_LEAD_RE = re.compile(
  r"^(remind me(\s+to\b)?|create (a )?task(\s+to\b)?|add (a )?task(\s+to\b)?|todo:?)\s*",
  re.I,
)
_STRIP_WHEN_RE = re.compile(
  r"\b(every (day|morning|evening|week|" + "|".join(_WEEKDAYS) + r")|tomorrow|next week|tonight|today)\b",
  re.I,
)
_STRIP_TIME_RE = re.compile(r"\b(at )?\d{1,2}(:\d{2})?\s?(am|pm)\b", re.I)
_IN_MINUTES_RE = re.compile(r"\bin (\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)\b", re.I)


@dataclass
class ParsedTask:
  title: str
  priority: str = "medium"
  due: datetime | None = None
  recurrence: str | None = None
  project_id: str | None = None
  tags: list[str] = field(default_factory=list)

  def to_api(self) -> dict[str, Any]:
    from maira.api.mapping import iso

    return {
      "title": self.title,
      "priority": self.priority,
      "due": iso(self.due),
      "recurrence": self.recurrence,
      "projectId": self.project_id,
      "tags": list(self.tags),
    }


def _title_case_recurrence(match: str) -> str:
  return " ".join(word.capitalize() for word in match.split())


def parse_task(text: str, *, now: datetime | None = None) -> ParsedTask:
  raw = " ".join((text or "").split())
  if not raw:
    return ParsedTask(title="Untitled")

  lower = raw.lower()
  moment = now or datetime.now().astimezone()
  due: datetime | None = None

  recurrence_match = _RECURRENCE_RE.search(lower)
  recurrence = _title_case_recurrence(recurrence_match.group(0)) if recurrence_match else None

  relative = _IN_MINUTES_RE.search(lower)
  if relative:
    amount = int(relative.group(1))
    unit = relative.group(2).lower()
    delta = timedelta(hours=amount) if unit.startswith(("hour", "hr")) else timedelta(minutes=amount)
    due = moment + delta
  else:
    target = moment
    if "tomorrow" in lower:
      target = target + timedelta(days=1)
    elif "next week" in lower:
      target = target + timedelta(days=7)

    weekday_match = _WEEKDAY_RE.search(lower)
    if weekday_match:
      wanted = _WEEKDAYS.index(weekday_match.group(1).lower())
      # Python: Monday=0. Shift so a named day always lands in the future.
      ahead = (wanted - target.weekday() + 7) % 7 or 7
      target = target + timedelta(days=ahead)

    time_match = _TIME_RE.search(lower)
    if time_match:
      hour = int(time_match.group(1))
      minute = int(time_match.group(2) or 0)
      meridiem = time_match.group(3).lower()
      if meridiem == "pm" and hour < 12:
        hour += 12
      if meridiem == "am" and hour == 12:
        hour = 0
      target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
      due = target
    elif weekday_match or _RELATIVE_RE.search(lower):
      hour = 20 if _EVENING_RE.search(lower) else 9
      due = target.replace(hour=hour, minute=0, second=0, microsecond=0)

  priority = "medium"
  if _HIGH_RE.search(lower):
    priority = "high"
  elif _LOW_RE.search(lower):
    priority = "low"

  title = _LEAD_RE.sub("", raw)
  title = _STRIP_WHEN_RE.sub("", title)
  title = _STRIP_TIME_RE.sub("", title)
  title = _IN_MINUTES_RE.sub("", title)
  title = re.sub(r"\s{2,}", " ", title)
  title = re.sub(r"^\s*(to|,)\s*", "", title, flags=re.I).strip(" ,")
  if not title:
    title = raw
  title = title[0].upper() + title[1:]

  return ParsedTask(
    title=title,
    priority=priority,
    due=due,
    recurrence=recurrence,
  )
