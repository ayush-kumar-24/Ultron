"""Windows toast helper process.

The Windows notification library (pywinrt) and Qt crash with an access
violation when loaded in one process, so toasts are shown from this separate,
Qt-free process. Protocol: one JSON object per line.

stdin  <- {"type": "init", "app_id", "app_name", "icon"}
          {"type": "show", "id", "title", "body", "actions": [...], "image"}
stdout -> {"type": "ready"} | {"type": "error", "message"}
          {"type": "action", "id", "action"} | {"type": "failed", "id"}

Never import PySide6 (directly or indirectly) here.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from maira.core.interfaces.notifier import Notification, NotificationAction, Notifier

NotifierFactory = Callable[..., Notifier]


def _default_factory(**kwargs: Any) -> Notifier:
  from maira.infrastructure.notifications.windows_toast import WindowsToastNotifier  # noqa: PLC0415

  return WindowsToastNotifier(**kwargs)


def _setup_logging() -> None:
  from loguru import logger  # noqa: PLC0415

  from maira.shared.utils.paths import logs_dir  # noqa: PLC0415

  logger.remove()
  logger.add(logs_dir() / "toast_helper.log", level="INFO", rotation="2 MB", retention=3, encoding="utf-8")


def run(stdin: IO[str], stdout: IO[str], factory: NotifierFactory = _default_factory) -> int:
  lock = threading.Lock()

  def send(message: dict[str, Any]) -> None:
    with lock:
      stdout.write(json.dumps(message) + "\n")
      stdout.flush()

  notifier: Notifier | None = None
  for line in stdin:
    line = line.strip()
    if not line:
      continue
    try:
      message = json.loads(line)
    except json.JSONDecodeError:
      continue
    kind = message.get("type")

    if kind == "init":
      icon = message.get("icon")
      notifier = factory(
        on_action=lambda nid, action: send({"type": "action", "id": nid, "action": action}),
        on_failed=lambda nid: send({"type": "failed", "id": nid}),
        app_name=str(message.get("app_name") or "Ultron"),
        app_id=str(message.get("app_id")),
        icon_path=Path(icon) if icon else None,
        image_path=Path(message["image"]) if message.get("image") else None,
      )
      if notifier.is_available():
        send({"type": "ready"})
      else:
        send({"type": "error", "message": "Windows notifications unavailable"})
        notifier = None

    elif kind == "show" and notifier is not None:
      notification = Notification(
        id=str(message.get("id")),
        title=str(message.get("title") or "Ultron"),
        body=str(message.get("body") or ""),
        actions=tuple(NotificationAction(a) for a in message.get("actions", [])),
      )
      try:
        if not notifier.show(notification):
          send({"type": "failed", "id": notification.id})
      except Exception:  # noqa: BLE001
        from loguru import logger  # noqa: PLC0415

        logger.exception("Toast show failed")
        send({"type": "failed", "id": notification.id})

  # stdin closed: Ultron quit.
  return 0


def main() -> int:
  _setup_logging()
  return run(sys.stdin, sys.stdout)


if __name__ == "__main__":
  sys.exit(main())
