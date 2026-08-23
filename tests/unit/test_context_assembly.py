"""Unit tests for context assembly."""

from datetime import datetime, timezone

from maira.core.domain.entities import MemoryEntry
from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.memory import Memory
from maira.modules.brain.context import ContextAssembler


class FakeMemory(Memory):
  def __init__(self, entries: list[MemoryEntry]) -> None:
    self._entries = entries

  def store(self, *, category, title, body):  # noqa: ANN001
    raise NotImplementedError

  def get(self, memory_id: str):
    return next((item for item in self._entries if item.id == memory_id), None)

  def list_memories(self, category=None):  # noqa: ANN001
    return list(self._entries)

  def search_keyword(self, query: str, *, category=None):  # noqa: ANN001
    return list(self._entries)

  def recall(self, query: str, *, k: int = 5, category=None):  # noqa: ANN001
    return self._entries[:k]

  def search(self, query: str, *, category=None):  # noqa: ANN001
    return self.recall(query)

  def update(self, memory_id: str, *, category, title, body):  # noqa: ANN001
    raise NotImplementedError

  def delete(self, memory_id: str) -> None:
    raise NotImplementedError

  def is_semantic_available(self) -> bool:
    return False


def _entry(memory_id: str, title: str, body: str) -> MemoryEntry:
  now = datetime.now(timezone.utc)
  return MemoryEntry(
    id=memory_id,
    category=MemoryCategory.PREFERENCE,
    title=title,
    body=body,
    created_at=now,
    updated_at=now,
  )


def test_assemble_includes_memory_block() -> None:
  memory = FakeMemory([_entry("1", "Name", "My name is Alex")])
  assembler = ContextAssembler(memory, max_memories=3, max_context_chars=2000)
  result = assembler.assemble("What is my name?")

  assert result.memory_ids == ("1",)
  assert "My name is Alex" in result.system_prompt
  assert "<<<MAIRA_MEMORY>>>" in result.system_prompt


def test_assemble_respects_budget() -> None:
  memory = FakeMemory(
    [
      _entry("1", "One", "A" * 200),
      _entry("2", "Two", "B" * 200),
      _entry("3", "Three", "C" * 200),
    ]
  )
  # Identity (~650) + one memory fits; three should not.
  assembler = ContextAssembler(memory, max_memories=5, max_context_chars=1100)
  result = assembler.assemble("tell me things")

  assert len(result.memories) >= 1
  assert len(result.system_prompt) <= 1100
  assert len(result.memories) < 3


def test_assemble_empty_without_memory() -> None:
  assembler = ContextAssembler(None)
  result = assembler.assemble("hello")
  assert result.memories == ()
  assert "You are Ultron" in result.system_prompt
  assert "Llama" in result.system_prompt or "model name" in result.system_prompt
