"""Brain looks at the screen only when asked, and keeps OCR out of history."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.llm import LLMProvider
from maira.core.interfaces.screen import Screen, ScreenReading
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.brain.service import BrainService


class FakeLLM(LLMProvider):
  def __init__(self) -> None:
    self.calls: list[Sequence[dict[str, str]]] = []

  def is_available(self) -> bool:
    return True

  def list_models(self) -> list[str]:
    return ["fake"]

  def chat_stream(self, messages, *, options=None) -> Iterator[str]:
    del options
    self.calls.append(list(messages))
    yield "ok"


class FakeVision(Screen):
  def __init__(self, *, ok: bool = True, text: str = "KeyError: alembic_version") -> None:
    self._ok = ok
    self._text = text
    self.reads = 0

  def is_available(self) -> tuple[bool, str]:
    return (True, "ready") if self._ok else (False, "no display")

  def read_screen(self, *, display=None, region=None) -> ScreenReading:
    self.reads += 1
    if not self._ok:
      return ScreenReading(ok=False, summary="no display")
    return ScreenReading(ok=True, summary="Read 1 line(s).", text=self._text, lines=(self._text,))

  def as_context(self, reading: ScreenReading) -> str:
    if not reading.ok:
      return f"[screen unavailable: {reading.summary}]"
    return f"[what is on screen right now]\n{reading.text}"


@pytest.fixture
def repo(tmp_path: Path) -> ConversationRepository:
  storage = SqliteStorage(tmp_path / "vision_brain.db")
  apply_migrations(storage)
  return ConversationRepository(storage)


def _system_prompt(llm: FakeLLM) -> str:
  return llm.calls[-1][0]["content"]


def test_screen_is_read_when_the_user_asks(repo: ConversationRepository) -> None:
  llm, vision = FakeLLM(), FakeVision()
  brain = BrainService(llm, EventBus(), repo, vision=vision, log_latency=False)
  brain.send_message("what does this error say?")
  assert vision.reads == 1
  assert "KeyError: alembic_version" in _system_prompt(llm)


def test_screen_is_not_read_for_ordinary_chat(repo: ConversationRepository) -> None:
  llm, vision = FakeLLM(), FakeVision()
  brain = BrainService(llm, EventBus(), repo, vision=vision, log_latency=False)
  brain.send_message("what is the capital of France")
  assert vision.reads == 0
  assert "what is on screen" not in _system_prompt(llm)


def test_ocr_text_stays_out_of_conversation_history(repo: ConversationRepository) -> None:
  """The dump belongs in the prompt, not in what Ultron remembers saying."""
  llm, vision = FakeLLM(), FakeVision()
  brain = BrainService(llm, EventBus(), repo, vision=vision, log_latency=False)
  brain.send_message("read my screen")
  user_turns = [m for m in llm.calls[-1] if m["role"] == "user"]
  assert user_turns[-1]["content"] == "read my screen"
  assert "KeyError" not in user_turns[-1]["content"]


def test_unavailable_screen_is_explained_to_the_model(repo: ConversationRepository) -> None:
  llm, vision = FakeLLM(), FakeVision(ok=False)
  brain = BrainService(llm, EventBus(), repo, vision=vision, log_latency=False)
  brain.send_message("what's on my screen?")
  prompt = _system_prompt(llm)
  assert "could not be read" in prompt
  assert "no display" in prompt


def test_works_with_no_vision_wired(repo: ConversationRepository) -> None:
  llm = FakeLLM()
  brain = BrainService(llm, EventBus(), repo, log_latency=False)
  brain.send_message("what's on my screen?")
  assert "what is on screen" not in _system_prompt(llm)
