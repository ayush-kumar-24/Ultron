"""Phase 1 HTTP API — fake brain/memory, no real LLM or screen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maira.api.overlay import OverlayStore
from maira.api.server import create_app
from maira.app.container import Container
from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Conversation, Message
from maira.core.domain.value_objects import MemoryCategory, MessageRole
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  ConversationRepository,
  MemoryRepository,
)
from maira.modules.brain.service import ConversationNotFoundError
from maira.modules.memory.service import MemoryService


class FakeLlm:
  model = "test-model"

  def is_available(self, *, force: bool = False) -> bool:
    return True


class FakeBrain:
  def __init__(self, bus: EventBus, repo: ConversationRepository) -> None:
    self._bus = bus
    self._repo = repo
    self._active: Conversation | None = None
    self.fail = False
    self.raise_error: Exception | None = None

  def get_active_conversation(self) -> Conversation:
    if self._active is not None:
      return self._active
    latest = self._repo.get_latest_conversation()
    if latest is None:
      latest = self._repo.create_conversation()
    self._active = latest
    return latest

  def open_conversation(self, conversation_id: str) -> Conversation:
    conversation = self._repo.get_conversation(conversation_id)
    if conversation is None:
      raise ConversationNotFoundError(f"Conversation not found: {conversation_id}")
    self._active = conversation
    return conversation

  def new_conversation(self) -> Conversation:
    self._active = self._repo.create_conversation()
    return self._active

  def send_message(self, text: str) -> None:
    active = self.get_active_conversation()
    self.send_in_conversation(active.id, text)

  def send_in_conversation(self, conversation_id: str, text: str) -> None:
    self.open_conversation(conversation_id)
    if self.raise_error is not None:
      raise self.raise_error
    self._repo.add_message(conversation_id, Message(role=MessageRole.USER, content=text))
    if self.fail:
      self._bus.publish("brain.error", {"message": "Ollama is down"})
      return
    self._bus.publish("brain.token", {"token": "Hello"})
    self._bus.publish("brain.token", {"token": " world"})
    self._repo.add_message(
      conversation_id,
      Message(role=MessageRole.ASSISTANT, content="Hello world"),
    )
    self._bus.publish("brain.complete", {"content": "Hello world"})


@pytest.fixture
def api(tmp_path: Path):
  settings = load_settings()
  storage = SqliteStorage(tmp_path / "api.db")
  apply_migrations(storage)
  repo = ConversationRepository(storage)
  memory = MemoryService(MemoryRepository(storage))
  bus = EventBus()
  brain = FakeBrain(bus, repo)
  container = Container()
  container.register_instance("settings", settings)
  container.register_instance("event_bus", bus)
  container.register_instance("conversation_repository", repo)
  container.register_instance("memory", memory)
  container.register_instance("overlay", OverlayStore(tmp_path / "user_profile.json"))
  container.register_instance("llm", FakeLlm())
  container.register_instance("brain", brain)
  client = TestClient(create_app(container))
  yield client, brain, memory, repo
  storage.close()


def _stream_events(client: TestClient, body: dict) -> tuple[list[dict], object]:
  response = client.post("/api/chat/stream", json=body)
  events = []
  for line in response.text.splitlines():
    line = line.strip()
    if not line.startswith("data:"):
      continue
    events.append(json.loads(line[5:].strip()))
  return events, response


def test_health_ok(api) -> None:
  client, _, _, _ = api
  response = client.get("/api/system/health")
  assert response.status_code == 200
  assert response.headers["content-type"].startswith("application/json")
  body = response.json()
  assert body["ok"] is True
  assert body["local"] is True
  assert body["model"] == "test-model"
  assert body["memoryCount"] == 0
  assert "latencyMs" in body


def test_unimplemented_endpoint_is_json_404(api) -> None:
  client, _, _, _ = api
  response = client.get("/api/overview")
  assert response.status_code == 404
  assert response.headers["content-type"].startswith("application/json")
  assert "detail" in response.json()


def test_me_get_and_patch(api) -> None:
  client, _, _, _ = api
  me = client.get("/api/me").json()
  assert me["id"] == "local"
  assert me["name"] == "Ayush"
  updated = client.patch("/api/me", json={"name": "Ultron User"}).json()
  assert updated["name"] == "Ultron User"
  assert updated["initials"] == "UU"
  assert client.get("/api/me").json()["name"] == "Ultron User"


def test_settings_get_and_patch(api) -> None:
  client, _, _, _ = api
  settings = client.get("/api/settings").json()
  assert "general" in settings
  assert "ai" in settings
  assert settings["ai"]["model"]  # live ollama model from yaml
  patched = client.patch("/api/settings/general", json={"theme": "system"}).json()
  assert patched["theme"] == "system"
  missing = client.patch("/api/settings/nope", json={"x": 1})
  assert missing.status_code == 404
  assert "detail" in missing.json()


def test_conversations_crud_and_404(api) -> None:
  client, _, _, _ = api
  created = client.post("/api/conversations", json={"title": "First"}).json()
  assert created["title"] == "First"
  assert created["pinned"] is False
  listed = client.get("/api/conversations").json()
  assert listed[0]["id"] == created["id"]
  got = client.get(f"/api/conversations/{created['id']}").json()
  assert got["id"] == created["id"]
  pinned = client.patch(f"/api/conversations/{created['id']}", json={"pinned": True}).json()
  assert pinned["pinned"] is True
  messages = client.get(f"/api/conversations/{created['id']}/messages").json()
  assert messages == []
  deleted = client.delete(f"/api/conversations/{created['id']}")
  assert deleted.status_code == 204
  assert client.get(f"/api/conversations/{created['id']}").status_code == 404
  assert client.get("/api/conversations/missing").status_code == 404
  assert client.get("/api/conversations/missing/messages").status_code == 404


def test_chat_stream_success(api) -> None:
  client, _, _, _ = api
  created = client.post("/api/conversations", json={"title": "New conversation"}).json()
  events, response = _stream_events(
    client,
    {"conversationId": created["id"], "text": "Hello Ultron", "context": None},
  )
  assert response.status_code == 200
  assert response.headers["content-type"].startswith("text/event-stream")
  types = [event["type"] for event in events]
  assert types[0] == "user"
  assert events[0]["payload"]["text"] == "Hello Ultron"
  assert "thinking" in [event.get("state") for event in events if event["type"] == "state"]
  assert "speaking" in [event.get("state") for event in events if event["type"] == "state"]
  tokens = "".join(event["text"] for event in events if event["type"] == "token")
  assert tokens == "Hello world"
  done = next(event for event in events if event["type"] == "done")
  assert done["payload"]["message"]["text"] == "Hello world"
  assert done["payload"]["message"]["role"] == "assistant"
  stored = client.get(f"/api/conversations/{created['id']}/messages").json()
  assert [item["role"] for item in stored] == ["user", "assistant"]


def test_chat_stream_missing_conversation(api) -> None:
  client, _, _, _ = api
  response = client.post(
    "/api/chat/stream",
    json={"conversationId": "does-not-exist", "text": "hi", "context": None},
  )
  assert response.status_code == 404
  assert "detail" in response.json()


def test_chat_stream_empty_text(api) -> None:
  client, _, _, _ = api
  created = client.post("/api/conversations", json={}).json()
  response = client.post(
    "/api/chat/stream",
    json={"conversationId": created["id"], "text": "   ", "context": None},
  )
  assert response.status_code == 400


def test_chat_stream_model_failure(api) -> None:
  client, brain, _, _ = api
  brain.fail = True
  created = client.post("/api/conversations", json={"title": "Fail"}).json()
  events, response = _stream_events(
    client,
    {"conversationId": created["id"], "text": "hi", "context": None},
  )
  assert response.status_code == 200
  error = next(event for event in events if event["type"] == "error")
  assert "Ollama" in error["detail"]


def test_chat_stream_service_failure(api) -> None:
  client, brain, _, _ = api
  brain.raise_error = RuntimeError("boom")
  created = client.post("/api/conversations", json={"title": "Boom"}).json()
  events, _ = _stream_events(
    client,
    {"conversationId": created["id"], "text": "hi", "context": None},
  )
  error = next(event for event in events if event["type"] == "error")
  assert error["status"] == 500


def test_memories_crud_and_delete_is_gone(api) -> None:
  client, _, _, _ = api
  created = client.post(
    "/api/memories",
    json={"text": "Prefers local models", "category": "preferences", "importance": "high"},
  ).json()
  assert created["text"] == "Prefers local models"
  assert created["category"] == "preferences"
  assert created["pinned"] is False
  listed = client.get("/api/memories", params={"category": "preferences"}).json()
  assert listed[0]["id"] == created["id"]
  pinned = client.patch(f"/api/memories/{created['id']}", json={"pinned": True}).json()
  assert pinned["pinned"] is True
  stats = client.get("/api/memory/stats").json()
  assert stats["total"] == 1
  assert stats["pinned"] == 1
  assert stats["byCategory"]["preferences"] == 1
  deleted = client.delete(f"/api/memories/{created['id']}")
  assert deleted.status_code == 204
  assert client.get("/api/memories").json() == []
  assert client.get("/api/memory/stats").json()["total"] == 0
  assert client.delete(f"/api/memories/{created['id']}").status_code == 404
  assert client.patch("/api/memories/missing", json={"pinned": True}).status_code == 404


def test_save_message_to_memory(api) -> None:
  client, _, _, repo = api
  conversation = repo.create_conversation()
  message = repo.add_message(
    conversation.id,
    Message(role=MessageRole.ASSISTANT, content="Remember this fact"),
  )
  saved = client.post(
    f"/api/messages/{message.id}/memory",
    json={"text": "Remember this fact"},
  ).json()
  assert saved["category"] == "conversations"
  assert saved["text"] == "Remember this fact"
  missing = client.post("/api/messages/nope/memory", json={"text": "x"})
  assert missing.status_code == 404


def test_legacy_preference_maps_to_preferences_filter(api) -> None:
  client, _, memory, _ = api
  memory.store(
    category=MemoryCategory.PREFERENCE,
    title="Dark mode",
    body="I prefer dark mode",
  )
  listed = client.get("/api/memories", params={"category": "preferences"}).json()
  assert len(listed) == 1
  assert listed[0]["category"] == "preferences"
