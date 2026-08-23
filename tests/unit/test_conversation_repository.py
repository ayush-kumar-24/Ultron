"""Unit tests for conversation repository and migrations."""

from pathlib import Path

import pytest

from maira.core.domain.entities import Message
from maira.core.domain.value_objects import MessageRole
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import (
  apply_migrations,
  current_version,
)
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository


@pytest.fixture
def storage(tmp_path: Path) -> SqliteStorage:
  db = SqliteStorage(tmp_path / "test.db")
  apply_migrations(db)
  yield db
  db.close()


@pytest.fixture
def repo(storage: SqliteStorage) -> ConversationRepository:
  return ConversationRepository(storage)


def test_migrations_are_idempotent(tmp_path: Path) -> None:
  db = SqliteStorage(tmp_path / "mig.db")
  first = apply_migrations(db)
  second = apply_migrations(db)
  assert first == [1, 2, 3]
  assert second == []
  assert current_version(db) == 3
  db.close()


def test_create_and_list_conversations(repo: ConversationRepository) -> None:
  first = repo.create_conversation("Alpha")
  second = repo.create_conversation("Beta")

  listed = repo.list_conversations()
  assert [item.id for item in listed] == [second.id, first.id]
  assert repo.get_latest_conversation() is not None
  assert repo.get_latest_conversation().id == second.id  # type: ignore[union-attr]


def test_add_and_get_messages(repo: ConversationRepository) -> None:
  conversation = repo.create_conversation()
  user = repo.add_message(
    conversation.id,
    Message(role=MessageRole.USER, content="Hello"),
  )
  assistant = repo.add_message(
    conversation.id,
    Message(role=MessageRole.ASSISTANT, content="Hi there"),
  )

  messages = repo.get_messages(conversation.id)
  assert len(messages) == 2
  assert messages[0].id == user.id
  assert messages[0].role == MessageRole.USER
  assert messages[0].content == "Hello"
  assert messages[1].id == assistant.id
  assert messages[1].content == "Hi there"


def test_update_title_and_touch(repo: ConversationRepository) -> None:
  conversation = repo.create_conversation("New chat")
  repo.update_title(conversation.id, "My topic")
  updated = repo.get_conversation(conversation.id)
  assert updated is not None
  assert updated.title == "My topic"
  assert updated.updated_at >= conversation.updated_at
