"""Context window assembly — selects relevant memories for the LLM prompt."""

from __future__ import annotations

from dataclasses import dataclass

from maira.core.domain.entities import MemoryEntry
from maira.core.interfaces.memory import Memory

MAIRA_IDENTITY_PROMPT = (
  "You are Ultron — a warm, sharp personal companion for an Indian user.\n"
  "Talk like someone they trust: natural and direct — not a corporate assistant "
  "or chatbot script.\n"
  "\n"
  "Language: Mirror the user (English, Hindi, or everyday Hinglish). "
  "Fluent urban Indian tone — not textbook Hindi, not forced slang every line. "
  "Avoid stiff lines like \"Certainly\", \"I'd be happy to\", \"As an AI\", "
  "\"How may I assist you\".\n"
  "\n"
  "Style: Simple questions → 1–3 sentences. Bullets only when a list helps. "
  "Long detail only when asked. Don't repeat their question. "
  "If they ask to remind/schedule/automate something at a time, acknowledge clearly. "
  "Never say you are Llama, Meta, Ollama, Qwen, or any model name. "
  "Warmth and personality are fine; don't claim a human body or physical senses."
)

MAIRA_VOICE_PROMPT = (
  "You are Ultron — a warm Indian companion speaking out loud.\n"
  "One short spoken reply (two sentences max). No lists, markdown, or preamble.\n"
  "Mirror their language: English, Hindi, or natural Hinglish — same mix they used.\n"
  "Sound like a quick reply to a friend, not an AI assistant script.\n"
  "Skip stiff openers (\"Certainly\", \"Of course\", \"I'd be happy to\").\n"
  "If unclear, ask them to say it again briefly — don't invent their request.\n"
  "Never say you are Llama, Meta, Ollama, or another model."
)


@dataclass(frozen=True)
class AssembledContext:
  memories: tuple[MemoryEntry, ...]
  system_prompt: str
  char_count: int

  @property
  def memory_ids(self) -> tuple[str, ...]:
    return tuple(entry.id for entry in self.memories)

  @property
  def memory_titles(self) -> tuple[str, ...]:
    return tuple(entry.title for entry in self.memories)


def identity_context() -> AssembledContext:
  return AssembledContext(
    memories=(),
    system_prompt=MAIRA_IDENTITY_PROMPT,
    char_count=len(MAIRA_IDENTITY_PROMPT),
  )


EMPTY_CONTEXT = identity_context()


class ContextAssembler:
  """Builds a system prompt from identity + recalled memories within a char budget."""

  def __init__(
    self,
    memory: Memory | None,
    *,
    max_memories: int = 5,
    max_context_chars: int = 2000,
  ) -> None:
    self._memory = memory
    self._max_memories = max(0, max_memories)
    self._max_context_chars = max(0, max_context_chars)

  def assemble(self, query: str, *, recall_mode: str = "semantic") -> AssembledContext:
    cleaned = query.strip()
    if not cleaned or self._memory is None or self._max_memories == 0:
      return identity_context()

    if recall_mode == "keyword" and hasattr(self._memory, "search_keyword"):
      recalled = self._memory.search_keyword(cleaned)[: self._max_memories]
    else:
      recalled = self._memory.recall(cleaned, k=self._max_memories)
    if not recalled:
      return identity_context()

    selected = self._fit_budget(recalled)
    if not selected:
      return identity_context()

    system_prompt = self._format_system_prompt(selected)
    return AssembledContext(
      memories=tuple(selected),
      system_prompt=system_prompt,
      char_count=len(system_prompt),
    )

  def _fit_budget(self, memories: list[MemoryEntry]) -> list[MemoryEntry]:
    """Keep highest-ranked memories that fit the character budget."""
    selected: list[MemoryEntry] = []
    for entry in memories:
      candidate = [*selected, entry]
      prompt = self._format_system_prompt(candidate)
      if len(prompt) <= self._max_context_chars:
        selected.append(entry)
        continue
      if not selected:
        truncated = self._truncate_to_fit(entry)
        if truncated is not None:
          selected.append(truncated)
      break
    return selected

  def _truncate_to_fit(self, entry: MemoryEntry) -> MemoryEntry | None:
    body = entry.body
    while True:
      candidate = MemoryEntry(
        id=entry.id,
        category=entry.category,
        title=entry.title,
        body=body if body == entry.body else f"{body}...",
        created_at=entry.created_at,
        updated_at=entry.updated_at,
      )
      prompt = self._format_system_prompt([candidate])
      if len(prompt) <= self._max_context_chars:
        return candidate
      if len(body) <= 20:
        return None
      body = body[: max(20, len(body) - 40)]

  @staticmethod
  def _format_memory_block(entry: MemoryEntry) -> str:
    body = entry.body.strip()
    if body:
      return f"[{entry.category.value}] {entry.title}\n{body}"
    return f"[{entry.category.value}] {entry.title}"

  def _format_system_prompt(self, memories: list[MemoryEntry]) -> str:
    if not memories:
      return MAIRA_IDENTITY_PROMPT

    blocks = "\n\n".join(self._format_memory_block(entry) for entry in memories)
    return (
      f"{MAIRA_IDENTITY_PROMPT}\n\n"
      "Use the following remembered facts about the user when relevant. "
      "If a fact does not help answer the question, ignore it.\n\n"
      "<<<MAIRA_MEMORY>>>\n"
      f"{blocks}\n"
      "<<<END_MAIRA_MEMORY>>>"
    )
