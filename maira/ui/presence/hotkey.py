"""Windows global hotkey (Ctrl+Alt+U) via RegisterHotKey. No extra dependency."""

from __future__ import annotations

import sys
from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QObject

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_U = 0x55
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x554C54  # "ULT"


class WinHotkeyFilter(QAbstractNativeEventFilter):
  def __init__(self, on_trigger: Callable[[], None]) -> None:
    super().__init__()
    self._on_trigger = on_trigger

  def nativeEventFilter(self, event_type: QByteArray | bytes, message: int) -> tuple[bool, int]:  # noqa: N802
    kind = bytes(event_type) if not isinstance(event_type, bytes) else event_type
    if kind != b"windows_generic_MSG":
      return False, 0
    try:
      import ctypes
      from ctypes import wintypes

      msg = wintypes.MSG.from_address(int(message))
    except (ValueError, TypeError, OSError):
      return False, 0
    if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
      self._on_trigger()
      return True, 0
    return False, 0


class GlobalHotkey(QObject):
  def __init__(self, parent: QObject | None, on_trigger: Callable[[], None]) -> None:
    super().__init__(parent)
    self._filter: WinHotkeyFilter | None = None
    self._registered = False
    if sys.platform != "win32":
      logger.info("Global hotkey skipped (Windows only)")
      return
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
    ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, modifiers, VK_U))
    if not ok:
      logger.warning("Could not register Ctrl+Alt+U — another app may own that hotkey")
      return
    self._registered = True
    self._filter = WinHotkeyFilter(on_trigger)
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
      app.installNativeEventFilter(self._filter)

  def unregister(self) -> None:
    if not self._registered or sys.platform != "win32":
      return
    import ctypes

    ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)  # type: ignore[attr-defined]
    self._registered = False
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None and self._filter is not None:
      app.removeNativeEventFilter(self._filter)
    self._filter = None
