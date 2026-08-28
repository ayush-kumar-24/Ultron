"""Tasks, natural-language task capture, and the day plan."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from maira.api.deps import get_calendar, get_tasks
from maira.api.mapping import task_to_api
from maira.api.parsing import parse_task
from maira.api.schemas import TaskCreate, TaskParseIn, TaskPatch
from maira.core.domain.value_objects import Priority

router = APIRouter(tags=["tasks"])

STAGES = ("todo", "in_progress", "done")
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _priority(value: str | None) -> Priority:
  if not value:
    return Priority.MEDIUM
  try:
    return Priority(value.strip().lower())
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=f"Unknown priority '{value}'") from exc


def _stage(value: str) -> str:
  cleaned = (value or "").strip().lower()
  if cleaned not in STAGES:
    raise HTTPException(status_code=400, detail=f"Unknown status '{value}'")
  return cleaned


def _moment(value: str | None) -> datetime | None:
  if not value:
    return None
  try:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=f"Invalid date '{value}'") from exc
  return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _end_of_today() -> datetime:
  now = datetime.now(timezone.utc).astimezone()
  return now.replace(hour=23, minute=59, second=59, microsecond=999999)


def _sorted(tasks: list) -> list:
  far_future = datetime.max.replace(tzinfo=timezone.utc)
  return sorted(
    tasks,
    key=lambda task: (task.stage == "done", task.due_at or far_future, task.created_at),
  )


@router.get("/tasks")
def list_tasks(
  view: str | None = Query(default=None),
  projectId: str | None = Query(default=None),
) -> list[dict]:
  tasks = get_tasks().list_tasks()
  cutoff = _end_of_today()

  if view == "today":
    tasks = [t for t in tasks if t.stage != "done" and t.due_at and t.due_at <= cutoff]
  elif view == "upcoming":
    tasks = [t for t in tasks if t.stage != "done" and t.due_at and t.due_at > cutoff]
  elif view == "inbox":
    tasks = [t for t in tasks if t.stage != "done" and not t.due_at]
  elif view == "completed":
    tasks = [t for t in tasks if t.stage == "done"]

  if projectId:
    tasks = [t for t in tasks if t.project_id == projectId]

  return [task_to_api(task) for task in _sorted(tasks)]


@router.post("/tasks/parse")
def parse(body: TaskParseIn) -> dict:
  return parse_task(body.text).to_api()


@router.post("/tasks", status_code=201)
def create_task(body: TaskCreate) -> dict:
  if body.text:
    parsed = parse_task(body.text)
    title = parsed.title
    priority = _priority(body.priority or parsed.priority)
    due_at = _moment(body.due) or parsed.due
    recurrence = body.recurrence or parsed.recurrence
    project_id = body.projectId or parsed.project_id
  else:
    if not (body.title or "").strip():
      raise HTTPException(status_code=422, detail="A task needs a title or a text line")
    title = body.title.strip()
    priority = _priority(body.priority)
    due_at = _moment(body.due)
    recurrence = body.recurrence
    project_id = body.projectId

  task = get_tasks().create(
    title,
    priority=priority,
    due_at=due_at,
    description=body.description or "",
    project_id=project_id,
    tags=body.tags or [],
    estimate=body.estimate or 30,
    recurrence=recurrence,
  )
  return task_to_api(task)


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskPatch) -> dict:
  task = get_tasks().update_task(
    task_id,
    title=body.title,
    description=body.description,
    priority=_priority(body.priority) if body.priority else None,
    stage=_stage(body.status) if body.status else None,
    due_at=_moment(body.due),
    clear_due=body.due is not None and not body.due,
    project_id=body.projectId,
    tags=body.tags,
    estimate=body.estimate,
  )
  if task is None:
    raise HTTPException(status_code=404, detail="Task not found")
  return task_to_api(task)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str) -> Response:
  tasks = get_tasks()
  if tasks.get(task_id) is None:
    raise HTTPException(status_code=404, detail="Task not found")
  tasks.delete(task_id)
  return Response(status_code=204)


@router.get("/plan/day")
def plan_day() -> dict:
  """Group today's open work and events into morning / afternoon / evening."""
  tasks = [t for t in get_tasks().list_tasks() if t.stage != "done"]
  far_future = datetime.max.replace(tzinfo=timezone.utc)
  ranked = sorted(
    tasks,
    key=lambda task: (_PRIORITY_ORDER.get(task.priority.value, 1), task.due_at or far_future),
  )

  today = datetime.now(timezone.utc).astimezone().date()
  events = [
    event
    for event in get_calendar().list_events()
    if event.start_at.astimezone().date() == today
  ]

  def slot(event) -> dict:
    return {"kind": event.type, "title": event.title, "at": event.start_at.isoformat()}

  def task_slot(index: int, fallback: str, minutes: int, why: str) -> dict:
    task = ranked[index] if len(ranked) > index else None
    return {
      "kind": "task",
      "title": task.title if task else fallback,
      "minutes": task.estimate if task else minutes,
      "why": why,
    }

  def in_hours(start: int, end: int) -> list[dict]:
    return [slot(e) for e in events if start <= e.start_at.astimezone().hour < end]

  busy_hours = sum(
    max(0.0, (event.end_at - event.start_at).total_seconds() / 3600.0) for event in events
  )

  return {
    "morning": [
      task_slot(0, "Review priorities", 30, "Highest priority, due soonest"),
      *in_hours(0, 12),
    ],
    "afternoon": [
      *in_hours(12, 17),
      task_slot(1, "Deep work", 60, "Fits the longest free block"),
    ],
    "evening": [
      task_slot(2, "Light admin", 30, "Small enough to finish tonight"),
      *in_hours(17, 24),
    ],
    "postpone": [
      {"title": task.title, "why": "No free block left today"} for task in ranked[3:5]
    ],
    "conflicts": (
      ["Three or more meetings overlap today's focus time"] if len(events) > 3 else []
    ),
    "freeHours": f"{max(0.0, 8 - busy_hours):.1f}",
  }
