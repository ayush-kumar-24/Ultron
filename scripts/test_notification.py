"""Check Windows notifications one small step at a time.

Run from the project folder:
  python -X faulthandler -m scripts.test_notification; echo "exit code: $LASTEXITCODE"
"""

from __future__ import annotations

import faulthandler
import os
import sys
import time

faulthandler.enable()  # print a trace even if Windows code crashes the process


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


def _wait(events: list[str], seconds: int = 15) -> str:
  for _ in range(seconds * 2):
    if events:
      return events[0]
    time.sleep(0.5)
  return "no click"


def main() -> int:
  if os.name != "nt":
    step("This check only runs on Windows.")
    return 1

  from maira.infrastructure.notifications.windows_toast import APP_ID, register_app_id  # noqa: PLC0415

  step(f"Python {sys.version.split()[0]} on {sys.platform}")
  step("1. Windows notification settings")
  toasts = _read_dword(r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled")
  app = _read_dword(rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{APP_ID}", "Enabled")
  step(f"   All notifications: {'OFF' if toasts == 0 else 'on'}")
  step(f"   Ultron notifications: {'OFF' if app == 0 else 'on / not set yet'}")

  step("2a. Importing notification library...")
  import windows_toasts  # noqa: PLC0415
  from windows_toasts import InteractableWindowsToaster, Toast, ToastButton  # noqa: PLC0415

  step(f"2b. windows-toasts {getattr(windows_toasts, '__version__', '?')} imported")

  step("3a. Registering Ultron with Windows...")
  register_app_id(APP_ID, "Ultron", None)
  step("3b. Creating notifier...")
  toaster = InteractableWindowsToaster("Ultron", notifierAUMID=APP_ID)
  step("3c. Building notification...")
  events: list[str] = []
  toast = Toast(["Ultron test (plain)", "Click Done if you can see this."])
  toast.AddAction(ToastButton("Done", "done"))
  toast.on_activated = lambda args: events.append(f"clicked {args.arguments}")
  toast.on_failed = lambda args: events.append(f"FAILED {getattr(args, 'error_code', '')}")
  step("3d. Sending plain notification (no Qt, no image)...")
  toaster.show_toast(toast)
  step("3e. Sent. Waiting 15s - click Done on the pop-up...")
  step(f"   Result: {_wait(events)}")

  step("4a. Starting Qt (like the app does)...")
  from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

  _app = QGuiApplication(sys.argv)
  step("4b. Rendering logo...")
  from maira.shared.utils.paths import data_dir  # noqa: PLC0415
  from maira.ui.system_tray import export_icon_files  # noqa: PLC0415

  icons = export_icon_files(data_dir() / "assets")
  step(f"   {icons}")
  step("4c. Sending notification the way Ultron does...")
  from maira.core.interfaces.notifier import Notification, NotificationAction  # noqa: PLC0415
  from maira.infrastructure.notifications.windows_toast import WindowsToastNotifier  # noqa: PLC0415

  events2: list[str] = []
  notifier = WindowsToastNotifier(
    lambda nid, action: events2.append(f"clicked {action}"),
    icon_path=icons.ico if icons else None,
    image_path=icons.png if icons else None,
    on_failed=lambda nid: events2.append("FAILED"),
  )
  step(f"   available: {notifier.is_available()}")
  notifier.show(
    Notification(
      "test",
      "Ultron test (full)",
      "Click Done or Snooze.",
      actions=(NotificationAction.DONE, NotificationAction.SNOOZE),
    )
  )
  step("4d. Sent. Waiting 15s - click a button...")
  step(f"   Result: {_wait(events2)}")
  step("Finished - send this whole output to Claude.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
