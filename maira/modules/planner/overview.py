"""Real data for the Home panel, the Activity timeline and global search.

Pure functions over the planner, automations and memory, so the UI only
renders what they return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from maira.core.domain.value_objects import AutomationStatus, Priority, TaskStatus
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.planner import Planner
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.chat import format_due, is_overdue

_HOME_ITEMS = 4


@dataclass(frozen=True)
class HomeItem:
  title: str
  meta: str
  id: str = ""
  warn: bool = False  # overdue / attention


@dataclass(frozen=True)
class HomeOverview:
  tasks: list[HomeItem] = field(default_factory=list)
  tasks_total: int = 0
  reminders: list[HomeItem] = field(default_factory=list)
  notes: list[HomeItem] = field(default_factory=list)


def _local(moment: datetime) -> datetime:
  return moment.astimezone(LOCAL_TZ)


def _clock(moment: datetime) -> str:
  return _local(moment).strftime("%I:%M %p").lstrip("0")


def _when(moment: datetime, now: datetime) -> str:
  """'10:42 AM' today, 'Yesterday 9:05 PM', else '22 Sep, 9:05 PM'."""
  local, today = _local(moment), _local(now).date()
  if local.date() == today:
    return _clock(moment)
  if local.date() == today - timedelta(days=1):
    return f"Yesterday {_clock(moment)}"
  if local.date() == today + timedelta(days=1):
    return f"Tomorrow {_clock(moment)}"
  return f"{local.strftime('%d %b').lstrip('0')}, {_clock(moment)}"


def home_overview(planner: Planner, automation: Automation | None, now: datetime | None = None) -> HomeOverview:
  now = _local(now or datetime.now(LOCAL_TZ))
  today = now.date()

  focus = [
    t
    for t in planner.list_tasks()
    if t.status == TaskStatus.OPEN and (t.due_at is None or _local(t.due_at).date() <= today)
  ]
  # Overdue first, then timed today, then date-only today, then undated; high priority first within.
  focus.sort(
    key=lambda t: (
      not is_overdue(t, now),
      t.due_at is None,
      t.due_at or now,
      t.priority != Priority.HIGH,
    )
  )
  tasks = []
  for task in focus[:_HOME_ITEMS]:
    overdue = is_overdue(task, now)
    parts = [format_due(task.due_at, now)] if task.due_at else []
    if overdue:
      parts.append("overdue")
    if task.priority == Priority.HIGH:
      parts.append("high")
    tasks.append(HomeItem(task.title, " · ".join(parts), task.id, warn=overdue))

  reminders = []
  if automation is not None:
    upcoming = [
      j
      for j in automation.list_jobs(include_done=False)
      if j.enabled and j.status == AutomationStatus.PENDING and j.run_at >= now - timedelta(minutes=1)
    ]
    upcoming.sort(key=lambda j: j.run_at)
    reminders = [HomeItem(j.title, _when(j.run_at, now), j.id) for j in upcoming[:3]]

  notes = [HomeItem(n.title or "Untitled", _when(n.updated_at, now), n.id) for n in planner.list_notes()[:2]]
  return HomeOverview(tasks=tasks, tasks_total=len(focus), reminders=reminders, notes=notes)


def activity_feed(
  planner: Planner,
  automation: Automation | None,
  now: datetime | None = None,
  *,
  limit: int = 40,
) -> list[dict[str, str]]:
  """What actually happened, newest first: tasks done, reminders fired, notes saved."""
  now = now or datetime.now(LOCAL_TZ)
  events: list[tuple[datetime, str]] = []
  for task in planner.list_tasks():
    if task.status == TaskStatus.DONE:
      events.append((task.updated_at, f'Task done: "{task.title}"'))
    else:
      events.append((task.created_at, f'Task added: "{task.title}"'))
  for note in planner.list_notes():
    events.append((note.updated_at, f'Note saved: "{note.title or "Untitled"}"'))
  if automation is not None:
    for job in automation.list_jobs(include_done=True):
      if job.last_run_at is None:
        continue
      if job.status == AutomationStatus.FAILED:
        events.append((job.last_run_at, f'Automation failed: "{job.title}"'))
      else:
        events.append((job.last_run_at, f'Reminder shown: "{job.title}"'))
  events.sort(key=lambda item: item[0], reverse=True)
  return [
    {"id": f"ev{i}", "time": _when(moment, now), "text": text}
    for i, (moment, text) in enumerate(events[:limit])
  ]


def search_everything(planner: Planner, memory=None, query: str = "", category: str = "Everything") -> list[dict[str, str]]:
  """Case-insensitive search over tasks, notes and memories."""
  q = query.strip().lower()
  want = category if category not in ("", "All", "Everything") else None
  results: list[dict[str, str]] = []

  def matches(*texts: str) -> bool:
    return not q or any(q in (t or "").lower() for t in texts)

  if want in (None, "Tasks"):
    for task in planner.list_tasks():
      if matches(task.title):
        state = "Done" if task.status == TaskStatus.DONE else "Open"
        results.append({"id": task.id, "category": "Tasks", "title": task.title, "subtitle": state})
  if want in (None, "Notes"):
    for note in planner.list_notes():
      if matches(note.title, note.body):
        results.append({"id": note.id, "category": "Notes", "title": note.title or "Untitled", "subtitle": "Note"})
  if want in (None, "Memory") and memory is not None:
    for entry in memory.list_memories():
      if matches(entry.title, entry.body):
        results.append(
          {"id": entry.id, "category": "Memory", "title": entry.title, "subtitle": entry.category.value.title()}
        )
  return results[:50]
