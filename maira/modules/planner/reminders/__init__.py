"""Tasks and reminders kept in sync.

``LinkedPlanner`` wraps the plain planner so every caller (chat, voice, the
Tasks screen) gets the same behaviour:

- a task with a clock time gets a reminder at that time;
- completing, deleting or re-timing the task cancels or moves its reminder;
- "Done" on the reminder completes the task;
- open tasks from earlier days move to today (``roll_over``).

The link is the task id stored in the reminder's JSON payload, so no schema
change is needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger

from maira.core.domain.entities import AutomationJob, Note, Task
from maira.core.domain.value_objects import AutomationActionType, Priority, TaskStatus
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.planner import Planner
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.intent import DATE_ONLY_TIME, is_date_only

TASK_ID_KEY = "task_id"


def task_id_of(job: AutomationJob) -> str | None:
  try:
    payload = json.loads(job.action_payload or "{}")
  except json.JSONDecodeError:
    return None
  value = payload.get(TASK_ID_KEY) if isinstance(payload, dict) else None
  return str(value) if value else None


def _has_clock_time(task: Task) -> bool:
  return task.due_at is not None and not is_date_only(task.due_at)


class LinkedPlanner(Planner):
  def __init__(
    self,
    planner: Planner,
    automation: Automation,
    *,
    remind_at_due: bool = True,
    roll_over_enabled: bool = True,
    clock=lambda: datetime.now(timezone.utc),
  ) -> None:
    self._inner = planner
    self._automation = automation
    self.reminders_enabled = remind_at_due
    self._roll_over_enabled = roll_over_enabled
    self._clock = clock

  # --- tasks (kept in sync with reminders) ------------------------------------

  def add_task(
    self,
    title: str,
    *,
    priority: Priority = Priority.MEDIUM,
    due_at: datetime | None = None,
  ) -> Task:
    task = self._inner.add_task(title, priority=priority, due_at=due_at)
    self._schedule(task)
    return task

  def set_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
    task = self._inner.set_task_status(task_id, status)
    if task is not None:
      self._cancel(task_id)
      if status == TaskStatus.OPEN:
        self._schedule(task)
    return task

  def set_task_due(self, task_id: str, due_at: datetime | None) -> Task | None:
    task = self._inner.set_task_due(task_id, due_at)
    if task is not None:
      self._cancel(task_id)
      self._schedule(task)
    return task

  def delete_task(self, task_id: str) -> None:
    self._cancel(task_id)
    self._inner.delete_task(task_id)

  def has_reminder(self, task: Task) -> bool:
    return any(task_id_of(job) == task.id for job in self._pending_jobs())

  def complete_from_job(self, job_id: str | None) -> Task | None:
    """"Done" on a reminder: complete the task it belongs to, if any."""
    if not job_id:
      return None
    job = self._automation.get(job_id)
    task_id = task_id_of(job) if job is not None else None
    if task_id is None:
      return None
    task = self._inner.get_task(task_id)
    if task is None or task.status == TaskStatus.DONE:
      return None
    logger.info("Task '{}' completed from its reminder", task.title)
    return self.set_task_status(task_id, TaskStatus.DONE)

  def roll_over(self, now: datetime | None = None) -> list[Task]:
    """Move open tasks due on earlier days to today (date only). Idempotent."""
    if not self._roll_over_enabled:
      return []
    today = (now or self._clock()).astimezone(LOCAL_TZ).date()
    moved: list[Task] = []
    for task in self._inner.list_tasks():
      if task.status != TaskStatus.OPEN or task.due_at is None:
        continue
      if task.due_at.astimezone(LOCAL_TZ).date() >= today:
        continue
      new_due = datetime.combine(today, DATE_ONLY_TIME, LOCAL_TZ)
      updated = self.set_task_due(task.id, new_due)
      if updated is not None:
        moved.append(updated)
    if moved:
      logger.info("Moved {} unfinished task(s) to today", len(moved))
    return moved

  # --- reminder bookkeeping ------------------------------------------------------

  def _schedule(self, task: Task) -> None:
    if not self.reminders_enabled or task.status != TaskStatus.OPEN or not _has_clock_time(task):
      return
    if task.due_at <= self._clock():
      return
    self._automation.create(
      task.title,
      task.title,
      task.due_at,
      action_type=AutomationActionType.NOTIFY,
      action_payload=json.dumps({"message": task.title, TASK_ID_KEY: task.id}),
    )
    logger.info("Reminder set for task '{}'", task.title)

  def _cancel(self, task_id: str) -> None:
    for job in self._pending_jobs():
      if task_id_of(job) == task_id:
        self._automation.delete(job.id)

  def _pending_jobs(self) -> list[AutomationJob]:
    return self._automation.list_jobs(include_done=False)

  # --- plain delegation ------------------------------------------------------------

  def list_tasks(self) -> list[Task]:
    return self._inner.list_tasks()

  def get_task(self, task_id: str) -> Task | None:
    return self._inner.get_task(task_id)

  def set_task_priority(self, task_id: str, priority: Priority) -> Task | None:
    return self._inner.set_task_priority(task_id, priority)

  def list_notes(self) -> list[Note]:
    return self._inner.list_notes()

  def add_note(self, title: str, body: str = "") -> Note:
    return self._inner.add_note(title, body)

  def update_note(self, note_id: str, *, title: str, body: str) -> Note | None:
    return self._inner.update_note(note_id, title=title, body=body)

  def delete_note(self, note_id: str) -> None:
    self._inner.delete_note(note_id)

  def get_note(self, note_id: str) -> Note | None:
    return self._inner.get_note(note_id)
