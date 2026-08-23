"""Decide which utterances become long-term memories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from maira.core.domain.value_objects import MemoryCategory

_REMEMBER = re.compile(r"\b(remember|don't forget|do not forget|note that|my name is)\b", re.I)
_PREF = re.compile(r"\b(i (prefer|like|hate|always|never)|call me)\b", re.I)
_TRIVIAL = re.compile(r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|bye)[.!]?$", re.I)


@dataclass(frozen=True)
class MemoryDecision:
  should_store: bool
  reason: str
  category: MemoryCategory | None = None
  title: str | None = None


class MemoryPolicy:
  def __init__(self, *, min_chars: int = 24) -> None:
    self._min_chars = min_chars

  def evaluate(self, text: str, *, role: str = "user") -> MemoryDecision:
    cleaned = " ".join(text.strip().split())
    if role != "user":
      return MemoryDecision(False, "assistant_turn")
    if len(cleaned) < self._min_chars:
      return MemoryDecision(False, "too_short")
    if _TRIVIAL.match(cleaned):
      return MemoryDecision(False, "trivial")
    if _REMEMBER.search(cleaned):
      return MemoryDecision(True, "explicit_remember", MemoryCategory.NOTE, cleaned[:48])
    if _PREF.search(cleaned):
      return MemoryDecision(True, "preference", MemoryCategory.PREFERENCE, cleaned[:48])
    return MemoryDecision(False, "not_candidate")
