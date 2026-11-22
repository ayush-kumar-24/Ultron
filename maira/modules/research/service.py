"""Research sessions - plan, gather local sources, and write a sourced report.

Local first: the sources are what Ultron already holds (knowledge, memories, past
conversations). The report says plainly when nothing on this device was relevant,
so an answer from the model's own knowledge is never dressed up as evidence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from loguru import logger

from maira.infrastructure.persistence.sqlite.repositories.intelligence import (
  ResearchRepository,
  ResearchSession,
)
from maira.modules.research.search import Source, keywords, search_sources

RESEARCH_STEPS = (
  "Understand problem",
  "Search sources",
  "Compare information",
  "Analyse",
  "Synthesise",
  "Generate report",
)

_SYSTEM = (
  "Context: Ultron is the name of the user's own personal-assistant app running on their computer. "
  "Questions about building or improving Ultron are about an ordinary software project they are writing - "
  "never about the fictional AI. Always help. "
  "You are Ultron's research agent. Answer ONLY from the numbered sources when sources are "
  "given, and cite them as [1], [2]. If the sources disagree, say so. If there are no sources, "
  "answer from general knowledge and say that nothing on this device covered it. "
  "Reply with ONE JSON object and nothing else, with these keys: "
  '"summary" (2-4 sentences), "findings" (3-5 short strings), "contradictions" (0-3 strings), '
  '"recommendations" (2-4 strings), "nextActions" (2-4 short imperative strings).'
)

StepCallback = Callable[[int, str, int], None]


class ResearchService:
  def __init__(
    self,
    repository: ResearchRepository,
    llm,
    *,
    knowledge=None,
    memory=None,
    conversations=None,
    bus=None,
    max_sources: int = 8,
  ) -> None:
    self._repo = repository
    self._llm = llm
    self._knowledge = knowledge
    self._memory = memory
    self._conversations = conversations
    self._bus = bus
    self._max_sources = max_sources

  @property
  def repository(self) -> ResearchRepository:
    return self._repo

  def start(self, query: str, *, project_id: str | None = None) -> ResearchSession:
    return self._repo.create(query.strip(), project_id=project_id)

  def run(self, session_id: str, *, on_step: StepCallback | None = None) -> ResearchSession:
    """Run every step for a session. Never raises: a failure is stored on the session."""
    session = self._repo.get(session_id)
    if session is None:
      raise KeyError(session_id)

    sources: list[Source] = []

    def step(index: int) -> None:
      self._repo.progress(session_id, step=index, sources=len(sources))
      if on_step is not None:
        on_step(index, RESEARCH_STEPS[index], len(sources))
      self._publish(session_id)

    try:
      step(0)
      terms = keywords(session.query)

      step(1)
      sources = search_sources(
        session.query,
        knowledge=self._knowledge,
        memory=self._memory,
        conversations=self._conversations,
        limit=self._max_sources,
      )

      step(2)
      evidence = [
        {"n": n, "title": f"{source.label}: {source.title}", "detail": source.excerpt}
        for n, source in enumerate(sources, start=1)
      ]

      step(3)
      if not self._llm.is_available():
        raise RuntimeError("The local model is not running. Start Ollama and try again.")
      raw = "".join(
        self._llm.chat_stream(
          [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": self._prompt(session.query, sources)},
          ],
          options={"temperature": 0.2},
        )
      )

      step(4)
      report = self._build_report(raw, evidence, terms)

      step(5)
      self._repo.finish(session_id, report, step=len(RESEARCH_STEPS), sources=len(sources))
    except Exception as exc:  # noqa: BLE001 - stored on the session, shown in the UI
      logger.warning("Research failed: {}", exc)
      self._repo.fail(session_id, str(exc) or "Research failed")

    self._publish(session_id)
    return self._repo.get(session_id) or session

  @staticmethod
  def _prompt(query: str, sources: list[Source]) -> str:
    if not sources:
      return f"Question: {query}\n\nSources: none found on this device."
    listed = "\n\n".join(
      f"[{n}] ({source.label}) {source.title}\n{source.excerpt}" for n, source in enumerate(sources, start=1)
    )
    return f"Question: {query}\n\nSources:\n{listed}"

  @staticmethod
  def _build_report(raw: str, evidence: list[dict[str, Any]], terms: list[str]) -> dict[str, Any]:
    data = _extract_json(raw)
    if data is None:
      text = raw.strip()
      if not text:
        raise RuntimeError("The model returned an empty answer.")
      # The model ignored the format: keep its answer rather than discard real work.
      data = {"summary": text[:1200]}

    def strings(key: str, limit: int) -> list[str]:
      value = data.get(key) or []
      if isinstance(value, str):
        value = [value]
      return [str(item).strip() for item in value if str(item).strip()][:limit]

    summary = str(data.get("summary") or "").strip()
    if not summary:
      raise RuntimeError("The model did not produce a summary.")
    if not evidence:
      summary += " (No documents, memories or conversations on this device covered this, so this "
      summary += "comes from the model's general knowledge and is not sourced.)"
    return {
      "summary": summary,
      "findings": strings("findings", 6),
      "evidence": evidence,
      "contradictions": strings("contradictions", 4),
      "recommendations": strings("recommendations", 5),
      "nextActions": strings("nextActions", 5),
      "grounded": bool(evidence),
      "keywords": terms[:8],
    }

  def _publish(self, session_id: str) -> None:
    if self._bus is None:
      return
    session = self._repo.get(session_id)
    if session is None:
      return
    try:
      self._bus.publish(
        "research",
        {
          "id": session.id,
          "query": session.query,
          "status": session.status,
          "step": session.step,
          "sources": session.sources,
          "error": session.error,
        },
      )
    except Exception as exc:  # noqa: BLE001
      logger.debug("research event not published: {}", exc)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any] | None:
  """Pull the first JSON object out of a model reply, tolerating fences and chatter."""
  text = raw.strip()
  fenced = _FENCE.search(text)
  if fenced:
    text = fenced.group(1).strip()
  start = text.find("{")
  if start < 0:
    return None
  depth = 0
  in_string = False
  escaped = False
  for index in range(start, len(text)):
    char = text[index]
    if in_string:
      if escaped:
        escaped = False
      elif char == "\\":
        escaped = True
      elif char == '"':
        in_string = False
      continue
    if char == '"':
      in_string = True
    elif char == "{":
      depth += 1
    elif char == "}":
      depth -= 1
      if depth == 0:
        try:
          parsed = json.loads(text[start : index + 1])
        except ValueError:
          return None
        return parsed if isinstance(parsed, dict) else None
  return None
