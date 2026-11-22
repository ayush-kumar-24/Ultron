"""Immutable value objects."""

from enum import Enum


class MessageRole(str, Enum):
  USER = "user"
  ASSISTANT = "assistant"
  SYSTEM = "system"


class TaskStatus(str, Enum):
  OPEN = "open"
  DONE = "done"


class Priority(str, Enum):
  LOW = "low"
  MEDIUM = "medium"
  HIGH = "high"


class MemoryCategory(str, Enum):
  PREFERENCE = "preference"
  CONVERSATION = "conversation"
  TASK = "task"
  NOTE = "note"
  IDEA = "idea"
  PROJECT = "project"
  # Used by the web UI's memory categories. Plurals ("preferences", "projects",
  # "conversations") are deliberately absent: they map onto the singular members above.
  PERSONAL = "personal"
  PEOPLE = "people"
  WORK = "work"
  LEARNED = "learned"


class AutomationStatus(str, Enum):
  PENDING = "pending"
  DONE = "done"
  FAILED = "failed"
  CANCELLED = "cancelled"


class AutomationRecurrence(str, Enum):
  NONE = "none"
  DAILY = "daily"
  WEEKLY = "weekly"


class AutomationActionType(str, Enum):
  AGENT = "agent"
  NOTIFY = "notify"
  OPEN_URL = "open_url"
  OPEN_APP = "open_app"
  DESKTOP = "desktop"
