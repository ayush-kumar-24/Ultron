"""System tray: keeps Ultron running in the background and shows reminders."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from maira.core.interfaces.notifier import Notification, Notifier
from maira.infrastructure.os.autostart import AutostartManager
from maira.ui.prototype.components.maira_logo import diamond_path
from maira.ui.prototype.theme import tokens as t

_BALLOON_MS = 10_000


def render_logo_pixmap(size: int = 64) -> QPixmap:
  """Nested-diamond mark on a dark rounded tile (readable on light and dark taskbars)."""
  pixmap = QPixmap(size, size)
  pixmap.fill(Qt.GlobalColor.transparent)
  painter = QPainter(pixmap)
  painter.setRenderHint(QPainter.RenderHint.Antialiasing)
  painter.setPen(Qt.PenStyle.NoPen)
  painter.setBrush(QColor(t.BG_ELEVATED))
  painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)

  c = size / 2
  painter.setBrush(Qt.BrushStyle.NoBrush)
  painter.setPen(QPen(QColor(t.ACCENT_LIGHT), max(1.5, size * 0.06)))
  painter.drawPath(diamond_path(c, c, size * 0.36))
  painter.setPen(QPen(QColor(t.GLOW_LAVENDER), max(1.0, size * 0.045)))
  painter.drawPath(diamond_path(c, c, size * 0.2))
  painter.setPen(Qt.PenStyle.NoPen)
  painter.setBrush(QColor(t.ACCENT_LIGHT))
  dot = size * 0.055
  painter.drawEllipse(QPointF(c - size * 0.2, c), dot, dot)
  painter.drawEllipse(QPointF(c + size * 0.2, c), dot, dot)
  painter.end()
  return pixmap


def app_icon() -> QIcon:
  icon = QIcon()
  for size in (16, 24, 32, 48, 64, 128):
    icon.addPixmap(render_logo_pixmap(size))
  return icon


@dataclass(frozen=True)
class IconFiles:
  png: Path  # toast image (Windows toasts only render PNG/JPG/GIF)
  ico: Path  # AUMID IconUri (must be .ico)


def export_icon_files(directory: Path) -> IconFiles | None:
  """Write the logo as PNG + ICO for Windows notifications."""
  try:
    directory.mkdir(parents=True, exist_ok=True)
    png_path = directory / "ultron_logo.png"
    ico_path = directory / "ultron_logo.ico"
    if not render_logo_pixmap(256).save(str(png_path), "PNG"):
      raise OSError(f"could not write {png_path}")
    from PIL import Image  # noqa: PLC0415

    with Image.open(png_path) as image:
      image.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    return IconFiles(png=png_path, ico=ico_path)
  except Exception:  # noqa: BLE001
    logger.exception("Could not export app icon")
    return None


class NotificationActionRelay(QObject):
  """Moves toast button clicks from the WinRT thread onto the Qt main thread.

  ``post`` is safe to call from any thread; ``handler`` always runs on the
  thread that owns the relay (create it on the main thread).
  """

  _action = Signal(str, str)  # notification_id, action

  def __init__(self, handler: Callable[[str, str], None], parent: QObject | None = None) -> None:
    super().__init__(parent)
    self._handler = handler
    self._action.connect(self._dispatch)

  def post(self, notification_id: str, action: str) -> None:
    self._action.emit(notification_id, action)

  @Slot(str, str)
  def _dispatch(self, notification_id: str, action: str) -> None:
    try:
      self._handler(notification_id, action)
    except Exception:  # noqa: BLE001
      logger.exception("Notification action failed")


class TrayController(QObject):
  open_requested = Signal()
  quit_requested = Signal()
  test_notification_requested = Signal()

  def __init__(
    self,
    icon: QIcon,
    *,
    app_name: str = "Ultron",
    autostart: AutostartManager | None = None,
    parent: QObject | None = None,
  ) -> None:
    super().__init__(parent)
    self._autostart = autostart
    self._hint_shown = False

    self._tray = QSystemTrayIcon(icon, self)
    self._tray.setToolTip(f"{app_name} — running in background")
    self._tray.activated.connect(self._on_activated)
    self._tray.messageClicked.connect(self.open_requested.emit)

    self._menu = QMenu()
    open_action = QAction(f"Open {app_name}", self._menu)
    open_action.triggered.connect(self.open_requested.emit)
    self._menu.addAction(open_action)
    self._menu.setDefaultAction(open_action)
    self._menu.addSeparator()

    self.autostart_action: QAction | None = None
    if autostart is not None and autostart.is_supported():
      self.autostart_action = QAction("Start with Windows", self._menu)
      self.autostart_action.setCheckable(True)
      self.autostart_action.setChecked(autostart.is_enabled())
      self.autostart_action.toggled.connect(self._toggle_autostart)
      self._menu.addAction(self.autostart_action)
      self._menu.addSeparator()

    test_action = QAction("Send test notification", self._menu)
    test_action.triggered.connect(self.test_notification_requested.emit)
    self._menu.addAction(test_action)
    self._menu.addSeparator()

    quit_action = QAction(f"Quit {app_name}", self._menu)
    quit_action.triggered.connect(self.quit_requested.emit)
    self._menu.addAction(quit_action)
    self._tray.setContextMenu(self._menu)

  @staticmethod
  def is_supported() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()

  def show(self) -> None:
    self._tray.show()

  def hide(self) -> None:
    self._tray.hide()

  def show_message(self, title: str, body: str) -> None:
    self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, _BALLOON_MS)

  def show_background_hint_once(self) -> None:
    if self._hint_shown:
      return
    self._hint_shown = True
    self.show_message(
      "Ultron is still running",
      "Reminders keep working. Right-click the tray icon to quit.",
    )

  def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
    if reason in (
      QSystemTrayIcon.ActivationReason.Trigger,
      QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
      self.open_requested.emit()

  def _toggle_autostart(self, enabled: bool) -> None:
    if self._autostart is None or self.autostart_action is None:
      return
    actual = self._autostart.set_enabled(enabled)
    if actual != enabled:
      self.autostart_action.blockSignals(True)
      self.autostart_action.setChecked(actual)
      self.autostart_action.blockSignals(False)


class TrayBalloonNotifier(Notifier):
  """Fallback when Windows toasts are unavailable: tray balloon, no buttons."""

  def __init__(self, tray: TrayController) -> None:
    self._tray = tray

  def name(self) -> str:
    return "tray-balloon"

  def is_available(self) -> bool:
    return QSystemTrayIcon.supportsMessages()

  def show(self, notification: Notification) -> bool:
    self._tray.show_message(notification.title, notification.body)
    return True
