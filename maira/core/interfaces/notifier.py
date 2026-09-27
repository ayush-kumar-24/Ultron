"""Notifier port — OS-level notifications (Windows toast, tray balloon)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class NotificationAction(str, Enum):
  DONE = "done"
  SNOOZE = "snooze"
  OPEN = "open"


@dataclass(frozen=True)
class Notification:
  id: str
  title: str
  body: str
  job_id: str | None = None
  actions: tuple[NotificationAction, ...] = ()


class Notifier(ABC):
  @abstractmethod
  def name(self) -> str:
    """Short backend name for logs."""

  @abstractmethod
  def is_available(self) -> bool:
    """Whether this backend can show notifications on this machine."""

  @abstractmethod
  def show(self, notification: Notification) -> bool:
    """Show a notification. Return False so the next backend is tried."""
