"""Local source search - knowledge, memories and past conversations. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9][a-z0-9_\-+.#]*", re.IGNORECASE)
_STOP = frozenset(
  "a an and are as at be best by can do does for from how i in is it my of on or should the "
  "their there this to use using vs was we what when where which who why will with you your "
  "about into over than then them these those have has had not but if so".split()
)


@dataclass(frozen=True)
class Source:
  kind: str  # knowledge | memory | conversation
  id: str
  title: str
  excerpt: str
  score: float

  @property
  def label(self) -> str:
    return {"knowledge": "Knowledge", "memory": "Memory", "conversation": "Conversation"}.get(
      self.kind, self.kind.title()
    )


def keywords(text: str) -> list[str]:
  """Meaningful words of a question, in order, without duplicates."""
  seen: list[str] = []
  for word in _WORD.findall(text.lower()):
    if len(word) < 3 or word in _STOP or word in seen:
      continue
    seen.append(word)
  return seen


def _score(terms: list[str], title: str, body: str) -> float:
  if not terms:
    return 0.0
  title_l, body_l = title.lower(), body.lower()
  hits = 0.0
  for term in terms:
    if term in title_l:
      hits += 2.0
    if term in body_l:
      hits += 1.0 + min(2.0, body_l.count(term) * 0.25)
  return hits / len(terms)


def _excerpt(terms: list[str], body: str, width: int = 360) -> str:
  text = " ".join(body.split())
  if len(text) <= width:
    return text
  lower = text.lower()
  positions = [lower.find(term) for term in terms if term in lower]
  start = max(0, min(positions) - 60) if positions else 0
  piece = text[start : start + width].strip()
  return ("..." if start else "") + piece + ("..." if start + width < len(text) else "")


def search_sources(
  query: str,
  *,
  knowledge=None,
  memory=None,
  conversations=None,
  limit: int = 8,
) -> list[Source]:
  """Rank what Ultron already holds against the question. Empty when nothing matches."""
  terms = keywords(query)
  found: list[Source] = []
  if not terms:
    return found

  if knowledge is not None:
    for item in knowledge.list_items():
      body = " ".join(part for part in (item.summary or "", item.body or "") if part)
      score = _score(terms, item.title, body + " " + " ".join(item.tags or []))
      if score > 0:
        found.append(Source("knowledge", item.id, item.title, _excerpt(terms, body or item.title), score + 0.5))

  if memory is not None:
    for entry in memory.list_memories():
      body = entry.body or entry.title
      score = _score(terms, entry.title or "", body)
      if score > 0:
        found.append(Source("memory", entry.id, (entry.title or body)[:80], _excerpt(terms, body), score))

  if conversations is not None:
    for conversation in conversations.list_conversations()[:30]:
      best: tuple[float, str] | None = None
      for message in conversations.get_messages(conversation.id)[-40:]:
        score = _score(terms, "", message.content)
        if score > 0 and (best is None or score > best[0]):
          best = (score, message.content)
      if best is not None:
        found.append(
          Source("conversation", conversation.id, conversation.title, _excerpt(terms, best[1]), best[0] * 0.8)
        )

  found.sort(key=lambda source: source.score, reverse=True)
  return found[:limit]
