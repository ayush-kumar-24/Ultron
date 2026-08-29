"""Regressions from a real-user stress pass: concurrency, junk input, edge times."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maira.api.overlay import OverlayStore
from maira.api.parsing import parse_task
from maira.api.routes.stream import ActivityStream
from maira.api.server import create_app
from maira.app.container import Container
from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Message
from maira.core.domain.value_objects import MessageRole
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  ConversationRepository,
  MemoryRepository,
  TaskRepository,
)
from maira.modules.memory.service import MemoryService


class SlowBrain:
  """Streams tokens with a gap, so overlapping turns would interleave."""

  def __init__(self, bus: EventBus, repo: ConversationRepository) -> None:
    self._bus = bus
    self._repo = repo

  def get_active_conversation(self):
    return self._repo.get_latest_conversation() or self._repo.create_conversation()

  def open_conversation(self, conversation_id: str):
    return self._repo.get_conversation(conversation_id)

  def send_in_conversation(self, conversation_id: str, text: str) -> None:
    self._repo.add_message(conversation_id, Message(role=MessageRole.USER, content=text))
    reply = f"reply to {text}"
    for token in reply.split(" "):
      self._bus.publish("brain.token", {"token": token + " "})
      time.sleep(0.03)
    self._repo.add_message(conversation_id, Message(role=MessageRole.ASSISTANT, content=reply))
    self._bus.publish("brain.complete", {"content": reply})


class FakeLlm:
  model = "test-model"

  def __init__(self) -> None:
    self.available = True

  def is_available(self, *, force: bool = False) -> bool:
    return self.available


@pytest.fixture
def api(tmp_path: Path):
  storage = SqliteStorage(tmp_path / "hardening.db")
  apply_migrations(storage)
  repo = ConversationRepository(storage)
  bus = EventBus()

  container = Container()
  container.register_instance("settings", load_settings())
  container.register_instance("event_bus", bus)
  container.register_instance("llm", FakeLlm())
  container.register_instance("overlay", OverlayStore(tmp_path / "profile.json"))
  container.register_instance("conversation_repository", repo)
  container.register_instance("memory", MemoryService(MemoryRepository(storage)))
  container.register_instance("task_repository", TaskRepository(storage))
  container.register_instance("brain", SlowBrain(bus, repo))

  client = TestClient(create_app(container))
  yield client, repo
  storage.close()


def _tokens(text: str) -> str:
  out = []
  for line in text.splitlines():
    line = line.strip()
    if not line.startswith("data:"):
      continue
    event = json.loads(line[5:])
    if event.get("type") == "token":
      out.append(event["text"])
  return "".join(out)


def test_concurrent_chats_do_not_cross_wire(api) -> None:
  """Two turns at once must not braid their tokens into each other's stream."""
  client, repo = api
  first = client.post("/api/conversations", json={"title": "A"}).json()
  second = client.post("/api/conversations", json={"title": "B"}).json()

  def send(conversation_id: str, text: str) -> str:
    return _tokens(
      client.post("/api/chat/stream", json={"conversationId": conversation_id, "text": text}).text
    )

  with concurrent.futures.ThreadPoolExecutor(2) as pool:
    a = pool.submit(send, first["id"], "alpha")
    b = pool.submit(send, second["id"], "bravo")
    text_a, text_b = a.result(timeout=30), b.result(timeout=30)

  assert text_a.strip() == "reply to alpha"
  assert text_b.strip() == "reply to bravo"
  assert "bravo" not in text_a
  assert "alpha" not in text_b

  assert len(repo.get_messages(first["id"])) == 2
  assert len(repo.get_messages(second["id"])) == 2


def test_turn_lock_is_released_after_each_turn(api) -> None:
  client, _ = api
  for _ in range(3):
    response = client.post("/api/chat/stream", json={"text": "ping"})
    assert response.status_code == 200
    assert "reply to ping" in _tokens(response.text)


def test_blank_task_text_is_rejected(api) -> None:
  client, _ = api
  for body in ({"text": "   "}, {"text": ""}, {"title": "  "}, {}):
    assert client.post("/api/tasks", json=body).status_code == 422, body


def test_task_values_are_clamped(api) -> None:
  client, _ = api
  task = client.post(
    "/api/tasks",
    json={"title": "x" * 900, "estimate": -50, "tags": ["a" * 100] + [f"t{i}" for i in range(20)]},
  ).json()
  assert len(task["title"]) == 500
  assert task["estimate"] == 0
  assert len(task["tags"]) == 12
  assert len(task["tags"][0]) == 40

  huge = client.patch(f"/api/tasks/{task['id']}", json={"estimate": 99999}).json()
  assert huge["estimate"] == 24 * 60


def test_a_time_already_past_means_tomorrow() -> None:
  """'remind me at 9am' typed at 6pm must not fire immediately."""
  evening = datetime(2026, 8, 29, 18, 0).astimezone()

  rolled = parse_task("remind me at 9am to stretch", now=evening)
  assert rolled.due is not None
  assert rolled.due.date() == (evening + timedelta(days=1)).date()
  assert rolled.due.hour == 9

  later_today = parse_task("remind me at 11pm to sleep", now=evening)
  assert later_today.due.date() == evening.date()

  # An explicit day is honoured as written, never rolled forward again.
  named = parse_task("call mom tomorrow at 9am", now=evening)
  assert named.due.date() == (evening + timedelta(days=1)).date()


def test_heartbeat_reports_model_availability() -> None:
  """The UI's online indicator is driven by these frames."""
  bus = EventBus()
  state = {"up": True}
  stream = ActivityStream(bus, heartbeat=0.05, probe=lambda: state["up"])
  frames = stream.frames()

  assert json.loads(next(frames).split("data: ", 1)[1])["type"] == "ready"
  first = json.loads(next(frames).split("data: ", 1)[1])
  assert first == {"type": "heartbeat", "payload": {"online": True}}

  state["up"] = False
  assert json.loads(next(frames).split("data: ", 1)[1])["payload"] == {"online": False}
  frames.close()


def test_heartbeat_survives_a_probe_that_raises() -> None:
  def boom() -> bool:
    raise RuntimeError("ollama exploded")

  stream = ActivityStream(EventBus(), heartbeat=0.05, probe=boom)
  frames = stream.frames()
  next(frames)  # ready
  assert json.loads(next(frames).split("data: ", 1)[1])["payload"] == {"online": False}
  frames.close()
