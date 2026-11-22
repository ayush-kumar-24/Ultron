"""Domain entities."""

from __future__ import annotations

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
  pinned: bool = False
  project_id: str | None = None


@dataclass
class Task:
  id: str
  title: str
  status: TaskStatus
  priority: Priority
  created_at: datetime
  updated_at: datetime
  due_at: datetime | None = None
  description: str = ""
  project_id: str | None = None
  tags: list[str] = field(default_factory=list)
  estimate: int = 30
  recurrence: str | None = None
  completed_at: datetime | None = None
  # The web UI distinguishes todo / in_progress / done; `status` stays the
  # two-state domain value so the desktop app is unaffected.
  stage: str = "todo"


@dataclass
class CalendarEvent:
  id: str
  title: str
  start_at: datetime
  end_at: datetime
  type: str = "meeting"
  project_id: str | None = None
  task_id: str | None = None
  created_at: datetime = field(default_factory=utc_now)


@dataclass
class Notification:
  id: str
  type: str
  title: str
  body: str
  created_at: datetime
  read: bool = False


@dataclass
class Project:
  id: str
  name: str
  description: str
  status: str
  color: str
  progress: int
  tags: list[str]
  created_at: datetime
  updated_at: datetime


@dataclass
class Goal:
  id: str
  title: str
  objective: str
  deadline: datetime | None
  progress: int
  project_id: str | None
  milestones: list[dict]
  created_at: datetime
  updated_at: datetime


@dataclass
class KnowledgeItem:
  id: str
  title: str
  type: str
  source: str
  body: str
  summary: str | None
  size: int
  tags: list[str]
  status: str
  project_id: str | None
  created_at: datetime
  updated_at: datetime


@dataclass
class AutomationRun:
  id: str
  automation_id: str
  ran_at: datetime
  status: str
  duration_ms: int = 0
  output: str = ""


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
  source: str = ""
  confidence: float = 0.9
  importance: str = "medium"
  pinned: bool = False
  last_accessed: datetime | None = None
  access_count: int = 0


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
