"""When a message is a job for the agent, and the yes/no flow around its risky steps."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from loguru import logger

from maira.modules.agent.runner import AgentRunner, Outcome
from maira.modules.agent.tools import Tool

_YES = re.compile(r"^(?:yes|y|yeah|yep|ok|okay|sure|go|go ahead|do it|send|send it|haan|han|ha|haa|haanji|ji|theek hai|thik hai|kar do|karo|bhej do|bhejo)[.! ]*$", re.IGNORECASE)
_NO = re.compile(r"^(?:no|n|nope|cancel|stop|don'?t|nahi|nahin|na|mat|mat karo|rehne do|skip|mat bhejo)[.! ]*$", re.IGNORECASE)
_EXPLICIT = re.compile(r"^(?:/?agent|/?do)\s*[:,-]?\s+(?P<goal>.+)$", re.IGNORECASE | re.DOTALL)
_ACTION = re.compile(
  r"\b(send|email|e-mail|mail|whatsapp|forward|share|attach|rename|move|copy|delete|remove|organi[sz]e|"
  r"sort|clean\s+up|create|make|write|save|find|search|look\s+for|locate|open|list|show|read|summari[sz]e|"
  r"edit|replace|bhej|bhejo|dhundh|dhoondh|khol|dikhao)\b",
  re.IGNORECASE,
)
_OBJECT = re.compile(
  r"\b(files?|folders?|pdfs?|docx?|documents?|downloads|desktop|photos?|images?|pictures?|screenshots?|"
  r"resume|cv|invoices?|spreadsheets?|csv|excel|txt|contacts?|whatsapp|e-?mail|gmail|attachment)\b"
  r"|[a-z]:[\\/]|\b[\w-]+\.(?:pdf|docx?|xlsx?|csv|txt|md|png|jpe?g|pptx?|zip)\b",
  re.IGNORECASE,
)
_QUESTION = re.compile(r"^(?:how\s+(?:do|can|to|does)|why|explain|what\s+is|what's\s+the\s+difference|can\s+you\s+explain)\b", re.IGNORECASE)


def wants_agent(text: str) -> str | None:
  """The goal, when the message is a job to do on this PC; None for normal chat."""
  explicit = _EXPLICIT.match(text.strip())
  if explicit:
    return explicit.group("goal").strip()
  if _QUESTION.match(text.strip()):
    return None
  if _ACTION.search(text) and _OBJECT.search(text):
    return text.strip()
  return None


class AgentService:
  def __init__(
    self,
    model_call: Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]],
    tools: Callable[[], list[Tool]],
    *,
    folders: Callable[[], str],
    model: str,
    enabled: bool = True,
    auto_detect: bool = True,
    max_steps: int = 10,
    user_name: Callable[[], str] = lambda: "",
  ) -> None:
    self._model_call = model_call
    self._tools = tools
    self._folders = folders
    self.model = model
    self.enabled = enabled
    self.auto_detect = auto_detect
    self.max_steps = max_steps
    self._user_name = user_name
    self._runner: AgentRunner | None = None

  @property
  def waiting(self) -> bool:
    return self._runner is not None and self._runner.pending is not None

  def goal_for(self, text: str) -> str | None:
    if not self.enabled:
      return None
    explicit = _EXPLICIT.match(text.strip())
    if explicit:
      return explicit.group("goal").strip()
    return wants_agent(text) if self.auto_detect else None

  def start(self, goal: str, *, history: list[dict[str, str]] | None = None,
            progress: Callable[[str], None] | None = None) -> Outcome:
    runner = AgentRunner(
      lambda messages, schemas: self._model_call(self.model, messages, schemas),
      self._tools(),
      folders=self._folders(),
      user_name=self._user_name(),
      max_steps=self.max_steps,
      progress=progress,
    )
    self._runner = runner
    logger.info("Agent goal: {}", goal[:120])
    return self._finish(runner.start(goal, history))

  def answer(self, text: str, *, progress: Callable[[str], None] | None = None) -> Outcome | None:
    """A reply while a step waits for approval. None = not a yes/no; the task is dropped."""
    if not self.waiting:
      return None
    runner = self._runner
    assert runner is not None
    runner._progress = progress or runner._progress  # noqa: SLF001
    if _YES.match(text.strip()):
      return self._finish(runner.approve())
    if _NO.match(text.strip()):
      return self._finish(runner.decline())
    self._runner = None
    return None

  def _finish(self, outcome: Outcome) -> Outcome:
    if outcome.kind != "approval":
      self._runner = None
    return outcome


def approval_prompt(question: str) -> str:
  return f"I'd like to:\n{question}\n\nSay **yes** to do it, or **no** to skip."
