"""Execute due automation jobs (notify / open / agent / desktop)."""

from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from maira.core.domain.entities import AutomationJob
from maira.core.domain.value_objects import AutomationActionType
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.desktop import DesktopController, DesktopStep


@dataclass(frozen=True)
class ExecutionResult:
  ok: bool
  message: str


class AutomationExecutor:
  def __init__(
    self,
    automation: Automation,
    *,
    brain: Brain | None = None,
    desktop: DesktopController | None = None,
    on_notify: Callable[[str], None] | None = None,
  ) -> None:
    self._automation = automation
    self._brain = brain
    self._desktop = desktop
    self._on_notify = on_notify

  def run(self, job: AutomationJob) -> ExecutionResult:
    try:
      payload = json.loads(job.action_payload or "{}")
    except json.JSONDecodeError:
      payload = {}

    try:
      if job.action_type == AutomationActionType.NOTIFY:
        result = self._notify(job, payload)
      elif job.action_type == AutomationActionType.OPEN_URL:
        result = self._open_url(payload)
      elif job.action_type == AutomationActionType.OPEN_APP:
        result = self._open_app(payload)
      elif job.action_type == AutomationActionType.DESKTOP:
        result = self._run_desktop(payload)
      else:
        result = self._run_agent(job, payload)
    except Exception as exc:  # noqa: BLE001
      logger.exception("Automation failed: {}", job.id)
      result = ExecutionResult(False, str(exc))

    next_run = None
    if result.ok:
      next_run = (
        self._automation.next_run_after(job)
        if hasattr(self._automation, "next_run_after")
        else None
      )

    self._automation.mark_ran(
      job.id,
      ok=result.ok,
      error=None if result.ok else result.message,
      next_run_at=next_run if result.ok else None,
    )
    return result

  def _notify(self, job: AutomationJob, payload: dict[str, Any]) -> ExecutionResult:
    message = str(payload.get("message") or job.instruction or job.title)
    if self._on_notify:
      self._on_notify(f"Automation: {message}")
    return ExecutionResult(True, message)

  def _open_url(self, payload: dict[str, Any]) -> ExecutionResult:
    if self._desktop is not None:
      result = self._desktop.open_url(str(payload.get("url") or ""))
      return ExecutionResult(result.ok, result.message)
    url = str(payload.get("url") or "").strip()
    if not url:
      return ExecutionResult(False, "Missing URL")
    webbrowser.open(url)
    return ExecutionResult(True, f"Opened {url}")

  def _open_app(self, payload: dict[str, Any]) -> ExecutionResult:
    if self._desktop is not None:
      result = self._desktop.open_app(str(payload.get("app") or payload.get("path") or ""))
      return ExecutionResult(result.ok, result.message)
    app = str(payload.get("app") or payload.get("path") or "").strip()
    if not app:
      return ExecutionResult(False, "Missing app")
    if os.name == "nt":
      os.startfile(app)  # type: ignore[attr-defined]
    else:
      subprocess.Popen([app], shell=False)  # noqa: S603
    return ExecutionResult(True, f"Launched {app}")

  def _run_desktop(self, payload: dict[str, Any]) -> ExecutionResult:
    if self._desktop is None:
      return ExecutionResult(False, "Desktop controller unavailable")
    raw_steps = payload.get("steps") or []
    steps: list[DesktopStep] = []
    for item in raw_steps:
      if isinstance(item, dict):
        steps.append(
          DesktopStep(str(item.get("kind") or ""), dict(item.get("args") or {}))
        )
    result = self._desktop.run_steps(steps)
    if self._on_notify:
      self._on_notify(result.message)
    return ExecutionResult(result.ok, result.message)

  def _run_agent(self, job: AutomationJob, payload: dict[str, Any]) -> ExecutionResult:
    instruction = str(payload.get("instruction") or job.instruction).strip()
    if not instruction:
      return ExecutionResult(False, "Missing instruction")
    if self._brain is None:
      if self._on_notify:
        self._on_notify(f"Due now: {instruction}")
      return ExecutionResult(True, f"Queued agent task: {instruction}")
    prompt = (
      f"[Automation:{job.title}] Do this now and keep the reply concise:\n{instruction}"
    )

    def _send() -> None:
      try:
        self._brain.send_message(prompt)
      except Exception:  # noqa: BLE001
        logger.exception("Automation agent send failed for {}", job.id)

    import threading

    threading.Thread(target=_send, name=f"maira-auto-{job.id[:8]}", daemon=True).start()
    if self._on_notify:
      self._on_notify(f"Running automation: {job.title}")
    return ExecutionResult(True, f"Agent ran: {job.title}")
