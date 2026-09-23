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


def test_second_instance_is_refused_and_activates_first(qtbot) -> None:
  name = _unique_name()
  first = SingleInstanceGuard(name)
  second = SingleInstanceGuard(name)
  try:
    assert first.try_acquire()
    with qtbot.waitSignal(first.activation_requested, timeout=3000):
      assert not second.try_acquire()
  finally:
    first.release()
    second.release()


def test_instance_can_start_after_previous_released(qtbot) -> None:
  name = _unique_name()
  first = SingleInstanceGuard(name)
  assert first.try_acquire()
  first.release()
  again = SingleInstanceGuard(name)
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
