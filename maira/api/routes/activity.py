"""Activity, insights, and search — all derived from what Ultron already stores.

Nothing here invents data: with an empty database these return empty lists and
zeroes, which is what the pages should show.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from maira.api.deps import (
  get_automation_runs,
  get_automations,
  get_conversations,
  get_knowledge,
  get_memory,
  get_projects,
  get_tasks,
)
from maira.api.mapping import iso, memory_category_to_api

router = APIRouter(tags=["activity"])

KINDS = ("tasks", "memory", "chat", "automations", "research", "system")


def _entries() -> list[dict]:
  items: list[dict] = []

  for task in get_tasks().list_tasks():
    if task.completed_at:
      items.append(
        {
          "id": f"ac_task_done_{task.id}",
          "kind": "tasks",
          "title": "Task completed",
          "body": task.title,
          "at": iso(task.completed_at),
        }
      )
    items.append(
      {
        "id": f"ac_task_new_{task.id}",
        "kind": "tasks",
        "title": "Task created",
        "body": task.title,
        "at": iso(task.created_at),
      }
    )

  for run in get_automation_runs().list_runs(limit=50):
    items.append(
      {
        "id": f"ac_run_{run.id}",
        "kind": "automations",
        "title": "Automation ran" if run.status == "done" else "Automation failed",
        "body": run.output,
        "at": iso(run.ran_at),
      }
    )

  for entry in get_memory().list_memories():
    items.append(
      {
        "id": f"ac_mem_{entry.id}",
        "kind": "memory",
        "title": "Memory saved",
        "body": (entry.body or entry.title)[:160],
        "at": iso(entry.created_at),
      }
    )

  for conversation in get_conversations().list_conversations():
    items.append(
      {
        "id": f"ac_conv_{conversation.id}",
        "kind": "chat",
        "title": "Conversation",
        "body": conversation.title,
        "at": iso(conversation.updated_at),
      }
    )

  items.sort(key=lambda item: item["at"] or "", reverse=True)
  return items


@router.get("/activity")
def list_activity(kind: str | None = Query(default=None), limit: int = Query(default=60)) -> list[dict]:
  items = _entries()
  if kind and kind != "all":
    items = [item for item in items if item["kind"] == kind]
  return items[: max(1, min(limit, 200))]


@router.get("/sessions")
def list_sessions() -> list[dict]:
  # Ultron does not track work sessions yet — an empty list is the honest answer.
  return []


@router.get("/agents")
def list_agents() -> list[dict]:
  # No agent runtime exists yet; the page shows its empty state rather than an error.
  return []


@router.get("/executions")
def list_executions() -> list[dict]:
  return []


@router.get("/research")
def list_research() -> list[dict]:
  return []


@router.get("/integrations")
def list_integrations() -> list[dict]:
  # Nothing is wired to external services yet.
  return []


@router.get("/insights")
def insights() -> dict:
  tasks = get_tasks().list_tasks()
  done = [task for task in tasks if task.stage == "done"]
  runs = get_automation_runs().list_runs(limit=500)
  memories = get_memory().list_memories()
  conversations = get_conversations().list_conversations()

  now = datetime.now(timezone.utc)
  recent = now - timedelta(days=30)
  active_days = {
    item["at"][:10]
    for item in _entries()
    if item["at"] and datetime.fromisoformat(item["at"]) >= recent
  }

  streak = 0
  day = now.date()
  while day.isoformat() in active_days:
    streak += 1
    day = day - timedelta(days=1)

  by_category: dict[str, int] = {}
  for entry in memories:
    key = memory_category_to_api(entry.category)
    by_category[key] = by_category.get(key, 0) + 1

  return {
    "usage": {
      "queries": len(conversations),
      "research": 0,
      "tasks": len(tasks),
      "automations": len(runs),
    },
    "tasks": {"done": len(done), "total": len(tasks)},
    "memory": {"total": len(memories), "byCategory": by_category},
    "sessions": [],
    "projects": [],
    "knowledgeTop": [],
    "focus": [],
    "activeDays": len(active_days),
    "streak": streak,
  }


@router.get("/search")
def search(q: str | None = Query(default=None)) -> list[dict]:
  needle = (q or "").strip().lower()
  if not needle:
    return []

  results: list[dict] = []

  for conversation in get_conversations().list_conversations():
    if needle in conversation.title.lower():
      results.append(
        {
          "kind": "conversation",
          "id": conversation.id,
          "title": conversation.title,
          "sub": "Conversation",
          "route": f"/chat/{conversation.id}",
        }
      )

  for entry in get_memory().list_memories():
    text = entry.body or entry.title
    if needle in text.lower():
      results.append(
        {
          "kind": "memory",
          "id": entry.id,
          "title": text[:120],
          "sub": f"Memory · {memory_category_to_api(entry.category)}",
          "route": f"/memory?q={q}",
        }
      )

  for task in get_tasks().list_tasks():
    if needle in task.title.lower():
      results.append(
        {
          "kind": "task",
          "id": task.id,
          "title": task.title,
          "sub": f"Task · {task.stage.replace('_', ' ')}",
          "route": "/tasks",
        }
      )

  for item in get_knowledge().list_items():
    if needle in item.title.lower() or any(needle in tag.lower() for tag in item.tags):
      results.append(
        {
          "kind": "knowledge",
          "id": item.id,
          "title": item.title,
          "sub": f"Knowledge · {item.type}",
          "route": f"/knowledge/{item.id}",
        }
      )

  for project in get_projects().list_projects():
    if needle in project.name.lower() or needle in project.description.lower():
      results.append(
        {
          "kind": "project",
          "id": project.id,
          "title": project.name,
          "sub": "Project",
          "route": f"/projects/{project.id}",
        }
      )

  return results[:30]
