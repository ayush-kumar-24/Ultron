"""Multi-agent run: Core -> Research -> Knowledge -> Planning -> Core (verify).

Each stage is real work by the service that owns it, tracked through the registry so the
Agents page shows it live. `verified` is only true when the checks at the end pass.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maira.modules.orchestration.registry import AgentRegistry
from maira.modules.research.search import Source, keywords, search_sources
from maira.modules.research.service import _extract_json

import re

_LEADING_NUMBER = re.compile(r"^\s*(?:step\s*)?\d+\s*[.):-]\s*", re.IGNORECASE)

StepCallback = Callable[[int, str, str, str], None]  # index, agent id, label, status

_SYSTEM = (
  "Context: Ultron is the name of the user's own personal-assistant app running on their computer. "
  "Questions about building or improving Ultron are about an ordinary software project they are writing - "
  "never about the fictional AI. Always help. "
  "You are Ultron's planning agent. Turn the request into a short, concrete plan the user can "
  "act on today. Use the numbered context when it is relevant and cite it as [1], [2]. "
  "Reply with ONE JSON object and nothing else: "
  '{"summary": "2-3 sentences", "plan": ["step", "step", ...]} with 3 to 7 steps, each one '
  "imperative and specific."
)


class Orchestrator:
  def __init__(
    self,
    registry: AgentRegistry,
    llm,
    *,
    knowledge=None,
    memory=None,
    conversations=None,
  ) -> None:
    self._registry = registry
    self._llm = llm
    self._knowledge = knowledge
    self._memory = memory
    self._conversations = conversations

  def run(self, request: str, *, on_step: StepCallback | None = None) -> dict[str, Any]:
    request = request.strip()

    def stage(index: int, agent: str, label: str, work: Callable[[], Any]) -> Any:
      if on_step is not None:
        on_step(index, agent, label, "running")
      with self._registry.track(agent, f"{label}: {request[:80]}"):
        result = work()
      if on_step is not None:
        on_step(index, agent, label, "done")
      return result

    terms = stage(0, "core", "Understand goal", lambda: keywords(request))

    recalled: list[Source] = stage(
      1,
      "research",
      "Search memory and conversations",
      lambda: search_sources(request, memory=self._memory, conversations=self._conversations, limit=5),
    )
    documents: list[Source] = stage(
      2,
      "knowledge",
      "Read the knowledge library",
      lambda: search_sources(request, knowledge=self._knowledge, limit=5),
    )
    sources = documents + recalled

    def draft() -> dict[str, Any]:
      if not self._llm.is_available():
        raise RuntimeError("The local model is not running. Start Ollama and try again.")
      context = "\n\n".join(
        f"[{n}] ({source.label}) {source.title}\n{source.excerpt}" for n, source in enumerate(sources, start=1)
      )
      if not context:
        context = "nothing relevant on this device"
      raw = "".join(
        self._llm.chat_stream(
          [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Request: {request}\n\nContext:\n{context}"},
          ],
          options={"temperature": 0.3},
        )
      )
      data = _extract_json(raw) or {}
      plan = data.get("plan") or []
      if isinstance(plan, str):
        plan = [line.strip(" -*0123456789.") for line in plan.splitlines()]
      return {
        "summary": str(data.get("summary") or raw.strip()[:600]).strip(),
        # The UI numbers the steps itself, so drop the model's own "1." / "2)" prefixes.
        "plan": [_LEADING_NUMBER.sub("", str(item)).strip() for item in plan if str(item).strip()][:8],
      }

    drafted = stage(3, "planning", "Draft the plan", draft)

    def verify() -> tuple[bool, list[str]]:
      checks: list[str] = []
      plan = drafted["plan"]
      if not drafted["summary"]:
        checks.append("No summary was produced")
      if len(plan) < 2:
        checks.append("The plan has fewer than two steps")
      if len({step.lower() for step in plan}) != len(plan):
        checks.append("The plan repeats a step")
      if terms and not any(term in (drafted["summary"] + " ".join(plan)).lower() for term in terms):
        checks.append("The plan does not mention anything from the request")
      return (not checks, checks)

    verified, problems = stage(4, "core", "Verify and report", verify)

    return {
      "summary": drafted["summary"],
      "plan": drafted["plan"],
      "verified": verified,
      "checks": problems,
      "sources": [{"n": n, "title": f"{s.label}: {s.title}"} for n, s in enumerate(sources, start=1)],
      "grounded": bool(sources),
    }
