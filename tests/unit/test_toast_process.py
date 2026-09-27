"""Toast helper process: protocol, callbacks, restart, and Qt isolation."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading

import pytest

from maira.core.interfaces.notifier import Notification, NotificationAction
from maira.infrastructure.notifications.toast_helper import run
from maira.infrastructure.notifications.toast_process import ToastProcessNotifier
from maira.shared.utils.paths import project_root

FAKE_HELPER = [sys.executable, "-m", "tests.fixtures.fake_toast_helper"]


def _notifier(events: list, **kwargs) -> ToastProcessNotifier:
  done = kwargs.pop("done", None)

  def record(item):
    events.append(item)
    if done is not None:
      done.set()

  return ToastProcessNotifier(
    lambda nid, action: record(("action", nid, action)),
    on_failed=lambda nid: record(("failed", nid)),
    command=FAKE_HELPER,
    supported=True,
    **kwargs,
  )


def test_helper_never_imports_qt() -> None:
  """pywinrt + Qt in one process crashes Windows (access violation)."""
  code = (
    "import sys, maira.infrastructure.notifications.toast_helper as h, "
    "maira.infrastructure.notifications.windows_toast; "
    "bad = [m for m in sys.modules if m.startswith(('PySide6', 'shiboken6'))]; "
    "print(bad); sys.exit(1 if bad else 0)"
  )
  result = subprocess.run([sys.executable, "-c", code], cwd=project_root(), capture_output=True, text=True)
  assert result.returncode == 0, result.stdout + result.stderr


def test_click_is_reported_back() -> None:
  events: list = []
  done = threading.Event()
  notifier = _notifier(events, done=done)
  try:
    assert notifier.is_available()
    assert notifier.show(Notification("n1", "click:snooze", "body", actions=(NotificationAction.SNOOZE,)))
    assert done.wait(10)
    assert events == [("action", "n1", "snooze")]
  finally:
    notifier.close()


def test_failure_is_reported_back() -> None:
  events: list = []
  done = threading.Event()
  notifier = _notifier(events, done=done)
  try:
    assert notifier.show(Notification("n2", "fail", "body"))
    assert done.wait(10)
    assert events == [("failed", "n2")]
  finally:
    notifier.close()


def test_helper_restarts_after_crash() -> None:
  events: list = []
  done = threading.Event()
  notifier = _notifier(events, done=done)
  try:
    assert notifier.show(Notification("n3", "crash", "body"))
    notifier._process.wait(timeout=10)  # noqa: SLF001
    assert notifier.show(Notification("n4", "click:done", "body"))
    assert done.wait(10)
    assert events == [("action", "n4", "done")]
  finally:
    notifier.close()


def test_unavailable_helper_reports_not_available(monkeypatch) -> None:
  monkeypatch.setenv("FAKE_TOAST_UNAVAILABLE", "1")
  notifier = _notifier([])
  try:
    assert not notifier.is_available()
    assert not notifier.show(Notification("n5", "click:done", "body"))
  finally:
    notifier.close()


def test_off_windows_is_unavailable_without_starting() -> None:
  notifier = ToastProcessNotifier(lambda *_: None, command=["does-not-exist"], supported=False)
  assert not notifier.is_available()
  assert notifier._process is None  # noqa: SLF001


@pytest.mark.skipif(os.name == "nt", reason="checks the non-Windows default")
def test_default_platform_check_is_false_off_windows() -> None:
  notifier = ToastProcessNotifier(lambda *_: None, command=["does-not-exist"])
  assert not notifier.is_available()


def test_run_protocol_in_process() -> None:
  from tests.fixtures.fake_toast_helper import FakeNotifier

  stdin = io.StringIO(
    "\n".join(
      [
        "not json",
        json.dumps({"type": "show", "id": "early", "title": "click:done"}),  # before init: ignored
        json.dumps({"type": "init", "app_id": "X", "app_name": "Ultron"}),
        json.dumps({"type": "show", "id": "a", "title": "click:done", "actions": ["done"]}),
      ]
    )
    + "\n"
  )
  stdout = io.StringIO()
  assert run(stdin, stdout, FakeNotifier) == 0
  lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
  assert lines == [{"type": "ready"}, {"type": "action", "id": "a", "action": "done"}]
