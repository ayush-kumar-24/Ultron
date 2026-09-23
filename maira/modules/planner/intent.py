"""Understand task / note commands typed or spoken in chat (English + Hinglish).

Pure parsing, no side effects: ``parse_planner_request`` returns a
``PlannerIntent`` or None (the message goes to the LLM instead).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum

from maira.core.domain.value_objects import Priority
from maira.modules.automation.parser import LOCAL_TZ, _parse_run_at

# A due date without a clock time is stored at 23:59 local ("any time that day").
DATE_ONLY_TIME = time(23, 59)


class PlannerAction(str, Enum):
  ADD_TASK = "add_task"
  LIST_TASKS = "list_tasks"
  COMPLETE_TASK = "complete_task"
  DELETE_TASK = "delete_task"
  ADD_NOTE = "add_note"
  BRIEFING = "briefing"


@dataclass(frozen=True)
class PlannerIntent:
  action: PlannerAction
  text: str = ""  # task title / task reference / note text
  due_at: datetime | None = None
  priority: Priority = Priority.MEDIUM
  today_only: bool = False
  # Loose phrasing ("pay bill ho gaya"): act only if a task clearly matches.
  strict: bool = True


_F = re.IGNORECASE
_KARO = r"(?:\s+(?:karo|kar\s+do|kardo|do|please))?"

_ADD_PATTERNS = [
  re.compile(r"^(?:please\s+)?(?:add|create|new|make)\s+(?:a\s+)?(?:new\s+)?(?:task|todo|to-do)\s*(?:[:\-]\s*|\s+)(?P<t>.+)$", _F),
  re.compile(r"^(?:task|todo|to-do)\s*[:\-]\s*(?P<t>.+)$", _F),
  re.compile(r"^(?:task|todo)\s+(?:add|bana(?:o|na)?)" + _KARO + r"\s*[:\-]?\s+(?P<t>.+)$", _F),
  re.compile(r"^(?:please\s+)?add\s+(?P<t>.+?)\s+to\s+(?:my\s+)?(?:tasks?|task\s+list|to-?do(?:\s+list)?|list)$", _F),
  re.compile(r"^(?P<t>.+?)\s+(?:ka\s+|ko\s+)?(?:task|todo)\s+(?:add|bana(?:o|na)?|daal(?:o|do)?)" + _KARO + r"$", _F),
]

_LIST_PATTERNS = [
  re.compile(r"^(?:show|list|see|view|check)\s+(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:pending\s+|open\s+)?(?:tasks?|to-?dos?|to-?do\s+list)(?:\s+for\s+today|\s+today)?$", _F),
  re.compile(r"^(?:what(?:'s|\s+is|\s+are)?|whats)\s+(?:is\s+)?(?:still\s+)?(?:pending|left|remaining|on\s+my\s+(?:list|plate)|my\s+(?:tasks?|to-?dos?))(?:\s+for\s+today|\s+today)?$", _F),
  re.compile(r"^(?:my\s+)?(?:pending\s+|open\s+|today'?s\s+)?(?:tasks?|to-?dos?)(?:\s+(?:for\s+)?today)?$", _F),
  re.compile(r"^(?:kya\s+)?(?:kya\s+)?pending\s+(?:hai|h|kya\s+hai|tasks?|kaam)(?:\s+kya\s+hai)?$", _F),
  re.compile(r"^(?:aaj|kal)\s+(?:ke|ka)\s+(?:tasks?|kaam)(?:\s+(?:kya\s+hai|batao|dikhao))?$", _F),
  re.compile(r"^(?:mere\s+)?(?:tasks?|kaam)\s+(?:batao|dikhao|kya\s+hai)$", _F),
]

_COMPLETE_STRICT = [
  re.compile(r"^(?:please\s+)?(?:mark|set)\s+(?:task\s+)?(?P<t>.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)$", _F),
  re.compile(r"^(?:done|complete|finish|finished|completed|tick)\s+task\s*[:\-]?\s*(?P<t>.+)$", _F),
  re.compile(r"^(?:done|complete|tick)\s+(?:#|no\.?\s*)?(?P<t>\d{1,2})$", _F),
  re.compile(r"^(?:task\s+)?(?P<t>\d{1,2})\s+(?:done|complete|ho\s+gaya|ho\s+gya)$", _F),
]
# "complete this code", "finish the story" are usually requests for the LLM:
# treat these as task completion only when a task clearly matches.
_COMPLETE_LOOSE = [
  re.compile(r"^(?:done|complete|finish|finished|completed|tick)\s*[:\-]?\s+(?P<t>.+)$", _F),
  re.compile(
    r"^(?:maine\s+)?(?P<t>.+?)\s+(?:ho\s+gaya|ho\s+gya|ho\s+gyi|ho\s+gayi|kar\s+liya|kar\s+diya|done|complete)$", _F
  ),
]
_DELETE_PATTERNS = [
  re.compile(r"^(?:please\s+)?(?:delete|remove|cancel)\s+(?:the\s+)?task\s*[:\-]?\s*(?P<t>.+)$", _F),
  re.compile(r"^(?:please\s+)?(?:delete|remove)\s+(?P<t>.+?)\s+from\s+(?:my\s+)?(?:tasks?|list|to-?do(?:\s+list)?)$", _F),
  re.compile(r"^(?P<t>.+?)\s+(?:wala\s+)?task\s+(?:delete|hata(?:o|do)?)" + _KARO + r"$", _F),
]
_NOTE_PATTERNS = [
  re.compile(r"^(?:please\s+)?(?:save|add|take|make|create|write)\s+(?:a\s+)?note\s*(?:[:\-]\s*|\s+)(?P<t>.+)$", _F),
  re.compile(r"^(?:note|note\s+down|jot\s+down)\s*[:\-]\s*(?P<t>.+)$", _F),
  re.compile(r"^note\s+(?:down\s+|kar\s+lo\s+|karo\s+)(?P<t>.+)$", _F),
]

_BRIEFING_PATTERNS = [
  re.compile(r"^(?:please\s+)?(?:plan|organi[sz]e)\s+(?:my|the)\s+day(?:\s+for\s+me)?$", _F),
  re.compile(r"^(?:give\s+me\s+)?(?:my\s+|the\s+)?(?:daily\s+|morning\s+|today'?s\s+)?(?:briefing|brief|day\s+plan|plan\s+for\s+today)$", _F),
  re.compile(r"^brief\s+me$", _F),
  re.compile(r"^(?:what(?:'s|\s+is|s)|how(?:'s|\s+is|s))\s+my\s+day(?:\s+(?:today|looking|look\s+like|looking\s+like))*$", _F),
  re.compile(r"^what(?:'s|\s+is|s)?\s+(?:on\s+)?(?:my\s+)?(?:plan|schedule|agenda)(?:\s+for)?(?:\s+today)?$", _F),
  re.compile(r"^(?:aaj|din)\s+ka\s+(?:plan|schedule)(?:\s+(?:kya\s+hai|batao|dikhao|bana\s*do))?$", _F),
  re.compile(r"^(?:mera\s+)?(?:aaj\s+ka\s+)?din\s+(?:kaisa\s+hai|plan\s+karo)$", _F),
  re.compile(r"^aaj\s+kya\s+(?:karna\s+hai|hai|plan\s+hai)$", _F),
]

_PRIORITY_HIGH = re.compile(r"\b(urgent|asap|important|high\s+priority|zaruri|zaroori)\b", _F)
_PRIORITY_LOW = re.compile(r"\b(low\s+priority|someday|whenever|kabhi\s+bhi)\b", _F)
_TODAY_WORD = re.compile(r"\b(today|aaj)\b", _F)
_TOMORROW_WORD = re.compile(r"\b(tomorrow|kal)\b", _F)
_DAY_AFTER = re.compile(r"\b(day\s+after\s+tomorrow|parso|parson)\b", _F)
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_RE = re.compile(r"\b(?:on\s+|this\s+|next\s+|by\s+)?(" + "|".join(_WEEKDAYS) + r")\b", _F)

# Removed from task titles once the date/priority has been read.
_STRIP_FROM_TITLE = [
  re.compile(r"\b(?:in|after)\s+\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b", _F),
  re.compile(r"\b\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)\s+(?:baad|later)\b", _F),
  re.compile(r"\b(?:by|on|at|due)?\s*(?:day\s+after\s+tomorrow|tomorrow|today|tonight|parso|parson|kal|aaj)\b", _F),
  _WEEKDAY_RE,
  re.compile(r"\b(?:by|at|before)?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", _F),
  re.compile(r"\b(?:by|at|before)\s+\d{1,2}(?::\d{2})?\b", _F),
  re.compile(r"\b(?:subah|shaam|raat|baje|tak)\b", _F),
  _PRIORITY_HIGH,
  _PRIORITY_LOW,
  re.compile(r"\((?:high|medium|low)\)", _F),
]


def parse_planner_request(text: str, *, now: datetime | None = None) -> PlannerIntent | None:
  cleaned = " ".join((text or "").strip().split()).rstrip(" .!?")
  if not cleaned:
    return None
  moment = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)

  for pattern in _BRIEFING_PATTERNS:
    if pattern.match(cleaned):
      return PlannerIntent(PlannerAction.BRIEFING)

  for pattern in _NOTE_PATTERNS:
    match = pattern.match(cleaned)
    if match:
      note = re.sub(r"^(?:that|ki)\s+", "", match.group("t").strip(), flags=_F)
      return PlannerIntent(PlannerAction.ADD_NOTE, note)

  for pattern in _ADD_PATTERNS:
    match = pattern.match(cleaned)
    if match:
      return _add_intent(match.group("t"), moment)

  for pattern in _LIST_PATTERNS:
    if pattern.match(cleaned):
      return PlannerIntent(PlannerAction.LIST_TASKS, today_only=bool(_TODAY_WORD.search(cleaned)))

  for pattern in _DELETE_PATTERNS:
    match = pattern.match(cleaned)
    if match:
      return PlannerIntent(PlannerAction.DELETE_TASK, _clean_reference(match.group("t")))

  for pattern in _COMPLETE_STRICT:
    match = pattern.match(cleaned)
    if match:
      return PlannerIntent(PlannerAction.COMPLETE_TASK, _clean_reference(match.group("t")))

  for pattern in _COMPLETE_LOOSE:
    match = pattern.match(cleaned)
    if match and len(match.group("t").split()) <= 8:
      return PlannerIntent(PlannerAction.COMPLETE_TASK, _clean_reference(match.group("t")), strict=False)
  return None


def _add_intent(raw: str, now: datetime) -> PlannerIntent | None:
  priority = Priority.MEDIUM
  if _PRIORITY_HIGH.search(raw):
    priority = Priority.HIGH
  elif _PRIORITY_LOW.search(raw):
    priority = Priority.LOW
  due = parse_due(raw, now)
  title = raw
  for pattern in _STRIP_FROM_TITLE:
    title = pattern.sub(" ", title)
  title = re.sub(r"\s+", " ", title).strip(" ,.-:;")
  title = re.sub(r"^(?:to|for)\s+|\s+(?:by|on|at|for|to|before)$", "", title, flags=_F).strip(" ,.-:;")
  if not title:
    return None
  return PlannerIntent(PlannerAction.ADD_TASK, title[:1].upper() + title[1:], due_at=due, priority=priority)


def parse_due(text: str, now: datetime) -> datetime | None:
  """Due time from a task phrase; date-only phrases get ``DATE_ONLY_TIME``."""
  moment = now.astimezone(LOCAL_TZ)
  timed = _parse_run_at(text, moment)
  day = None
  if _DAY_AFTER.search(text):
    day = (moment + timedelta(days=2)).date()
  elif _TOMORROW_WORD.search(text):
    day = (moment + timedelta(days=1)).date()
  elif _TODAY_WORD.search(text) or re.search(r"\btonight\b", text, _F):
    day = moment.date()
  else:
    weekday = _WEEKDAY_RE.search(text)
    if weekday:
      target = _WEEKDAYS.index(weekday.group(1).lower())
      ahead = (target - moment.weekday()) % 7 or 7
      day = (moment + timedelta(days=ahead)).date()

  if timed is not None:
    if day is not None and "parso" not in text.lower() and not _WEEKDAY_RE.search(text):
      return timed  # the reminder parser already applied today / tomorrow
    if day is not None:
      return datetime.combine(day, timed.astimezone(LOCAL_TZ).time(), LOCAL_TZ)
    return timed
  if day is not None:
    return datetime.combine(day, DATE_ONLY_TIME, LOCAL_TZ)
  return None


def is_date_only(due: datetime) -> bool:
  local = due.astimezone(LOCAL_TZ)
  return local.hour == DATE_ONLY_TIME.hour and local.minute == DATE_ONLY_TIME.minute


def _clean_reference(raw: str) -> str:
  ref = re.sub(r"^(?:the|my|task|number|no\.?|#)\s+", "", raw.strip(), flags=_F)
  ref = re.sub(r"^#", "", ref)
  ref = re.sub(r"\s+(?:task|wala(?:\s+task)?|wala\s+kaam)$", "", ref, flags=_F)
  return ref.strip(" .,:;\"'")
