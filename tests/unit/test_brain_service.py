"""Unit tests for brain module."""

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import MessageRole
from maira.core.interfaces.llm import LLMProvider
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_ERROR, TOPIC_TOKEN


class FakeLLM(LLMProvider):
  def __init__(self, tokens: list[str] | None = None, available: bool = True) -> None:
    self._tokens = tokens or ["Hi", " there"]
    self._available = available
    self.calls: list[Sequence[dict[str, str]]] = []

  def is_available(self) -> bool:
    return self._available

  def list_models(self) -> list[str]:
    return ["fake"]

  def chat_stream(self, messages: Sequence[dict[str, str]], *, options: dict | None = None) -> Iterator[str]:
    del options
    self.calls.append(list(messages))
    yield from self._tokens


@pytest.fixture
def repo(tmp_path: Path) -> ConversationRepository:
  storage = SqliteStorage(tmp_path / "brain.db")
  apply_migrations(storage)
  return ConversationRepository(storage)


def test_conversation_session_tracks_messages() -> None:
  session = ConversationSession()
  session.add_user_message("Hello")
  session.add_assistant_message("Hi")

  messages = session.get_messages()
  assert len(messages) == 2
  assert messages[0].role == MessageRole.USER
  assert messages[1].role == MessageRole.ASSISTANT
  assert session.to_llm_payload() == [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi"},
  ]


def test_brain_service_streams_and_stores_history(repo: ConversationRepository) -> None:
  bus = EventBus()
  tokens: list[str] = []
  completed: list[str] = []

  bus.subscribe(TOPIC_TOKEN, lambda p: tokens.append(p["token"]))
  bus.subscribe(TOPIC_COMPLETE, lambda p: completed.append(p["content"]))

  brain = BrainService(FakeLLM(["A", "B"]), bus, repo)
  brain.send_message("Hello")

  assert tokens == ["A", "B"]
  assert completed == ["AB"]
  history = brain.get_history()
  assert history[-1].content == "AB"
  assert history[-2].content == "Hello"

  stored = repo.get_messages(brain.get_active_conversation().id)
  assert len(stored) == 2
  assert stored[0].content == "Hello"
  assert stored[1].content == "AB"
  assert brain.get_active_conversation().title == "Hello"


def test_brain_service_publishes_error_when_unavailable(repo: ConversationRepository) -> None:
  bus = EventBus()
  errors: list[str] = []
  bus.subscribe(TOPIC_ERROR, lambda p: errors.append(p["message"]))

  brain = BrainService(FakeLLM(available=False), bus, repo)
  brain.send_message("Hello")

  assert errors
  assert "can't reach the local AI model" in errors[0]
  assert brain.get_history() == []
  assert repo.get_messages(brain.get_active_conversation().id) == []


def test_brain_service_includes_system_prompt_and_limits_history(repo: ConversationRepository) -> None:
  bus = EventBus()
  llm = FakeLLM(["ok"])
  brain = BrainService(llm, bus, repo, history_messages=4, log_latency=False)
  for index in range(6):
    brain.send_message(f"msg-{index}")
  last_call = llm.calls[-1]
  assert last_call[0]["role"] == "system"
  assert "You are Maira" in last_call[0]["content"]
  # system + last 4 conversation messages
  assert len(last_call) == 5


def test_brain_service_empty_message_noop(repo: ConversationRepository) -> None:
  bus = EventBus()
  llm = FakeLLM(["x"])
  brain = BrainService(llm, bus, repo, log_latency=False)
  brain.send_message("   ")
  assert llm.calls == []
  assert brain.get_history() == []


def test_brain_service_new_conversation(repo: ConversationRepository) -> None:
  bus = EventBus()
  brain = BrainService(FakeLLM(["ok"]), bus, repo)
  brain.send_message("First")
  first_id = brain.get_active_conversation().id

  created = brain.new_conversation()
  assert created.id != first_id
  assert brain.get_history() == []
  assert created.title == "New chat"


def test_brain_service_list_and_open_conversation(repo: ConversationRepository) -> None:
  bus = EventBus()
  brain = BrainService(FakeLLM(["one"]), bus, repo)
  brain.send_message("alpha chat")
  first_id = brain.get_active_conversation().id

  brain.new_conversation()
  brain.send_message("beta chat")
  second_id = brain.get_active_conversation().id

  listed = brain.list_conversations()
  assert [item.id for item in listed[:2]] == [second_id, first_id]

  opened = brain.open_conversation(first_id)
  assert opened.id == first_id
  assert [message.content for message in brain.get_history()] == ["alpha chat", "one"]
  assert brain.get_active_conversation().title == "alpha chat"


def test_brain_service_injects_memory_context(repo: ConversationRepository) -> None:
  from datetime import datetime, timezone

  from maira.core.domain.entities import MemoryEntry
  from maira.core.domain.value_objects import MemoryCategory
  from maira.modules.brain.streaming import TOPIC_CONTEXT
  from tests.unit.test_context_assembly import FakeMemory

  now = datetime.now(timezone.utc)
  memory = FakeMemory(
    [
      MemoryEntry(
        id="1",
        category=MemoryCategory.PREFERENCE,
        title="Name",
        body="My name is Alex",
        created_at=now,
        updated_at=now,
      )
    ]
  )

  llm = FakeLLM(["Alex"])
  bus = EventBus()
  contexts: list[dict] = []
  bus.subscribe(TOPIC_CONTEXT, lambda payload: contexts.append(payload))

  brain = BrainService(llm, bus, repo, memory=memory, max_memories=3)
  brain.send_message("What is my name?")

  assert contexts
  assert "Name" in contexts[0]["memory_titles"]
  assert llm.calls
  assert llm.calls[0][0]["role"] == "system"
  assert "My name is Alex" in llm.calls[0][0]["content"]
  assert llm.calls[0][1]["role"] == "user"
