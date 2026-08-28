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
