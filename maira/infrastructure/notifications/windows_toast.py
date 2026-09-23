"""Windows toast notifications with action buttons (``windows-toasts``)."""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from maira.core.interfaces.notifier import Notification, NotificationAction, Notifier

APP_ID = "Ultron.PersonalAI"
_SEP = "|"
_LABELS = {
  NotificationAction.DONE: "Done",
  NotificationAction.SNOOZE: "Snooze",
}

ActionCallback = Callable[[str, str], None]  # notification_id, action


def encode_arguments(action: NotificationAction, notification_id: str) -> str:
  return f"{action.value}{_SEP}{notification_id}"


def decode_arguments(arguments: str | None) -> tuple[str, str] | None:
  """Parse toast activation arguments into (notification_id, action)."""
  if not arguments or _SEP not in arguments:
    return None
  action, _, notification_id = arguments.partition(_SEP)
  if not action or not notification_id:
    return None
  return notification_id, action


def register_app_id(app_id: str, display_name: str, icon_path: Path | None) -> None:
  """Register an AUMID under HKCU so toast buttons call back into this app."""
  import winreg  # noqa: PLC0415 — Windows only

  key_path = f"SOFTWARE\\Classes\\AppUserModelId\\{app_id}"
  with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
    winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
    if icon_path is not None and icon_path.suffix == ".ico" and icon_path.exists():
      winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon_path.resolve()))


class WindowsToastNotifier(Notifier):
  """Toasts appear in the Windows notification centre, even when Ultron is hidden.

  ``on_action`` is called from a WinRT thread; the caller must marshal it to Qt.
  """

  def __init__(
    self,
    on_action: ActionCallback,
    *,
    app_name: str = "Ultron",
    app_id: str = APP_ID,
    icon_path: Path | None = None,
  ) -> None:
    self._on_action = on_action
    self._app_name = app_name
    self._app_id = app_id
    self._icon_path = icon_path
    self._toaster = None
    self._available: bool | None = None
    # Keep recent toasts alive so their button callbacks are never collected.
    self._recent: deque = deque(maxlen=20)

  def name(self) -> str:
    return "windows-toast"

  def is_available(self) -> bool:
    if self._available is None:
      self._available = self._setup()
    return self._available

  def _setup(self) -> bool:
    if os.name != "nt":
      return False
    try:
      from windows_toasts import InteractableWindowsToaster  # noqa: PLC0415
    except ImportError:
      logger.warning("windows-toasts not installed; using tray notifications")
      return False
    try:
      register_app_id(self._app_id, self._app_name, self._icon_path)
      self._toaster = InteractableWindowsToaster(self._app_name, notifierAUMID=self._app_id)
    except Exception:  # noqa: BLE001
      logger.exception("Windows toast setup failed")
      return False
    return True

  def show(self, notification: Notification) -> bool:
    if not self.is_available() or self._toaster is None:
      return False
    from windows_toasts import (  # noqa: PLC0415
      Toast,
      ToastButton,
      ToastDisplayImage,
      ToastDuration,
      ToastImage,
      ToastImagePosition,
      ToastScenario,
    )

    toast = Toast(
      [notification.title, notification.body],
      duration=ToastDuration.Long,
      # Reminder scenario keeps the toast on screen until the user acts.
      scenario=ToastScenario.Reminder if notification.actions else ToastScenario.Default,
      launch_action=encode_arguments(NotificationAction.OPEN, notification.id),
    )
    for action in notification.actions:
      toast.AddAction(ToastButton(_LABELS.get(action, action.value.title()), encode_arguments(action, notification.id)))
    if self._icon_path is not None and self._icon_path.exists():
      toast.AddImage(
        ToastDisplayImage(ToastImage(str(self._icon_path)), position=ToastImagePosition.AppLogo)
      )
    toast.on_activated = self._activated
    self._toaster.show_toast(toast)
    self._recent.append(toast)
    return True

  def _activated(self, event_args) -> None:
    parsed = decode_arguments(getattr(event_args, "arguments", None))
    if parsed is None:
      return
    try:
      self._on_action(*parsed)
    except Exception:  # noqa: BLE001
      logger.exception("Toast action handler failed")
