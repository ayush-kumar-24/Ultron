"""Map domain entities onto the frontend API contract."""

from __future__ import annotations

from datetime import datetime, timezone

from maira.core.domain.entities import (
  AutomationJob,
  AutomationRun,
  CalendarEvent,
  Conversation,
  Goal,
  KnowledgeItem,
  MemoryEntry,
  Message,
  Notification,
  Project,
  Task,
)
from maira.core.domain.value_objects import MemoryCategory, MessageRole

API_MEMORY_CATEGORIES = (
  "personal",
  "preferences",
  "projects",
  "people",
  "work",
  "conversations",
  "learned",
)

_LEGACY_TO_API = {
  "preference": "preferences",
  "conversation": "conversations",
  "task": "work",
  "note": "personal",
  "idea": "learned",
  "project": "projects",
}

_FILTER_ALIASES = {
  "preferences": ("preferences", "preference"),
  "conversations": ("conversations", "conversation"),
  "projects": ("projects", "project"),
  "work": ("work", "task"),
  "personal": ("personal", "note"),
  "learned": ("learned", "idea"),
  "people": ("people",),
}


def iso(value: datetime | None) -> str | None:
  if value is None:
    return None
  if value.tzinfo is None:
    value = value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc).isoformat()


def conversation_to_api(conversation: Conversation) -> dict:
  return {
    "id": conversation.id,
    "title": conversation.title,
    "projectId": conversation.project_id,
    "updatedAt": iso(conversation.updated_at),
    "pinned": bool(conversation.pinned),
  }


def message_to_api(message: Message) -> dict:
  return {
    "id": message.id,
    "role": message.role.value if isinstance(message.role, MessageRole) else str(message.role),
    "text": message.content,
    "at": iso(message.timestamp),
  }


def memory_category_to_api(category: MemoryCategory | str) -> str:
  value = category.value if isinstance(category, MemoryCategory) else str(category)
  return _LEGACY_TO_API.get(value, value)


def memory_category_from_api(value: str) -> MemoryCategory:
  cleaned = (value or "personal").strip().lower()
  try:
    return MemoryCategory(cleaned)
  except ValueError:
    mapped = {v: k for k, v in _LEGACY_TO_API.items()}
    if cleaned in mapped:
      return MemoryCategory(mapped[cleaned])
    return MemoryCategory.PERSONAL


def category_filter_values(api_category: str) -> set[str]:
  return set(_FILTER_ALIASES.get(api_category, (api_category,)))


def memory_to_api(entry: MemoryEntry) -> dict:
  text = entry.body.strip() or entry.title
  return {
    "id": entry.id,
    "text": text,
    "category": memory_category_to_api(entry.category),
    "source": entry.source or "Teach Ultron",
    "confidence": entry.confidence,
    "importance": entry.importance or "medium",
    "createdAt": iso(entry.created_at),
    "lastAccessed": iso(entry.last_accessed) or iso(entry.updated_at),
    "pinned": bool(entry.pinned),
    "accessCount": entry.access_count,
  }


def title_from_text(text: str, limit: int = 48) -> str:
  cleaned = " ".join(text.split())
  if not cleaned:
    return "Untitled"
  if len(cleaned) <= limit:
    return cleaned
  return f"{cleaned[: limit - 3]}..."


def task_to_api(task: Task) -> dict:
  return {
    "id": task.id,
    "title": task.title,
    "description": task.description,
    "priority": task.priority.value,
    "status": task.stage,
    "due": iso(task.due_at),
    "projectId": task.project_id,
    "tags": list(task.tags),
    "estimate": task.estimate,
    "recurrence": task.recurrence,
    "completedAt": iso(task.completed_at),
    "createdAt": iso(task.created_at),
  }


def event_to_api(event: CalendarEvent) -> dict:
  return {
    "id": event.id,
    "title": event.title,
    "start": iso(event.start_at),
    "end": iso(event.end_at),
    "type": event.type,
    "projectId": event.project_id,
    "taskId": event.task_id,
  }


def notification_to_api(notification: Notification) -> dict:
  return {
    "id": notification.id,
    "type": notification.type,
    "title": notification.title,
    "body": notification.body,
    "at": iso(notification.created_at),
    "read": bool(notification.read),
  }


def automation_run_to_api(run: AutomationRun) -> dict:
  return {
    "id": run.id,
    "automationId": run.automation_id,
    "at": iso(run.ran_at),
    "status": run.status,
    "ms": run.duration_ms,
    "output": run.output,
  }


_RECURRENCE_LABEL = {
  "daily": "Every day",
  "weekly": "Every week",
  "none": "Once",
}


def automation_trigger_label(job: AutomationJob) -> str:
  """'Every day · 8:00 AM' — the human sentence the automations page shows."""
  base = _RECURRENCE_LABEL.get(job.recurrence.value, job.recurrence.value.capitalize())
  moment = job.run_at
  if moment is None:
    return base
  if moment.tzinfo is None:
    moment = moment.replace(tzinfo=timezone.utc)
  local = moment.astimezone()
  clock = local.strftime("%I:%M %p").lstrip("0")
  if job.recurrence.value == "none":
    return f"{local.strftime('%d %b')} · {clock}"
  return f"{base} · {clock}"


def automation_status_to_api(job: AutomationJob) -> str:
  if not job.enabled:
    return "paused"
  if job.status.value == "failed":
    return "failed"
  if job.status.value in {"done", "cancelled"}:
    return "paused" if job.status.value == "cancelled" else "active"
  return "active"


def automation_to_api(job: AutomationJob, *, runs: int = 0, failures: int = 0) -> dict:
  pending = job.status.value == "pending" and job.enabled
  return {
    "id": job.id,
    "name": job.title,
    "trigger": automation_trigger_label(job),
    "action": job.instruction,
    "status": automation_status_to_api(job),
    "lastRun": iso(job.last_run_at),
    "nextRun": iso(job.run_at) if pending else None,
    "runs": runs,
    "failures": failures,
    "error": job.last_error,
    "recurrence": job.recurrence.value,
    "actionType": job.action_type.value,
  }


def project_to_api(project: Project, *, open_tasks: int = 0) -> dict:
  return {
    "id": project.id,
    "name": project.name,
    "description": project.description,
    "status": project.status,
    "color": project.color,
    "progress": project.progress,
    "tags": list(project.tags),
    "openTasks": open_tasks,
    "updatedAt": iso(project.updated_at),
  }


def goal_to_api(goal: Goal, *, project_name: str | None = None) -> dict:
  return {
    "id": goal.id,
    "title": goal.title,
    "objective": goal.objective,
    "deadline": iso(goal.deadline),
    "progress": goal.progress,
    "projectId": goal.project_id,
    "project": project_name,
    "milestones": list(goal.milestones),
  }


def knowledge_to_api(item: KnowledgeItem) -> dict:
  return {
    "id": item.id,
    "title": item.title,
    "type": item.type,
    "source": item.source,
    "size": item.size,
    "tags": list(item.tags),
    "status": item.status,
    "summary": item.summary,
    "projectId": item.project_id,
    "createdAt": iso(item.created_at),
  }
