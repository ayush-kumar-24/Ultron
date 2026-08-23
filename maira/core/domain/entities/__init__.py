"""Domain entities."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
  MemoryCategory,
  MessageRole,
  Priority,
  TaskStatus,
)


def utc_now() -> datetime:
  return datetime.now(timezone.utc)


@dataclass
class Message:
  role: MessageRole
  content: str
  timestamp: datetime = field(default_factory=utc_now)
  id: str | None = None
  conversation_id: str | None = None

  def to_llm_dict(self) -> dict[str, str]:
    return {"role": self.role.value, "content": self.content}


@dataclass
class Conversation:
  id: str
  title: str
  created_at: datetime
  updated_at: datetime


@dataclass
class Task:
  id: str
  title: str
  status: TaskStatus
  priority: Priority
  created_at: datetime
  updated_at: datetime
  due_at: datetime | None = None


@dataclass
class Note:
  id: str
  title: str
  body: str
  created_at: datetime
  updated_at: datetime


@dataclass
class MemoryEntry:
  id: str
  category: MemoryCategory
  title: str
  body: str
  created_at: datetime
  updated_at: datetime


@dataclass
class AutomationJob:
  id: str
  title: str
  instruction: str
  action_type: AutomationActionType
  action_payload: str
  run_at: datetime
  recurrence: AutomationRecurrence
  enabled: bool
  status: AutomationStatus
  created_at: datetime
  updated_at: datetime
  last_run_at: datetime | None = None
  last_error: str | None = None
