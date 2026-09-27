"""Check Windows notifications the way Ultron sends them.

Run from the project folder:
  python -X faulthandler -m scripts.test_notification; echo "exit code: $LASTEXITCODE"

Qt runs in this process and toasts run in a separate helper process, exactly
like the app (pywinrt and Qt crash when loaded together).
"""

from __future__ import annotations

import faulthandler
import os
import sys
import time

faulthandler.enable()  # print a trace even if native code crashes the process


def step(text: str) -> None:
  print(text, flush=True)


def _read_dword(path: str, name: str) -> int | None:
  import winreg  # noqa: PLC0415

  try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
      value, _ = winreg.QueryValueEx(key, name)
      return int(value)
  except OSError:
    return None


def main() -> int:
  if os.name != "nt":
    step("This check only runs on Windows.")
    return 1

  from maira.infrastructure.notifications.windows_toast import APP_ID  # noqa: PLC0415

  step(f"Python {sys.version.split()[0]} on {sys.platform}")
  step("1. Windows notification settings")
  toasts = _read_dword(r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled")
  app = _read_dword(rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{APP_ID}", "Enabled")
  step(f"   All notifications: {'OFF' if toasts == 0 else 'on'}")
  step(f"   Ultron notifications: {'OFF' if app == 0 else 'on / not set yet'}")

  step("2. Starting Qt (like the app does)...")
  from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

  _app = QGuiApplication(sys.argv)
  from maira.shared.utils.paths import data_dir  # noqa: PLC0415
  from maira.ui.system_tray import export_icon_files  # noqa: PLC0415

  icons = export_icon_files(data_dir() / "assets")

  step("3. Starting notification helper process...")
  from maira.core.interfaces.notifier import Notification, NotificationAction  # noqa: PLC0415
  from maira.infrastructure.notifications.toast_process import ToastProcessNotifier  # noqa: PLC0415

  events: list[str] = []
  notifier = ToastProcessNotifier(
    lambda nid, action: events.append(f"clicked {action}"),
    icon_path=icons.ico if icons else None,
    image_path=icons.png if icons else None,
    on_failed=lambda nid: events.append("FAILED"),
  )
  if not notifier.is_available():
    step("   Helper did not start  <-- send data/logs/toast_helper.log and maira.log")
    return 1
  step("   ready")

  step("4. Sending notification...")
  notifier.show(
    Notification(
      "test",
      "Ultron test",
      "Click Done or Snooze.",
      actions=(NotificationAction.DONE, NotificationAction.SNOOZE),
    )
  )
  step("   Sent. Waiting 20s - click a button on the pop-up...")
  for _ in range(40):
    if events:
      break
    time.sleep(0.5)
  step(f"   Result: {events[0] if events else 'no click'}")
  notifier.close()
  step("Finished - send this output to Claude.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
