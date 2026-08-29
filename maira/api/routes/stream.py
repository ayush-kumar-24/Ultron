"""Server-sent events — background activity pushed to whatever page is open.

The frontend's EventSource previously pointed at /api/events, which is the
calendar REST endpoint; it received JSON instead of an event stream and
reconnected forever. This is the dedicated stream.
"""

from __future__ import annotations

import json
import queue
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from maira.api.deps import get_event_bus

router = APIRouter(tags=["stream"])

TOPICS = ("automation", "automation.notify", "automation.changed", "desktop.ran")
QUEUE_MAX = 256
HEARTBEAT_SECONDS = 20.0


def _frame(event_type: str, payload: dict) -> str:
  body = json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False)
  return f"data: {body}\n\n"


class ActivityStream:
  """Fans event-bus topics into SSE frames for one browser connection."""

  def __init__(self, bus, *, topics: tuple[str, ...] = TOPICS, heartbeat: float = HEARTBEAT_SECONDS) -> None:
    self._bus = bus
    self._topics = topics
    self._heartbeat = heartbeat
    self._events: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=QUEUE_MAX)
    self._handlers: dict[str, object] = {}

  def subscribe(self) -> None:
    for topic in self._topics:
      handler = self._forward(topic)
      self._handlers[topic] = handler
      self._bus.subscribe(topic, handler)

  def close(self) -> None:
    for topic, handler in self._handlers.items():
      self._bus.unsubscribe(topic, handler)
    self._handlers.clear()

  def _forward(self, topic: str):
    def handler(payload) -> None:
      try:
        self._events.put_nowait((topic, dict(payload or {})))
      except queue.Full:  # pragma: no cover - slow client
        pass

    return handler

  def frames(self, stop=None) -> Iterator[str]:
    self.subscribe()
    try:
      yield _frame("ready", {"topics": list(self._topics)})
      while stop is None or not stop.is_set():
        try:
          topic, payload = self._events.get(timeout=self._heartbeat)
        except queue.Empty:
          yield ": keep-alive\n\n"
          continue
        yield _frame(topic.split(".")[0], payload)
    finally:
      self.close()


@router.get("/stream")
def stream() -> StreamingResponse:
  activity = ActivityStream(get_event_bus())
  return StreamingResponse(
    activity.frames(),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
  )
