"""Background memory worker — never blocks chat/LLM."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from loguru import logger

from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.memory import Memory
from maira.modules.memory.policy import MemoryPolicy


@dataclass
class MemoryJob:
  text: str
  role: str  # user | assistant


class MemoryWorker:
  def __init__(self, memory: Memory | None, policy: MemoryPolicy | None = None) -> None:
    self._memory = memory
    self._policy = policy or MemoryPolicy()
    self._queue: queue.Queue[MemoryJob | None] = queue.Queue()
    self._thread: threading.Thread | None = None
    self._running = False
    self._busy = False

  @property
  def busy(self) -> bool:
    return self._busy

  def start(self) -> None:
    if self._running or self._memory is None:
      return
    self._running = True
    self._thread = threading.Thread(target=self._loop, name="maira-memory-worker", daemon=True)
    self._thread.start()
    logger.info("[MAIRA MEMORY] worker started")

  def stop(self) -> None:
    if not self._running:
      return
    self._running = False
    self._queue.put(None)
    if self._thread and self._thread.is_alive():
      self._thread.join(timeout=2.0)
    self._thread = None
    logger.info("[MAIRA MEMORY] worker stopped")

  def enqueue(self, text: str, *, role: str = "user") -> None:
    if not self._running or self._memory is None:
      return
    cleaned = text.strip()
    if not cleaned:
      return
    self._queue.put(MemoryJob(text=cleaned, role=role))

  def _loop(self) -> None:
    while self._running:
      try:
        job = self._queue.get(timeout=0.5)
      except queue.Empty:
        continue
      if job is None:
        break
      self._busy = True
      try:
        self._handle(job)
      except Exception as exc:  # noqa: BLE001
        logger.warning("[MAIRA MEMORY] background job failed: {}", exc)
      finally:
        self._busy = False

  def _handle(self, job: MemoryJob) -> None:
    assert self._memory is not None
    decision = self._policy.evaluate(job.text, role=job.role)
    if not decision.should_store:
      logger.debug("[MAIRA MEMORY] skip store: {}", decision.reason)
      return
    self._memory.store(
      category=decision.category or MemoryCategory.NOTE,
      title=decision.title or job.text[:48],
      body=job.text,
    )
    logger.info("[MAIRA MEMORY] stored ({})", decision.reason)
