"""Automation port — scheduled jobs Maira runs at set times."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from maira.core.domain.entities import AutomationJob
from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
)


class Automation(ABC):
  @abstractmethod
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
    """Schedule a new automation."""

  @abstractmethod
  def list_jobs(self, *, include_done: bool = True) -> list[AutomationJob]:
    """List automations newest-first."""

  @abstractmethod
  def get(self, job_id: str) -> AutomationJob | None:
    """Fetch one job."""

  @abstractmethod
  def set_enabled(self, job_id: str, enabled: bool) -> AutomationJob | None:
    """Enable or pause a job."""

  @abstractmethod
  def cancel(self, job_id: str) -> AutomationJob | None:
    """Cancel a pending job."""

  @abstractmethod
  def delete(self, job_id: str) -> None:
    """Remove a job permanently."""

  @abstractmethod
  def due_jobs(self, now: datetime | None = None) -> list[AutomationJob]:
    """Enabled pending jobs whose run_at is <= now."""

  @abstractmethod
  def mark_ran(
    self,
    job_id: str,
    *,
    ok: bool,
    error: str | None = None,
    next_run_at: datetime | None = None,
  ) -> AutomationJob | None:
    """Record execution result; optionally reschedule recurrence."""
