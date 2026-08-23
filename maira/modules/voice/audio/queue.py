"""Thread-safe FIFO audio/speech work queue with cancel/clear."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class QueuedSpeech:
  priority: int
  text: str = field(compare=False)
  meta: dict[str, Any] = field(default_factory=dict, compare=False)


class AudioQueue:
  """Priority FIFO for TTS chunks. Lower priority number = sooner."""

  def __init__(self) -> None:
    self._queue: queue.PriorityQueue[QueuedSpeech] = queue.PriorityQueue()
    self._seq = 0
    self._lock = threading.Lock()
    self._cancelled = threading.Event()

  def put(self, text: str, *, priority: int = 100, meta: dict | None = None) -> None:
    cleaned = text.strip()
    if not cleaned or self._cancelled.is_set():
      return
    with self._lock:
      # Stabilize FIFO among equal priorities
      item = QueuedSpeech(priority=priority * 1_000_000 + self._seq, text=cleaned, meta=meta or {})
      self._seq += 1
    self._queue.put(item)

  def get(self, timeout: float | None = 0.2) -> QueuedSpeech | None:
    if self._cancelled.is_set():
      return None
    try:
      return self._queue.get(timeout=timeout)
    except queue.Empty:
      return None

  def clear(self) -> None:
    with self._lock:
      while True:
        try:
          self._queue.get_nowait()
        except queue.Empty:
          break

  def empty(self) -> bool:
    return self._queue.empty()

  def cancel_all(self) -> None:
    self._cancelled.set()
    self.clear()

  def reset(self) -> None:
    self._cancelled.clear()
    self.clear()
    with self._lock:
      self._seq = 0

  @property
  def cancelled(self) -> bool:
    return self._cancelled.is_set()
