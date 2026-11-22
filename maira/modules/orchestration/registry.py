"""Agent registry - what each part of Ultron is, what it can do, and what it is doing now.

Nothing here is decorative: every agent maps to a real service in the container, its
status comes from real work passing through `track()`, and its history is persisted.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from maira.infrastructure.persistence.sqlite.repositories.intelligence import (
  AgentExecutionRepository,
)


@dataclass
class AgentSpec:
  id: str
  name: str
  role: str
  description: str
  capabilities: Callable[[], list[str]]
  model: Callable[[], str]
  available: Callable[[], tuple[bool, str]]
  idle_status: str = "ready"  # ready | idle | monitoring
  permissions: list[str] = field(default_factory=list)


class AgentRegistry:
  def __init__(self, executions: AgentExecutionRepository, *, bus=None) -> None:
    self._executions = executions
    self._bus = bus
    self._specs: dict[str, AgentSpec] = {}
    self._active: dict[str, list[str]] = {}
    self._lock = threading.Lock()

  def register(self, spec: AgentSpec) -> None:
    self._specs[spec.id] = spec

  def ids(self) -> list[str]:
    return list(self._specs)

  def describe(self, agent_id: str) -> dict[str, Any] | None:
    spec = self._specs.get(agent_id)
    if spec is None:
      return None
    try:
      ok, reason = spec.available()
    except Exception as exc:  # noqa: BLE001 - one broken service must not hide the rest
      ok, reason = False, str(exc)
    with self._lock:
      current = (self._active.get(agent_id) or [None])[-1]
    count, last = self._executions.stats(agent_id)
    status = "working" if current else (spec.idle_status if ok else "idle")
    try:
      capabilities = spec.capabilities()
    except Exception:  # noqa: BLE001
      capabilities = []
    return {
      "id": spec.id,
      "name": spec.name,
      "role": spec.role,
      "status": status,
      "description": spec.description if ok else f"{spec.description} Unavailable: {reason}",
      "capabilities": capabilities,
      "executions": count,
      "lastRun": last.isoformat() if last else None,
      "model": spec.model(),
      "currentTask": current,
      "permissions": list(spec.permissions),
      "available": ok,
    }

  def list_agents(self) -> list[dict[str, Any]]:
    return [agent for agent in (self.describe(agent_id) for agent_id in self._specs) if agent]

  @contextmanager
  def track(self, agent_id: str, task: str) -> Iterator[None]:
    """Record one piece of real work: live status, a persisted execution, and an event."""
    if agent_id not in self._specs:
      yield
      return
    execution = self._executions.start(agent_id, task)
    with self._lock:
      self._active.setdefault(agent_id, []).append(task[:120])
    self._publish(agent_id)
    try:
      yield
    except Exception as exc:
      self._executions.finish(execution.id, ok=False, error=str(exc))
      raise
    else:
      self._executions.finish(execution.id, ok=True)
    finally:
      with self._lock:
        stack = self._active.get(agent_id) or []
        if stack:
          stack.pop()
      self._publish(agent_id)

  def record(self, agent_id: str, task: str, *, ok: bool, error: str | None = None) -> None:
    """Log work that already happened elsewhere (e.g. a scheduled automation)."""
    if agent_id not in self._specs:
      return
    execution = self._executions.start(agent_id, task)
    self._executions.finish(execution.id, ok=ok, error=error)
    self._publish(agent_id)

  def _publish(self, agent_id: str) -> None:
    if self._bus is None:
      return
    try:
      payload = self.describe(agent_id)
      if payload:
        self._bus.publish("agent", payload)
    except Exception as exc:  # noqa: BLE001
      logger.debug("agent event not published: {}", exc)
