"""Integration tests for conversation persistence across BrainService instances."""

from pathlib import Path

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.llm import LLMProvider
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.brain.service import BrainService


class FakeLLM(LLMProvider):
  def __init__(self, reply: str = "pong") -> None:
    self._reply = reply

  def is_available(self) -> bool:
    return True

  def list_models(self) -> list[str]:
    return ["fake"]

  def chat_stream(self, messages, *, options=None):  # noqa: ANN001
    del options
    yield self._reply


def test_conversation_survives_service_reopen(tmp_path: Path) -> None:
  db_path = tmp_path / "persist.db"
  storage = SqliteStorage(db_path)
  apply_migrations(storage)
  repo = ConversationRepository(storage)

  brain = BrainService(FakeLLM("hello back"), EventBus(), repo)
  brain.send_message("persist me")
  conversation_id = brain.get_active_conversation().id
  storage.close()

  storage2 = SqliteStorage(db_path)
  apply_migrations(storage2)
  repo2 = ConversationRepository(storage2)
  brain2 = BrainService(FakeLLM("ignored"), EventBus(), repo2)

  assert brain2.get_active_conversation().id == conversation_id
  history = brain2.get_history()
  assert len(history) == 2
  assert history[0].content == "persist me"
  assert history[1].content == "hello back"
  assert brain2.get_active_conversation().title == "persist me"
  storage2.close()


def test_new_chat_leaves_old_conversation_intact(tmp_path: Path) -> None:
  storage = SqliteStorage(tmp_path / "two.db")
  apply_migrations(storage)
  repo = ConversationRepository(storage)

  brain = BrainService(FakeLLM("one"), EventBus(), repo)
  brain.send_message("old chat")
  old_id = brain.get_active_conversation().id

  brain.new_conversation()
  brain.send_message("new chat")
  new_id = brain.get_active_conversation().id

  assert old_id != new_id
  old_messages = repo.get_messages(old_id)
  new_messages = repo.get_messages(new_id)
  assert [m.content for m in old_messages] == ["old chat", "one"]
  assert [m.content for m in new_messages] == ["new chat", "one"]
  storage.close()
