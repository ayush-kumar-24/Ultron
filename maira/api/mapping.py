"""Map domain entities onto the frontend API contract."""

from __future__ import annotations

from datetime import datetime, timezone

from maira.core.domain.entities import Conversation, MemoryEntry, Message
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
