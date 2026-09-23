"""Show Windows toasts through the Qt-free helper process (see toast_helper)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from maira.core.interfaces.notifier import Notification, Notifier
from maira.infrastructure.notifications.windows_toast import APP_ID
from maira.shared.utils.paths import project_root

HELPER_MODULE = "maira.infrastructure.notifications.toast_helper"
_READY_TIMEOUT_S = 15.0
_MAX_RESTARTS = 3


def default_helper_command() -> list[str]:
  return [sys.executable, "-m", HELPER_MODULE]


class ToastProcessNotifier(Notifier):
  """``on_action`` / ``on_failed`` are called from a reader thread; marshal to Qt."""

  def __init__(
    self,
    on_action: Callable[[str, str], None],
    *,
    on_failed: Callable[[str], None] | None = None,
    app_name: str = "Ultron",
    app_id: str = APP_ID,
    icon_path: Path | None = None,
    image_path: Path | None = None,
    command: list[str] | None = None,
    supported: bool | None = None,
  ) -> None:
    self._on_action = on_action
    self._on_failed = on_failed
    self._init = {
      "type": "init",
      "app_id": app_id,
      "app_name": app_name,
      "icon": str(icon_path) if icon_path else None,
      "image": str(image_path) if image_path else None,
    }
    self._command = command or default_helper_command()
    self._supported = supported
    self._process: subprocess.Popen | None = None
    self._ready = threading.Event()
    self._error: str | None = None
    self._write_lock = threading.Lock()
    self._restarts = 0
    self._available: bool | None = None

  def name(self) -> str:
    return "windows-toast"

  def is_available(self) -> bool:
    if self._available is None:
      self._available = self._platform_ok() and self._start()
    return self._available

  def _platform_ok(self) -> bool:
    if self._supported is not None:
      return self._supported
    if os.name != "nt":
      return False
    # find_spec does not import it: loading pywinrt next to Qt crashes.
    if importlib.util.find_spec("windows_toasts") is None:
      logger.warning("windows-toasts not installed; using tray notifications")
      return False
    return True

  def _start(self) -> bool:
    self._ready.clear()
    self._error = None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
      self._process = subprocess.Popen(  # noqa: S603
        self._command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=str(project_root()),
        creationflags=flags,
      )
    except OSError:
      logger.exception("Could not start the notification helper")
      return False
    threading.Thread(
      target=self._read_loop, args=(self._process,), name="ultron-toast-reader", daemon=True
    ).start()
    if not self._write(self._init):
      return False
    if not self._ready.wait(_READY_TIMEOUT_S) or self._error:
      logger.error("Notification helper not ready: {}", self._error or "timeout")
      self.close()
      return False
    logger.info("Windows notifications ready (helper process {})", self._process.pid)
    return True

  def _read_loop(self, process: subprocess.Popen) -> None:
    assert process.stdout is not None
    for line in process.stdout:
      try:
        message = json.loads(line)
      except json.JSONDecodeError:
        continue
      kind = message.get("type")
      try:
        if kind == "ready":
          self._ready.set()
        elif kind == "error":
          self._error = str(message.get("message"))
          self._ready.set()
        elif kind == "action":
          self._on_action(str(message.get("id")), str(message.get("action")))
        elif kind == "failed" and self._on_failed is not None:
          self._on_failed(str(message.get("id")))
      except Exception:  # noqa: BLE001
        logger.exception("Notification helper message failed: {}", kind)
    if process is self._process:
      logger.warning("Notification helper stopped unexpectedly; it restarts on the next reminder")

  def _write(self, message: dict) -> bool:
    process = self._process
    if process is None or process.stdin is None:
      return False
    try:
      with self._write_lock:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
      return True
    except (OSError, ValueError):
      return False

  def _alive(self) -> bool:
    return self._process is not None and self._process.poll() is None

  def show(self, notification: Notification) -> bool:
    if not self.is_available():
      return False
    if not self._alive():
      if self._restarts >= _MAX_RESTARTS:
        return False
      self._restarts += 1
      logger.warning("Restarting notification helper ({}/{})", self._restarts, _MAX_RESTARTS)
      if not self._start():
        return False
    return self._write(
      {
        "type": "show",
        "id": notification.id,
        "title": notification.title,
        "body": notification.body,
        "actions": [action.value for action in notification.actions],
      }
    )

  def close(self) -> None:
    process = self._process
    self._process = None
    if process is None:
      return
    try:
      if process.stdin is not None:
        process.stdin.close()
      process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
      process.kill()
