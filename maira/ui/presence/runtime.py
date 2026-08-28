"""Wires orb, tray, hotkey, and autostart to the main window and event bus."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from maira.app.settings import PresenceSettings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.os.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_ERROR as BRAIN_ERROR, TOPIC_TOKEN
from maira.modules.presence.mapper import apply_presence_event
from maira.modules.presence.state import PresenceState
from maira.modules.voice.service import TOPIC_ERROR as VOICE_ERROR, TOPIC_STATUS
from maira.shared.utils.paths import project_root
from maira.ui.presence.hotkey import GlobalHotkey
from maira.ui.presence.orb import OrbWidget, _STATE_COLOR, _diamond


def _tray_icon() -> QIcon:
  pix = QPixmap(64, 64)
  pix.fill(Qt.GlobalColor.transparent)
  painter = QPainter(pix)
  painter.setRenderHint(QPainter.RenderHint.Antialiasing)
  color = _STATE_COLOR[PresenceState.READY]
  painter.setPen(color)
  painter.setBrush(color)
  painter.drawPath(_diamond(32, 32, 18))
  painter.end()
  return QIcon(pix)


class PresenceRuntime(QObject):
  _event_arrived = Signal(str, object)

  def __init__(
    self,
    window: QWidget,
    event_bus: EventBus,
    settings: PresenceSettings,
    qt_app: QApplication,
    *,
    project_dir: Path | None = None,
  ) -> None:
    super().__init__(window)
    self._window = window
    self._bus = event_bus
    self._settings = settings
    self._qt_app = qt_app
    self._project_dir = project_dir or project_root()
    self._state = PresenceState.READY
    self._topics = (
      TOPIC_STATUS,
      VOICE_ERROR,
      TOPIC_TOKEN,
      TOPIC_COMPLETE,
      BRAIN_ERROR,
      "desktop.ran",
    )

    self.orb = OrbWidget()
    self.orb.clicked.connect(self.toggle_main_window)
    self.orb.move(40, 80)

    self._tray = QSystemTrayIcon(_tray_icon(), self)
    self._tray.setToolTip("Ultron")
    self._menu = QMenu()
    self._open_action = QAction("Open Ultron", self._menu)
    self._open_action.triggered.connect(self.show_main_window)
    self._orb_action = QAction("Show orb", self._menu)
    self._orb_action.setCheckable(True)
    self._orb_action.setChecked(True)
    self._orb_action.toggled.connect(self._toggle_orb)
    self._autostart_action = QAction("Start with Windows", self._menu)
    self._autostart_action.setCheckable(True)
    self._autostart_action.setChecked(is_autostart_enabled())
    self._autostart_action.toggled.connect(self._toggle_autostart)
    self._quit_action = QAction("Quit", self._menu)
    self._quit_action.triggered.connect(self.quit_app)
    self._menu.addAction(self._open_action)
    self._menu.addAction(self._orb_action)
    self._menu.addSeparator()
    self._menu.addAction(self._autostart_action)
    self._menu.addSeparator()
    self._menu.addAction(self._quit_action)
    self._tray.setContextMenu(self._menu)
    self._tray.activated.connect(self._tray_activated)

    self._handlers: dict[str, object] = {}
    self._event_arrived.connect(self._apply_bus_event)
    self._hotkey = GlobalHotkey(self, self.toggle_main_window)

  def start(self) -> None:
    self._qt_app.setQuitOnLastWindowClosed(False)
    setattr(self._window, "hide_on_close", True)
    for topic in self._topics:
      handler = self._make_handler(topic)
      self._handlers[topic] = handler
      self._bus.subscribe(topic, handler)

    if self._settings.autostart:
      try:
        enable_autostart(self._project_dir)
        self._autostart_action.blockSignals(True)
        self._autostart_action.setChecked(True)
        self._autostart_action.blockSignals(False)
      except OSError as exc:
        logger.warning("Could not enable Windows autostart: {}", exc)

    self._tray.show()
    if self._settings.orb_visible:
      self.orb.show()
    if self._settings.start_hidden:
      self._window.hide()
    else:
      self._window.show()
    logger.info("Desktop presence started (hotkey Ctrl+Alt+U)")

  def shutdown(self) -> None:
    for topic, handler in self._handlers.items():
      self._bus.unsubscribe(topic, handler)
    self._handlers.clear()
    self._hotkey.unregister()
    self._tray.hide()
    self.orb.close()

  def _make_handler(self, topic: str):
    def _handler(payload: object) -> None:
      self._event_arrived.emit(topic, payload)

    return _handler

  @Slot(str, object)
  def _apply_bus_event(self, topic: str, payload: object) -> None:
    nxt = apply_presence_event(topic, payload, self._state)
    if nxt is self._state:
      return
    self._state = nxt
    self.orb.set_presence_state(nxt)

  def show_main_window(self) -> None:
    self._window.show()
    self._window.raise_()
    self._window.activateWindow()

  def toggle_main_window(self) -> None:
    if self._window.isVisible():
      self._window.hide()
    else:
      self.show_main_window()

  def _toggle_orb(self, visible: bool) -> None:
    self.orb.setVisible(visible)

  def _toggle_autostart(self, enabled: bool) -> None:
    try:
      if enabled:
        enable_autostart(self._project_dir)
      else:
        disable_autostart()
    except OSError as exc:
      logger.warning("Autostart change failed: {}", exc)

  def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
      self.toggle_main_window()

  def quit_app(self) -> None:
    setattr(self._window, "hide_on_close", False)
    self.shutdown()
    self._qt_app.quit()
