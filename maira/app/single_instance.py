"""One Ultron per user — a second launch brings the running window forward."""

from __future__ import annotations

import getpass
import re

from loguru import logger
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SHOW = b"show"
_CONNECT_TIMEOUT_MS = 500


def default_server_name(app_name: str = "Ultron") -> str:
  try:
    user = getpass.getuser()
  except Exception:  # noqa: BLE001
    user = "user"
  return re.sub(r"[^A-Za-z0-9_-]", "_", f"{app_name}-{user}").lower()


class SingleInstanceGuard(QObject):
  """Needs a QCoreApplication; ``activation_requested`` fires on the primary."""

  activation_requested = Signal()

  def __init__(self, server_name: str | None = None, parent: QObject | None = None) -> None:
    super().__init__(parent)
    self._name = server_name or default_server_name()
    self._server: QLocalServer | None = None
    self._connections: set[QLocalSocket] = set()

  def try_acquire(self) -> bool:
    """Return True if this is the only instance; otherwise signal the running one."""
    if self._notify_running():
      logger.info("Ultron is already running; asked it to show its window")
      return False

    server = QLocalServer(self)
    # A crashed instance can leave a stale socket file behind (non-Windows).
    QLocalServer.removeServer(self._name)
    if not server.listen(self._name):
      logger.warning("Single-instance server failed: {}", server.errorString())
      return True
    server.newConnection.connect(self._on_connection)
    self._server = server
    return True

  def release(self) -> None:
    for connection in list(self._connections):
      connection.readyRead.disconnect()
      connection.disconnected.disconnect()
      connection.abort()
      connection.deleteLater()
    self._connections.clear()
    if self._server is not None:
      self._server.close()
      self._server.deleteLater()
      self._server = None

  def _notify_running(self) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(self._name)
    if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
      return False
    socket.write(_SHOW)
    socket.flush()
    socket.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
    socket.disconnectFromServer()
    # Finish disconnecting before the socket is freed, or queued events crash Qt.
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
      socket.waitForDisconnected(_CONNECT_TIMEOUT_MS)
    return True

  def _on_connection(self) -> None:
    if self._server is None:
      return
    while self._server.hasPendingConnections():
      connection = self._server.nextPendingConnection()
      self._connections.add(connection)
      connection.readyRead.connect(lambda c=connection: self._on_ready(c))
      connection.disconnected.connect(lambda c=connection: self._on_disconnected(c))
      if connection.bytesAvailable():
        self._on_ready(connection)

  def _on_ready(self, connection: QLocalSocket) -> None:
    if bytes(connection.readAll().data()).strip() == _SHOW:
      self.activation_requested.emit()

  def _on_disconnected(self, connection: QLocalSocket) -> None:
    if connection in self._connections:
      self._connections.discard(connection)
      connection.deleteLater()
