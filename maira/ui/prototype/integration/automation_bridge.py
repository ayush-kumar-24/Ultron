"""Bridge: AutomationsScreen ↔ AutomationService + runner toasts."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import AutomationRecurrence
from maira.core.interfaces.automation import Automation
from maira.modules.automation.parser import (
  LOCAL_TZ,
  infer_action,
  parse_schedule_request,
)
from maira.modules.automation.runner import AutomationRunner
from maira.ui.prototype.screens.automations import AutomationsScreen


def _schedule_label(job) -> str:
  local = job.run_at.astimezone(LOCAL_TZ)
  stamp = local.strftime("%a %d %b · %I:%M %p").replace(" 0", " ")
  status = job.status.value
  if job.recurrence == AutomationRecurrence.DAILY:
    base = f"Every day · next {stamp}"
  elif job.recurrence == AutomationRecurrence.WEEKLY:
    base = f"Every week · next {stamp}"
  else:
    base = stamp
  if status != "pending":
    return f"{base} · {status}"
  if not job.enabled:
    return f"{base} · paused"
  return base


class ProtoAutomationBridge(QObject):
  # Chat schedules on a worker thread; refresh the screen on the UI thread.
  _changed = Signal()

  def __init__(
    self,
    automation: Automation,
    event_bus: EventBus,
    view: AutomationsScreen,
    runner: AutomationRunner | None = None,
    *,
    toast=None,
  ) -> None:
    super().__init__()
    self._automation = automation
    self._view = view
    self._toast = toast
    self._runner = runner

    view.set_live_mode(True)
    view.create_requested.connect(self.create_from_form)
    view.toggle_requested.connect(self.toggle)
    view.delete_requested.connect(self.delete)

    self._changed.connect(self.refresh)
    event_bus.subscribe("automation.changed", lambda _p: self._changed.emit())
    if runner is not None:
      runner.jobs_changed.connect(self.refresh)
      runner.job_ran.connect(self._on_job_ran)

    self.refresh()

  def refresh(self) -> None:
    rows = []
    for job in self._automation.list_jobs(include_done=True):
      rows.append(
        {
          "id": job.id,
          "title": job.title,
          "schedule": _schedule_label(job),
          "instruction": job.instruction,
          "enabled": job.enabled and job.status.value == "pending",
        }
      )
    # Show pending first, then recent done
    rows.sort(key=lambda r: (0 if "paused" not in r["schedule"] and "done" not in r["schedule"] else 1, r["schedule"]))
    self._view.set_automations(rows)

  @Slot(str, str, str)
  def create_from_form(self, title: str, when: str, instruction: str) -> None:
    # Reuse chat parser: "instruction when"
    blob = f"{instruction} {when}".strip()
    parsed = parse_schedule_request(f"schedule {blob}")
    if parsed is None:
      # Try when-only glued
      parsed = parse_schedule_request(f"remind me to {instruction} {when}")
    if parsed is None:
      if self._toast:
        self._toast("Couldn't parse that time. Try “in 10 minutes” or “tomorrow at 9am”.")
      return
    action_type, payload = infer_action(instruction)
    import json

    self._automation.create(
      title or parsed.title,
      instruction or parsed.instruction,
      parsed.run_at,
      action_type=action_type,
      action_payload=json.dumps(payload),
      recurrence=parsed.recurrence,
    )
    if self._toast:
      self._toast(f"Scheduled: {title or parsed.title}")
    self.refresh()

  @Slot(str, bool)
  def toggle(self, job_id: str, enabled: bool) -> None:
    self._automation.set_enabled(job_id, enabled)
    self.refresh()

  @Slot(str)
  def delete(self, job_id: str) -> None:
    self._automation.delete(job_id)
    self.refresh()

  @Slot(str, bool, str)
  def _on_job_ran(self, title: str, ok: bool, message: str) -> None:
    if self._toast:
      prefix = "Ran" if ok else "Failed"
      self._toast(f"{prefix}: {title}" + (f" — {message}" if message and not ok else ""))
    self.refresh()
