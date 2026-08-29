"""Resolve live services from the shared application container."""

from __future__ import annotations

from maira.app.container import Container
from maira.app.settings import Settings
from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.memory import Memory
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRunRepository,
  GoalRepository,
  KnowledgeRepository,
  ProjectRepository,
  CalendarEventRepository,
  ConversationRepository,
  NotificationRepository,
  TaskRepository,
)
from maira.modules.brain.service import BrainService

_container: Container | None = None


def bind_container(container: Container) -> None:
  global _container
  _container = container


def get_container() -> Container:
  if _container is None:
    raise RuntimeError("API container is not bound")
  return _container


def get_settings() -> Settings:
  return get_container().resolve("settings")


def get_event_bus() -> EventBus:
  return get_container().resolve("event_bus")


def get_brain() -> Brain:
  return get_container().resolve("brain")


def get_brain_service() -> BrainService:
  brain = get_brain()
  if not isinstance(brain, BrainService):
    raise RuntimeError("Brain is not a BrainService")
  return brain


def get_llm():
  return get_container().resolve("llm")


def get_memory() -> Memory:
  return get_container().resolve("memory")


def get_conversations() -> ConversationRepository:
  return get_container().resolve("conversation_repository")


def get_tasks() -> TaskRepository:
  return get_container().resolve("task_repository")


def get_calendar() -> CalendarEventRepository:
  return get_container().resolve("calendar_repository")


def get_notifications() -> NotificationRepository:
  return get_container().resolve("notification_repository")


def get_automations():
  return get_container().resolve("automation")


def get_automation_runs() -> AutomationRunRepository:
  return get_container().resolve("automation_run_repository")


def get_scheduler():
  return get_container().try_resolve("automation_scheduler")


def get_projects() -> ProjectRepository:
  return get_container().resolve("project_repository")


def get_goals() -> GoalRepository:
  return get_container().resolve("goal_repository")


def get_knowledge() -> KnowledgeRepository:
  return get_container().resolve("knowledge_repository")


def get_storage():
  return get_container().resolve("storage")


def get_overlay():
  overlay = get_container().try_resolve("overlay")
  if overlay is None:
    from pathlib import Path

    from maira.api.overlay import OverlayStore

    overlay = OverlayStore(Path("data") / "user_profile.json")
    get_container().register_instance("overlay", overlay)
  return overlay
