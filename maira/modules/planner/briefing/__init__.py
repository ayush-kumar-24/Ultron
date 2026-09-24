"""Daily briefing — today's tasks, overdue items and reminders in one message."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from maira.core.domain.entities import AutomationJob, Task
from maira.core.domain.value_objects import AutomationStatus, Priority, TaskStatus
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.planner import Planner
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.intent import is_date_only

_MAX_ITEMS = 6


@dataclass(frozen=True)
class Briefing:
  text: str  # full message for chat
  summary: str  # one line for the notification
  speech: str  # short version to speak aloud
  empty: bool


def _clock(moment: datetime) -> str:
  return moment.astimezone(LOCAL_TZ).strftime("%I:%M %p").lstrip("0")


def _greeting(now: datetime) -> str:
  hour = now.hour
  if hour < 12:
    return "Good morning"
  if hour < 17:
    return "Good afternoon"
  return "Good evening"


def _plural(count: int, word: str) -> str:
  return f"{count} {word}{'' if count == 1 else 's'}"


class BriefingService:
  def __init__(self, planner: Planner, automation: Automation | None = None, *, name: str = "") -> None:
    self._planner = planner
    self._automation = automation
    self._name = name.strip()

  def set_name(self, name: str) -> None:
    """Change the name used in greetings (Settings → Your name)."""
    self._name = name.strip()

  def build(self, now: datetime | None = None) -> Briefing:
    now = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    today = now.date()
    open_tasks = [t for t in self._planner.list_tasks() if t.status == TaskStatus.OPEN]

    def local_day(task: Task):
      return task.due_at.astimezone(LOCAL_TZ).date() if task.due_at else None

    overdue = [t for t in open_tasks if t.due_at and self._is_overdue(t, now)]
    due_today = [t for t in open_tasks if local_day(t) == today and t not in overdue]
    undated = [t for t in open_tasks if t.due_at is None]
    tomorrow = [t for t in open_tasks if local_day(t) == today + timedelta(days=1)]
    reminders = self._reminders_today(now)

    overdue.sort(key=lambda t: t.due_at)
    due_today.sort(key=lambda t: (is_date_only(t.due_at), t.due_at, t.priority != Priority.HIGH))
    undated.sort(key=lambda t: t.priority != Priority.HIGH)

    who = f", {self._name}" if self._name else ""
    header = f"{_greeting(now)}{who}! Aaj {now.strftime('%A, %d %b').replace(' 0', ' ')} hai."
    lines = [header]

    if overdue:
      lines.append("")
      lines.append(f"Overdue ({len(overdue)}):")
      lines += [f"• {t.title}" for t in overdue[:_MAX_ITEMS]]
    if due_today:
      lines.append("")
      lines.append(f"Aaj ke tasks ({len(due_today)}):")
      for t in due_today[:_MAX_ITEMS]:
        when = "" if is_date_only(t.due_at) else f"{_clock(t.due_at)} — "
        flag = " (high)" if t.priority == Priority.HIGH else ""
        lines.append(f"• {when}{t.title}{flag}")
    if reminders:
      lines.append("")
      lines.append(f"Reminders aaj ({len(reminders)}):")
      lines += [f"• {_clock(j.run_at)} — {j.title}" for j in reminders[:_MAX_ITEMS]]
    if undated:
      lines.append("")
      shown = ", ".join(t.title for t in undated[:3])
      more = f" +{len(undated) - 3} aur" if len(undated) > 3 else ""
      lines.append(f"Bina date ke ({len(undated)}): {shown}{more}")
    if tomorrow:
      lines.append("")
      lines.append(f"Kal ke liye: {_plural(len(tomorrow), 'task')}.")

    focus = self._focus(overdue, due_today, undated)
    empty = not (overdue or due_today or reminders or undated)
    if empty:
      lines.append("")
      lines.append("Aaj ka din free hai — koi task ya reminder nahi.")
      lines.append('Plan banane ke liye bolo: "add task …" ya "remind me at 5pm to …".')
    elif focus is not None:
      lines.append("")
      lines.append(f'Pehle yeh karo: "{focus.title}".')

    counts = []
    if due_today:
      counts.append(f"{_plural(len(due_today), 'task')} aaj")
    if overdue:
      counts.append(f"{len(overdue)} overdue")
    if reminders:
      counts.append(_plural(len(reminders), "reminder"))
    if undated:
      counts.append(f"{len(undated)} bina date")
    summary = ", ".join(counts) if counts else "Aaj koi task ya reminder nahi."

    spoken = []
    if due_today:
      spoken.append(_plural(len(due_today), "task"))
    if overdue:
      spoken.append(f"{len(overdue)} overdue")
    if reminders:
      spoken.append(_plural(len(reminders), "reminder"))
    speech = f"{_greeting(now)}{who}! "
    if spoken:
      speech += f"Aaj {', '.join(spoken)} hain."
    elif undated:
      speech += f"Aaj ke liye kuch fixed nahi, par {_plural(len(undated), 'task')} pending hain."
    else:
      speech += "Aaj ka din free hai."
    if focus is not None and not empty:
      speech += f" Pehle {focus.title} karo."
    return Briefing(text="\n".join(lines), summary=summary, speech=speech, empty=empty)

  @staticmethod
  def _is_overdue(task: Task, now: datetime) -> bool:
    due = task.due_at.astimezone(LOCAL_TZ)
    if is_date_only(due):
      return due.date() < now.date()
    return due < now

  @staticmethod
  def _focus(overdue: list[Task], due_today: list[Task], undated: list[Task]) -> Task | None:
    for group in (overdue, [t for t in due_today if t.priority == Priority.HIGH], due_today):
      if group:
        return group[0]
    high = [t for t in undated if t.priority == Priority.HIGH]
    return high[0] if high else None

  def _reminders_today(self, now: datetime) -> list[AutomationJob]:
    if self._automation is None:
      return []
    today = now.date()
    jobs = [
      j
      for j in self._automation.list_jobs(include_done=False)
      if j.enabled
      and j.status == AutomationStatus.PENDING
      and j.run_at.astimezone(LOCAL_TZ).date() == today
      and j.run_at >= now - timedelta(minutes=1)
    ]
    return sorted(jobs, key=lambda j: j.run_at)
