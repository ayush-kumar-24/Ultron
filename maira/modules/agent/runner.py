"""The agent loop: the model picks tools toward a goal; risky steps wait for the user's OK."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from maira.modules.agent.tools import Tool, ToolError

# A chat_tools-like function: (messages, tool_schemas) -> {"content", "tool_calls"}.
ModelCall = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]
Progress = Callable[[str], None]

SYSTEM_PROMPT = """You are Ultron's action agent on the user's Windows PC. Reach the user's goal by calling tools.
Rules:
- Only the user's allowed folders can be used: {folders}.
- Never guess file paths. Use find_files or list_folder first, then use the exact path they return.
- Read a file before summarizing, editing or sending it if you need its content.
- Steps that change or send something (writing, moving, deleting, email, WhatsApp, saving contacts) are shown to the user for approval automatically. Just call the tool; do not ask for permission in text.
- If you are missing something only the user knows (an email address, which file they meant), stop and ask in one short question.
- When the goal is done, reply with a short summary of what you did. Do not call more tools after that.
Today is {today}. The user's name is {name}."""


@dataclass
class Outcome:
  kind: str  # "done" | "approval" | "error"
  text: str


@dataclass
class _Pending:
  tool: Tool
  arguments: dict[str, Any]
  queue: list[dict[str, Any]] = field(default_factory=list)  # later calls from the same reply


class AgentRunner:
  def __init__(
    self,
    model_call: ModelCall,
    tools: list[Tool],
    *,
    folders: str,
    user_name: str = "",
    max_steps: int = 10,
    progress: Progress | None = None,
  ) -> None:
    self._call = model_call
    self._tools = {t.name: t for t in tools}
    self._schemas = [t.schema() for t in tools]
    self._max_steps = max_steps
    self._progress = progress or (lambda _text: None)
    self._messages: list[dict[str, Any]] = [{
      "role": "system",
      "content": SYSTEM_PROMPT.format(
        folders=folders, today=datetime.now().strftime("%A %d %B %Y"), name=user_name or "the user"
      ),
    }]
    self._steps = 0
    self._seen: dict[str, int] = {}
    self.pending: _Pending | None = None
    self.log: list[str] = []  # one line per action taken, for the final summary

  # --- public ------------------------------------------------------------------------------

  def start(self, goal: str, history: list[dict[str, str]] | None = None) -> Outcome:
    self._messages += list(history or [])
    self._messages.append({"role": "user", "content": goal})
    return self._loop()

  def approve(self) -> Outcome:
    pending = self._take_pending()
    self._execute(pending.tool, pending.arguments)
    return self._continue(pending.queue) or self._loop()

  def decline(self) -> Outcome:
    pending = self._take_pending()
    self._tool_result(pending.tool.name, "The user said no. Do not do this; ask what they want instead, or finish.")
    self.log.append(f"Skipped: {pending.tool.name} (you said no)")
    for call in pending.queue:
      self._tool_result(call["name"], "Skipped because the user declined the step before it.")
    return self._loop()

  # --- loop ----------------------------------------------------------------------------------

  def _take_pending(self) -> _Pending:
    if self.pending is None:
      raise RuntimeError("Nothing is waiting for approval")
    pending, self.pending = self.pending, None
    return pending

  def _loop(self) -> Outcome:
    while self._steps < self._max_steps:
      self._steps += 1
      try:
        reply = self._call(self._messages, self._schemas)
      except Exception as exc:  # noqa: BLE001 — the model may be missing or offline
        logger.warning("Agent model call failed: {}", exc)
        return Outcome("error", str(exc) or "The AI model did not answer.")
      calls = reply.get("tool_calls") or []
      content = str(reply.get("content") or "").strip()
      self._messages.append({
        "role": "assistant",
        "content": content,
        **({"tool_calls": [{"function": c} for c in calls]} if calls else {}),
      })
      if not calls:
        return Outcome("done", content or "Done.")
      outcome = self._continue(calls)
      if outcome is not None:
        return outcome
    return Outcome("done", self._summary("I stopped after the step limit; say \"continue\" to keep going."))

  def _continue(self, calls: list[dict[str, Any]]) -> Outcome | None:
    """Run tool calls in order; stop at the first one that needs approval (None = keep going)."""
    for index, call in enumerate(calls):
      name, arguments = call.get("name", ""), call.get("arguments") or {}
      tool = self._tools.get(name)
      if tool is None:
        self._tool_result(name, f"There is no tool called {name}. Available: {', '.join(self._tools)}.")
        continue
      key = name + json.dumps(arguments, sort_keys=True, default=str)
      self._seen[key] = self._seen.get(key, 0) + 1
      if self._seen[key] > 2:
        return Outcome("done", self._summary("I was repeating the same step, so I stopped."))
      if tool.confirm is not None:
        try:
          if tool.check is not None:
            tool.check(arguments)
          question = tool.confirm(arguments)
        except ToolError as exc:
          self._tool_result(name, f"Error: {exc}")
          continue
        self.pending = _Pending(tool, arguments, calls[index + 1:])
        return Outcome("approval", question)
      self._execute(tool, arguments)
    return None

  def _execute(self, tool: Tool, arguments: dict[str, Any]) -> None:
    self._progress(_progress_line(tool.name, arguments))
    try:
      result = tool.run(arguments)
      if tool.confirm is not None:
        self.log.append(result.splitlines()[0] if result else tool.name)
    except ToolError as exc:
      result = f"Error: {exc}"
    except Exception as exc:  # noqa: BLE001
      logger.exception("Agent tool {} crashed", tool.name)
      result = f"Error: {exc}"
    self._tool_result(tool.name, result)

  def _tool_result(self, name: str, result: str) -> None:
    self._messages.append({"role": "tool", "tool_name": name, "content": result[:12_000]})

  def _summary(self, reason: str) -> str:
    done = "\n".join(f"• {line}" for line in self.log) or "• Nothing was changed."
    return f"{reason}\n{done}"


def _progress_line(name: str, args: dict[str, Any]) -> str:
  hint = next((str(args[k]) for k in ("path", "query", "source", "target", "to", "name") if args.get(k)), "")
  labels = {
    "list_folder": "Looking in", "find_files": "Searching for", "read_file": "Reading",
    "write_file": "Saving", "edit_file": "Editing", "move_file": "Moving", "delete_file": "Deleting",
    "make_folder": "Creating folder", "open": "Opening", "play_music": "Playing",
    "find_contact": "Looking up", "save_contact": "Saving contact", "send_email": "Emailing",
    "send_whatsapp": "WhatsApp to",
  }
  return f"• {labels.get(name, name)} {hint}".rstrip() + "\n"
