"""Check Windows notifications step by step.

Run from the project folder:  python -m scripts.test_notification
"""

from __future__ import annotations

import os
import sys
import time


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
    print("This check only runs on Windows.")
    return 1

  from maira.infrastructure.notifications.windows_toast import APP_ID  # noqa: PLC0415

  print("1. Windows notification settings")
  toasts = _read_dword(r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled")
  app = _read_dword(
    rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{APP_ID}", "Enabled"
  )
  print(f"   All notifications: {'OFF  <-- turn on in Settings > System > Notifications' if toasts == 0 else 'on'}")
  print(f"   Ultron notifications: {'OFF  <-- turn on Ultron in Settings > System > Notifications' if app == 0 else 'on / not set yet'}")
  print("   (Also check Do Not Disturb / Focus is off.)")

  print("2. Notification library")
  try:
    import windows_toasts  # noqa: F401, PLC0415
  except ImportError:
    print("   MISSING  <-- run: pip install -e .")
    return 1
  print("   installed")

  print("3. Sending a test notification...")
  from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

  from maira.infrastructure.notifications.windows_toast import WindowsToastNotifier  # noqa: PLC0415
  from maira.core.interfaces.notifier import Notification, NotificationAction  # noqa: PLC0415
  from maira.shared.utils.paths import data_dir  # noqa: PLC0415
  from maira.ui.system_tray import export_icon_files  # noqa: PLC0415

  _app = QGuiApplication(sys.argv)  # needed to render the logo
  icons = export_icon_files(data_dir() / "assets")
  events: list[str] = []
  notifier = WindowsToastNotifier(
    lambda nid, action: events.append(f"clicked: {action}"),
    icon_path=icons.ico if icons else None,
    image_path=icons.png if icons else None,
    on_failed=lambda nid: events.append("FAILED"),
  )
  if not notifier.is_available():
    print("   Setup failed  <-- send data/logs/maira.log")
    return 1
  notifier.show(
    Notification(
      "test",
      "Ultron test notification",
      "If you can see this, notifications work. Click Done.",
      actions=(NotificationAction.DONE, NotificationAction.SNOOZE),
    )
  )
  print("   Sent. Waiting 20 seconds — click a button on the pop-up...")
  for _ in range(40):
    if events:
      break
    time.sleep(0.5)

  if not events:
    print("   No response. If no pop-up appeared, check step 1 and Do Not Disturb.")
  elif events[0] == "FAILED":
    print("   Windows REJECTED the notification  <-- send this output to Claude")
  else:
    print(f"   Works! ({events[0]})")
  return 0


if __name__ == "__main__":
  sys.exit(main())
