"""Carry out planner intents from chat and phrase short Hinglish replies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from maira.core.domain.entities import Task
from maira.core.domain.value_objects import Priority, TaskStatus
from maira.core.interfaces.planner import Planner
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.intent import (
  PlannerAction,
  PlannerIntent,
  is_date_only,
  parse_planner_request,
)

_STOPWORDS = {"the", "a", "an", "my", "to", "ka", "ki", "ke", "ko", "wala", "task", "i", "i'm", "im", "all"}
_MAX_LISTED = 15


@dataclass(frozen=True)
class PlannerReply:
  text: str
  changed: bool  # tasks or notes were modified


def format_due(due: datetime | None, now: datetime) -> str:
  if due is None:
    return ""
  local = due.astimezone(LOCAL_TZ)
  today = now.astimezone(LOCAL_TZ).date()
  delta = (local.date() - today).days
  if delta == 0:
    day = "aaj"
  elif delta == 1:
    day = "kal"
  elif delta == -1:
    day = "kal (beet gaya)"
  elif 1 < delta < 7:
    day = local.strftime("%A")
  else:
    day = local.strftime("%d %b").lstrip("0")
  if is_date_only(local):
    return day
  return f"{day} {local.strftime('%I:%M %p').lstrip('0')}"


def is_overdue(task: Task, now: datetime) -> bool:
  if task.due_at is None or task.status == TaskStatus.DONE:
    return False
  due = task.due_at.astimezone(LOCAL_TZ)
  if is_date_only(due):
    return due.date() < now.astimezone(LOCAL_TZ).date()
  return due < now


def _due_on(task: Task, day: date) -> bool:
  return task.due_at is not None and task.due_at.astimezone(LOCAL_TZ).date() <= day


def _tokens(text: str) -> set[str]:
  return {w for w in re.findall(r"[\w']+", text.lower()) if w not in _STOPWORDS and len(w) > 1}


class PlannerChat:
  def __init__(self, planner: Planner) -> None:
    self._planner = planner
    self._last_listing: list[str] = []  # task ids in the order last shown

  def handle(self, text: str, *, now: datetime | None = None) -> PlannerReply | None:
    moment = now or datetime.now(LOCAL_TZ)
    intent = parse_planner_request(text, now=moment)
    if intent is None:
      return None
    if intent.action == PlannerAction.ADD_TASK:
      return self._add(intent, moment)
    if intent.action == PlannerAction.LIST_TASKS:
      return self._list(intent, moment)
    if intent.action == PlannerAction.COMPLETE_TASK:
      return self._complete(intent)
    if intent.action == PlannerAction.DELETE_TASK:
      return self._delete(intent)
    return self._note(intent)

  def _add(self, intent: PlannerIntent, now: datetime) -> PlannerReply:
    task = self._planner.add_task(intent.text, priority=intent.priority, due_at=intent.due_at)
    details = []
    if task.due_at is not None:
      details.append(format_due(task.due_at, now))
    if task.priority == Priority.HIGH:
      details.append("high priority")
    suffix = f" ({', '.join(details)})" if details else ""
    return PlannerReply(f'Task add ho gaya: "{task.title}"{suffix}.', changed=True)

  def _list(self, intent: PlannerIntent, now: datetime) -> PlannerReply:
    open_tasks = [t for t in self._planner.list_tasks() if t.status == TaskStatus.OPEN]
    open_tasks.sort(key=lambda t: (t.due_at is None, t.due_at or now, t.priority != Priority.HIGH))
    if intent.today_only:
      today = now.astimezone(LOCAL_TZ).date()
      open_tasks = [t for t in open_tasks if _due_on(t, today) or t.due_at is None]
    if not open_tasks:
      self._last_listing = []
      return PlannerReply("Koi pending task nahi hai. Sab clear!", changed=False)

    shown = open_tasks[:_MAX_LISTED]
    self._last_listing = [t.id for t in shown]
    heading = "Aaj ke tasks" if intent.today_only else "Pending tasks"
    lines = [f"{heading} ({len(open_tasks)}):"]
    for number, task in enumerate(shown, start=1):
      extras = []
      if task.due_at is not None:
        extras.append(format_due(task.due_at, now))
      if is_overdue(task, now):
        extras.append("overdue")
      if task.priority == Priority.HIGH:
        extras.append("high")
      extra = f" — {', '.join(extras)}" if extras else ""
      lines.append(f"{number}. {task.title}{extra}")
    if len(open_tasks) > len(shown):
      lines.append(f"…aur {len(open_tasks) - len(shown)} more (Tasks tab mein dekho)")
    lines.append('Complete karne ke liye bolo: "done 1".')
    return PlannerReply("\n".join(lines), changed=False)

  def _complete(self, intent: PlannerIntent) -> PlannerReply | None:
    candidates = [t for t in self._planner.list_tasks() if t.status == TaskStatus.OPEN]
    found = self._resolve(intent.text, candidates)
    if isinstance(found, Task):
      self._planner.set_task_status(found.id, TaskStatus.DONE)
      return PlannerReply(f'Badhiya! "{found.title}" done mark kar diya.', changed=True)
    if not intent.strict:
      return None  # "I'm done" etc. — not about a task; let the LLM answer
    return self._not_found(intent.text, found, "done")

  def _delete(self, intent: PlannerIntent) -> PlannerReply:
    tasks = self._planner.list_tasks()
    open_first = [t for t in tasks if t.status == TaskStatus.OPEN] + [
      t for t in tasks if t.status != TaskStatus.OPEN
    ]
    found = self._resolve(intent.text, open_first)
    if isinstance(found, Task):
      self._planner.delete_task(found.id)
      self._last_listing = [i for i in self._last_listing if i != found.id]
      return PlannerReply(f'Task delete kar diya: "{found.title}".', changed=True)
    return self._not_found(intent.text, found, "delete")

  def _note(self, intent: PlannerIntent) -> PlannerReply:
    words = intent.text.split()
    title = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    title = title[:1].upper() + title[1:]
    self._planner.add_note(title, intent.text)
    return PlannerReply(f'Note save ho gaya: "{title}".', changed=True)

  def _resolve(self, reference: str, candidates: list[Task]) -> Task | list[Task]:
    """A single matching task, or the (possibly empty) list of ambiguous matches."""
    ref = reference.strip()
    if ref.isdigit():
      index = int(ref) - 1
      if 0 <= index < len(self._last_listing):
        task_id = self._last_listing[index]
        for task in candidates:
          if task.id == task_id:
            return task
      return []

    lowered = ref.lower()
    exact = [t for t in candidates if t.title.lower() == lowered]
    if len(exact) == 1:
      return exact[0]
    query = _tokens(ref)
    if not query:
      return []
    # Every meaningful word of the reference must appear in the title.
    matches = [t for t in candidates if query <= _tokens(t.title) or lowered in t.title.lower()]
    if len(matches) == 1:
      return matches[0]
    return matches

  def _not_found(self, reference: str, matches: list[Task], verb: str) -> PlannerReply:
    if matches:
      shown = matches[:5]
      self._last_listing = [t.id for t in shown]
      options = "\n".join(f"{n}. {t.title}" for n, t in enumerate(shown, start=1))
      return PlannerReply(
        f'Kaunsa task? Ek se zyada match hue:\n{options}\nBolo: "{verb} 1".', changed=False
      )
    if reference.isdigit():
      if self._last_listing:
        return PlannerReply(f"List mein number {reference} nahi hai.", changed=False)
      return PlannerReply(
        'Pehle "pending tasks" dikhao, phir number bolo (jaise "done 1").', changed=False
      )
    return PlannerReply(f'"{reference}" naam ka koi task nahi mila. "Pending tasks" bolke list dekho.', changed=False)
