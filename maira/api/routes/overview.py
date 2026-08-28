"""The home dashboard — one call for everything the overview page shows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from maira.api.deps import (
  get_automation_runs,
  get_automations,
  get_calendar,
  get_conversations,
  get_memory,
  get_notifications,
  get_tasks,
)
from maira.api.mapping import (
  automation_to_api,
  event_to_api,
  memory_category_to_api,
  notification_to_api,
  task_to_api,
)

router = APIRouter(tags=["overview"])


def _cognitive_load(open_count: int) -> str:
  if open_count > 8:
    return "High"
  if open_count > 4:
    return "Moderate"
  return "Light"


@router.get("/overview")
def overview() -> dict:
  now = datetime.now(timezone.utc)
  tasks = get_tasks().list_tasks()
  done = [task for task in tasks if task.stage == "done"]
  open_tasks = [task for task in tasks if task.stage != "done"]
  due_soon = [
    task for task in open_tasks if task.due_at and task.due_at <= now + timedelta(days=1)
  ]
  rate = round(len(done) / len(tasks) * 100) if tasks else 0

  memories = get_memory().list_memories()
  by_category: dict[str, int] = {}
  for entry in memories:
    key = memory_category_to_api(entry.category)
    by_category[key] = by_category.get(key, 0) + 1
  pinned = sum(1 for entry in memories if getattr(entry, "pinned", False))

  jobs = get_automations().list_jobs(include_done=False)
  runs = get_automation_runs().list_runs(limit=5)

  upcoming = sorted(
    (job for job in jobs if job.enabled and job.status.value == "pending"),
    key=lambda job: job.run_at,
  )[:5]

  today = now.astimezone().date()
  events = [
    event
    for event in get_calendar().list_events(start=now - timedelta(hours=12))
    if event.start_at.astimezone().date() == today
  ]

  notifications = get_notifications().list_notifications(limit=5)
  conversations = get_conversations().list_conversations()[:5]

  return {
    "memory": {"total": len(memories), "byCategory": by_category},
    "pinned": pinned,
    "productivity": {
      "done": len(done),
      "pending": len(open_tasks),
      "rate": rate,
      "sessions": 0,
    },
    "dueSoon": len(due_soon),
    "tasks": [task_to_api(task) for task in open_tasks[:5]],
    "events": [event_to_api(event) for event in events],
    "automations": [automation_to_api(job) for job in upcoming],
    "notifications": [notification_to_api(item) for item in notifications],
    "conversations": [
      {"id": item.id, "title": item.title, "updatedAt": item.updated_at.isoformat()}
      for item in conversations
    ],
    "activity": [
      {
        "id": run.id,
        "kind": "automations",
        "title": "Automation ran" if run.status == "done" else "Automation failed",
        "body": run.output,
        "at": run.ran_at.isoformat(),
      }
      for run in runs
    ],
    "log": [notification_to_api(item) for item in notifications[:4]],
    "metrics": [
      {
        "l": "Task completion",
        "v": f"{rate}%",
        "d": f"{len(done)} of {len(tasks)}",
        "up": rate >= 50,
      },
      {"l": "Open tasks", "v": str(len(open_tasks)), "d": f"{len(due_soon)} due within a day"},
      {"l": "Automations", "v": str(len(jobs)), "d": f"{len(upcoming)} scheduled next"},
      {
        "l": "Cognitive load",
        "v": _cognitive_load(len(open_tasks)),
        "d": f"{len(events)} events today",
      },
    ],
    "focus": [],
    "agents": [],
    "projects": [],
  }
