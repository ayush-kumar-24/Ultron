"""Automations — schedule, pause, run, and see what happened."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from maira.api.deps import (
  get_automation_runs,
  get_automations,
  get_notifications,
  get_scheduler,
)
from maira.api.mapping import automation_run_to_api, automation_to_api
from maira.api.parsing import parse_task
from maira.api.schemas import AutomationCreate, AutomationPatch
from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
)

router = APIRouter(tags=["automations"])

_RECURRENCE_FROM_TEXT = {
  "every day": AutomationRecurrence.DAILY,
  "every morning": AutomationRecurrence.DAILY,
  "every evening": AutomationRecurrence.DAILY,
  "every week": AutomationRecurrence.WEEKLY,
}


def _recurrence(value: str | None) -> AutomationRecurrence:
  cleaned = (value or "").strip().lower()
  if not cleaned:
    return AutomationRecurrence.NONE
  if cleaned in _RECURRENCE_FROM_TEXT:
    return _RECURRENCE_FROM_TEXT[cleaned]
  if cleaned.startswith("every monday") or "weekly" in cleaned:
    return AutomationRecurrence.WEEKLY
  if cleaned.startswith("every"):
    return AutomationRecurrence.DAILY
  try:
    return AutomationRecurrence(cleaned)
  except ValueError:
    return AutomationRecurrence.NONE


def _with_counts(job) -> dict:
  runs, failures = get_automation_runs().counts(job.id)
  return automation_to_api(job, runs=runs, failures=failures)


@router.get("/automations")
def list_automations() -> list[dict]:
  jobs = get_automations().list_jobs(include_done=True)
  return [_with_counts(job) for job in jobs]


@router.get("/automations/{job_id}/runs")
def list_runs(job_id: str) -> list[dict]:
  if get_automations().get(job_id) is None:
    raise HTTPException(status_code=404, detail="Automation not found")
  return [automation_run_to_api(run) for run in get_automation_runs().list_runs(job_id)]


@router.post("/automations", status_code=201)
def create_automation(body: AutomationCreate) -> dict:
  source = body.text or body.name or ""
  if not source.strip():
    raise HTTPException(status_code=422, detail="An automation needs text or a name")

  parsed = parse_task(source)
  title = body.name or parsed.title
  run_at = None
  if body.due:
    try:
      run_at = datetime.fromisoformat(body.due.replace("Z", "+00:00"))
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=f"Invalid due '{body.due}'") from exc
  run_at = run_at or parsed.due
  if run_at is None:
    raise HTTPException(
      status_code=422,
      detail="No time found. Try 'every day at 8am' or 'remind me tomorrow at 6pm'.",
    )
  if run_at.tzinfo is None:
    run_at = run_at.replace(tzinfo=timezone.utc)

  recurrence = _recurrence(body.recurrence or body.trigger or parsed.recurrence)
  action = body.action or f"Remind: {title}"

  job = get_automations().create(
    title,
    action,
    run_at,
    action_type=AutomationActionType.NOTIFY,
    action_payload=json.dumps({"message": action}),
    recurrence=recurrence,
  )
  return _with_counts(job)


@router.patch("/automations/{job_id}")
def update_automation(job_id: str, body: AutomationPatch) -> dict:
  automations = get_automations()
  if automations.get(job_id) is None:
    raise HTTPException(status_code=404, detail="Automation not found")

  if body.status is not None:
    wanted = body.status.strip().lower()
    if wanted == "paused":
      automations.set_enabled(job_id, False)
    elif wanted == "active":
      automations.set_enabled(job_id, True)
    elif wanted == "cancelled":
      automations.cancel(job_id)
    else:
      raise HTTPException(status_code=400, detail=f"Unknown status '{body.status}'")

  job = automations.get(job_id)
  if job is None:  # pragma: no cover - deleted between calls
    raise HTTPException(status_code=404, detail="Automation not found")
  return _with_counts(job)


@router.delete("/automations/{job_id}", status_code=204)
def delete_automation(job_id: str) -> Response:
  automations = get_automations()
  if automations.get(job_id) is None:
    raise HTTPException(status_code=404, detail="Automation not found")
  automations.delete(job_id)
  return Response(status_code=204)


@router.post("/automations/{job_id}/run")
def run_automation(job_id: str) -> dict:
  """Fire a job now — the only way to test a reminder without waiting for it."""
  automations = get_automations()
  job = automations.get(job_id)
  if job is None:
    raise HTTPException(status_code=404, detail="Automation not found")

  scheduler = get_scheduler()
  if scheduler is None:  # pragma: no cover - always registered
    raise HTTPException(status_code=503, detail="Automation runtime unavailable")

  runs = get_automation_runs()
  before = runs.list_runs(job_id, limit=1)
  latest_before = before[0].id if before else None

  started = time.perf_counter()
  result = scheduler.run_now(job)
  duration_ms = int((time.perf_counter() - started) * 1000)

  # A wired scheduler records the run and raises the notification in its own
  # callback; only write them here when that did not happen.
  after = runs.list_runs(job_id, limit=1)
  if after and after[0].id != latest_before:
    return automation_run_to_api(after[0])

  get_notifications().create(
    type="automation",
    title="Automation ran" if result.ok else "Automation failed",
    body=f"{job.title} — {result.message}",
  )
  return automation_run_to_api(
    runs.record(
      job_id,
      status="done" if result.ok else "failed",
      duration_ms=duration_ms,
      output=result.message,
    )
  )
