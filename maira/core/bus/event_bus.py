"""In-process event bus for decoupled inter-module communication."""

from __future__ import annotations

import threading
from typing import Any

from maira.core.types import EventHandler


class EventBus:
  """Thread-safe publish/subscribe dispatcher."""

  def __init__(self) -> None:
    self._handlers: dict[str, list[EventHandler]] = {}
    self._lock = threading.Lock()

  def subscribe(self, topic: str, handler: EventHandler) -> None:
    with self._lock:
      self._handlers.setdefault(topic, []).append(handler)

  def unsubscribe(self, topic: str, handler: EventHandler) -> None:
    with self._lock:
      handlers = self._handlers.get(topic, [])
      if handler in handlers:
        handlers.remove(handler)

  def publish(self, topic: str, payload: Any = None) -> None:
    with self._lock:
      handlers = list(self._handlers.get(topic, []))

    for handler in handlers:
      handler(payload)
