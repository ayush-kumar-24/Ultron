"""Tray, close-to-tray, single instance, and cross-thread notification actions."""

from __future__ import annotations

import threading
import uuid

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent

from maira.app.single_instance import SingleInstanceGuard, default_server_name
from maira.ui.system_tray import (
  NotificationActionRelay,
  app_icon,
  export_icon_files,
  render_logo_pixmap,
)


def _unique_name() -> str:
  return f"ultron-test-{uuid.uuid4().hex[:12]}"


def _second_instance(qtbot, name: str, build_id: str) -> str:
  """Start a second instance in another process while this one serves requests."""
  import subprocess
  import sys

  from maira.shared.utils.paths import project_root

  proc = subprocess.Popen(
    [sys.executable, "-m", "tests.fixtures.second_instance", name, build_id],
    cwd=project_root(),
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
  )
  qtbot.waitUntil(lambda: proc.poll() is not None, timeout=20000)
  return proc.stdout.read().strip()


def test_same_build_is_refused_and_shows_first(qtbot) -> None:
  name = _unique_name()
  first = SingleInstanceGuard(name, build_id="build-a")
  shown: list = []
  first.activation_requested.connect(lambda: shown.append(True))
  try:
    assert first.try_acquire()
    assert _second_instance(qtbot, name, "build-a") == "REFUSED"
    assert shown == [True]
  finally:
    first.release()


def test_newer_build_replaces_running_instance(qtbot) -> None:
  name = _unique_name()
  first = SingleInstanceGuard(name, build_id="old-build")
  replaced: list = []

  def quit_like_the_app() -> None:
    replaced.append(True)
    first.release()  # the app quits, which releases the guard

  first.replace_requested.connect(quit_like_the_app)
  assert first.try_acquire()
  assert _second_instance(qtbot, name, "new-build") == "ACQUIRED"
  assert replaced == [True]


def test_build_id_changes_with_code(tmp_path) -> None:
  import os

  from maira.app.single_instance import compute_build_id

  (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
  before = compute_build_id(tmp_path)
  assert compute_build_id(tmp_path) == before
  target = tmp_path / "a.py"
  target.write_text("x = 22\n", encoding="utf-8")
  os.utime(target, ns=(1, 1))
  assert compute_build_id(tmp_path) != before


def test_instance_can_start_after_previous_released(qtbot) -> None:
  name = _unique_name()
  first = SingleInstanceGuard(name, build_id="b")
  assert first.try_acquire()
  first.release()
  again = SingleInstanceGuard(name, build_id="b")
  try:
    assert again.try_acquire()
  finally:
    again.release()


def test_default_server_name_is_safe() -> None:
  name = default_server_name("Ultron App")
  assert name.startswith("ultron_app-")
  assert all(ch.isalnum() or ch in "_-" for ch in name)


def test_relay_runs_handler_on_main_thread(qtbot) -> None:
  main_thread = QThread.currentThread()
  seen: list = []
  relay = NotificationActionRelay(
    lambda nid, action: seen.append((nid, action, QThread.currentThread() is main_thread))
  )

  worker = threading.Thread(target=relay.post, args=("n1", "snooze"))
  worker.start()
  worker.join()
  qtbot.waitUntil(lambda: bool(seen), timeout=3000)

  assert seen == [("n1", "snooze", True)]


def test_relay_survives_handler_error(qtbot) -> None:
  calls: list = []

  def handler(nid: str, action: str) -> None:
    calls.append(nid)
    raise RuntimeError("boom")

  relay = NotificationActionRelay(handler)
  relay.post("a", "done")
  relay.post("b", "done")
  qtbot.waitUntil(lambda: len(calls) == 2, timeout=3000)


def test_logo_renders_and_exports(qtbot, tmp_path) -> None:
  assert not render_logo_pixmap(32).isNull()
  assert not app_icon().isNull()
  icons = export_icon_files(tmp_path / "assets")
  assert icons is not None
  assert icons.ico.suffix == ".ico" and icons.ico.stat().st_size > 0
  # Toast images must be PNG; Windows drops toasts with unsupported images.
  assert icons.png.suffix == ".png" and icons.png.stat().st_size > 0



def test_prototype_window_hides_to_tray_instead_of_closing(qtbot) -> None:
  from maira.ui.prototype.shell.main_window import PrototypeWindow

  window = PrototypeWindow(skip_onboarding=True)
  qtbot.addWidget(window)
  window.show()
  hides: list = []
  window.set_close_handler(lambda: hides.append(True) or True)

  event = QCloseEvent()
  window.closeEvent(event)

  assert hides == [True]
  assert not event.isAccepted()
  assert not window.isVisible()

  window.bring_to_front()
  assert window.isVisible()


def test_prototype_window_closes_without_handler(qtbot) -> None:
  from maira.ui.prototype.shell.main_window import PrototypeWindow

  window = PrototypeWindow(skip_onboarding=True)
  qtbot.addWidget(window)
  window.set_close_handler(lambda: False)
  event = QCloseEvent()
  window.closeEvent(event)
  assert event.isAccepted()


def test_old_running_version_without_replies_is_left_alone(qtbot) -> None:
  """Builds before auto-replace never answer; the new launch must not hang or double-run."""
  from PySide6.QtNetwork import QLocalServer

  name = _unique_name()
  QLocalServer.removeServer(name)
  old = QLocalServer()
  assert old.listen(name)
  keep: list = []
  old.newConnection.connect(lambda: keep.append(old.nextPendingConnection()))
  try:
    assert _second_instance(qtbot, name, "new-build") == "REFUSED"
  finally:
    old.close()
