"""Automation facade — schedule, list, and mark timed jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from maira.core.domain.entities import AutomationJob
from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
)
from maira.core.interfaces.automation import Automation
from maira.infrastructure.persistence.sqlite.repositories import AutomationRepository


class AutomationService(Automation):
  def __init__(self, repository: AutomationRepository) -> None:
    self._repo = repository

  def create(
    self,
    title: str,
    instruction: str,
    run_at: datetime,
    *,
    action_type: AutomationActionType = AutomationActionType.AGENT,
    action_payload: str = "{}",
    recurrence: AutomationRecurrence = AutomationRecurrence.NONE,
    enabled: bool = True,
  ) -> AutomationJob:
    if run_at.tzinfo is None:
      run_at = run_at.replace(tzinfo=timezone.utc)
    return self._repo.create(
      title,
      instruction,
      run_at.astimezone(timezone.utc),
      action_type=action_type,
      action_payload=action_payload,
      recurrence=recurrence,
      enabled=enabled,
    )

  def list_jobs(self, *, include_done: bool = True) -> list[AutomationJob]:
    return self._repo.list_jobs(include_done=include_done)

  def get(self, job_id: str) -> AutomationJob | None:
    return self._repo.get(job_id)

  def set_enabled(self, job_id: str, enabled: bool) -> AutomationJob | None:
    return self._repo.set_enabled(job_id, enabled)

  def cancel(self, job_id: str) -> AutomationJob | None:
    return self._repo.set_status(job_id, AutomationStatus.CANCELLED)

  def delete(self, job_id: str) -> None:
    self._repo.delete(job_id)

  def due_jobs(self, now: datetime | None = None) -> list[AutomationJob]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
      moment = moment.replace(tzinfo=timezone.utc)
    return self._repo.due_jobs(moment.astimezone(timezone.utc))

  def mark_ran(
    self,
    job_id: str,
    *,
    ok: bool,
    error: str | None = None,
    next_run_at: datetime | None = None,
  ) -> AutomationJob | None:
    return self._repo.mark_ran(job_id, ok=ok, error=error, next_run_at=next_run_at)

  def next_run_after(
    self,
    job: AutomationJob,
    from_time: datetime | None = None,
    *,
    now: datetime | None = None,
  ) -> datetime | None:
    """Next fire time for recurring jobs, always in the future.

    If Ultron was closed for days, skip the missed runs instead of firing
    once per missed day.
    """
    base = from_time or job.run_at
    if base.tzinfo is None:
      base = base.replace(tzinfo=timezone.utc)
    if job.recurrence == AutomationRecurrence.DAILY:
      step = timedelta(days=1)
    elif job.recurrence == AutomationRecurrence.WEEKLY:
      step = timedelta(weeks=1)
    else:
      return None
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
      moment = moment.replace(tzinfo=timezone.utc)
    nxt = base + step
    if nxt <= moment:
      missed = (moment - nxt) // step + 1
      nxt += step * missed
    return nxt
