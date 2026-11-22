"""Pydantic request bodies mirroring frontend/docs/API.md."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class UserPatch(BaseModel):
  name: str | None = None
  initials: str | None = None
  email: str | None = None
  timezone: str | None = None
  language: str | None = None
  role: str | None = None


class ConversationCreate(BaseModel):
  title: str | None = None
  projectId: str | None = None


class ConversationPatch(BaseModel):
  title: str | None = None
  pinned: bool | None = None
  projectId: str | None = None


class ChatContext(BaseModel):
  projectId: str | None = None
  documentId: str | None = None
  label: str | None = None


class ChatStreamIn(BaseModel):
  conversationId: str | None = None
  text: str
  context: ChatContext | None = None


class MessageMemoryIn(BaseModel):
  text: str


class MemoryCreate(BaseModel):
  text: str
  category: str = "personal"
  importance: str = "medium"


class MemoryPatch(BaseModel):
  text: str | None = None
  category: str | None = None
  importance: str | None = None
  pinned: bool | None = None
  source: str | None = None


class SettingsPatch(BaseModel):
  model_config = {"extra": "allow"}

  def as_dict(self) -> dict[str, Any]:
    return self.model_dump(exclude_unset=True)


class TaskCreate(BaseModel):
  """Either a plain `text` line to parse, or explicit fields."""

  text: str | None = None
  title: str | None = None
  description: str | None = None
  priority: str | None = None
  due: str | None = None
  projectId: str | None = None
  tags: list[str] | None = None
  estimate: int | None = None
  recurrence: str | None = None


class TaskPatch(BaseModel):
  title: str | None = None
  description: str | None = None
  priority: str | None = None
  status: str | None = None
  due: str | None = None
  projectId: str | None = None
  tags: list[str] | None = None
  estimate: int | None = None


class TaskParseIn(BaseModel):
  text: str


class MessageTaskIn(BaseModel):
  title: str
  projectId: str | None = None


class EventCreate(BaseModel):
  title: str
  start: str
  end: str | None = None
  type: str | None = None
  projectId: str | None = None


class AutomationCreate(BaseModel):
  text: str | None = None
  name: str | None = None
  trigger: str | None = None
  action: str | None = None
  due: str | None = None
  recurrence: str | None = None


class AutomationPatch(BaseModel):
  status: str | None = None
  name: str | None = None
  action: str | None = None


class NotificationPatch(BaseModel):
  read: bool | None = None


class ProjectCreate(BaseModel):
  name: str
  description: str | None = None
  color: str | None = None
  tags: list[str] | None = None


class ProjectPatch(BaseModel):
  name: str | None = None
  description: str | None = None
  status: str | None = None
  progress: int | None = None


class GoalCreate(BaseModel):
  title: str
  objective: str | None = None
  deadline: str | None = None
  projectId: str | None = None
  milestones: list[Any] | None = None


class GoalPatch(BaseModel):
  title: str | None = None
  objective: str | None = None
  progress: int | None = None
  milestones: list[Any] | None = None


class KnowledgeCreate(BaseModel):
  title: str
  type: str | None = None
  source: str | None = None
  body: str | None = None
  tags: list[str] | None = None
  projectId: str | None = None
