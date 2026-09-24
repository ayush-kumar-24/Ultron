"""Helper process for tests: real protocol, fake notifier (no Windows APIs).

Title "click:<action>" answers with that action; title "fail" reports failure;
title "crash" kills the helper.
"""

from __future__ import annotations

import os
import sys

from maira.core.interfaces.notifier import Notification, Notifier
from maira.infrastructure.notifications.toast_helper import run


class FakeNotifier(Notifier):
  def __init__(self, *, on_action, on_failed, **_kwargs) -> None:
    self._on_action = on_action
    self._on_failed = on_failed

  def name(self) -> str:
    return "fake"

  def is_available(self) -> bool:
    return os.environ.get("FAKE_TOAST_UNAVAILABLE") != "1"

  def show(self, notification: Notification) -> bool:
    if notification.title == "crash":
      os._exit(3)
    if notification.title == "fail":
      self._on_failed(notification.id)
    elif notification.title.startswith("click:"):
      self._on_action(notification.id, notification.title.split(":", 1)[1])
    return True


if __name__ == "__main__":
  sys.exit(run(sys.stdin, sys.stdout, FakeNotifier))
