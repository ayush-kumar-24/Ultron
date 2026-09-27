"""One Ultron per user.

A second launch of the same code brings the running window forward. A launch
of *different* code (after ``git pull``) asks the running copy to quit and
takes over, so updates apply without hunting for the tray icon.
"""

from __future__ import annotations

import getpass
import hashlib
import re
import time
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_CONNECT_TIMEOUT_MS = 500
_REPLY_TIMEOUT_MS = 1500
_TAKEOVER_TIMEOUT_S = 30.0
_SHOWN = b"shown"
_REPLACE = b"replace"


def default_server_name(app_name: str = "Ultron") -> str:
  try:
    user = getpass.getuser()
  except Exception:  # noqa: BLE001
    user = "user"
  return re.sub(r"[^A-Za-z0-9_-]", "_", f"{app_name}-{user}").lower()


def compute_build_id(root: Path | None = None) -> str:
  """Fingerprint of the app's code; changes whenever a .py file changes."""
  base = root or Path(__file__).resolve().parents[1]  # the maira package
  digest = hashlib.sha1()
  for path in sorted(base.rglob("*.py")):
    try:
      stat = path.stat()
    except OSError:
      continue
    digest.update(f"{path.relative_to(base)}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
  return digest.hexdigest()[:16]


class SingleInstanceGuard(QObject):
  """Needs a QCoreApplication.

  On the running (primary) instance: ``activation_requested`` = show the window,
  ``replace_requested`` = a newer build started; quit now.
  """

  activation_requested = Signal()
  replace_requested = Signal()

  def __init__(
    self,
    server_name: str | None = None,
    parent: QObject | None = None,
    *,
    build_id: str | None = None,
    takeover_timeout_s: float = _TAKEOVER_TIMEOUT_S,
  ) -> None:
    super().__init__(parent)
    self._name = server_name or default_server_name()
    self._build_id = build_id if build_id is not None else compute_build_id()
    self._takeover_timeout_s = takeover_timeout_s
    self._server: QLocalServer | None = None
    self._connections: set[QLocalSocket] = set()

  def try_acquire(self) -> bool:
    """True if this process should run (first instance, or took over an old build)."""
    reply = self._ask_running()
    if reply == _SHOWN:
      logger.info("Ultron is already running; brought its window forward")
      return False
    if reply == _REPLACE:
      logger.info("An older Ultron is running; replacing it with this version")
      if not self._wait_for_exit():
        logger.warning("The older Ultron did not quit; quit it from the tray and start again")
        return False
    elif reply is not None:
      # Connected, but it runs a build from before automatic replacement.
      logger.warning(
        "An older Ultron is still running. Quit it from the tray icon "
        "(right-click → Quit Ultron), then start again."
      )
      return False
    return self._listen()

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

  def _listen(self) -> bool:
    server = QLocalServer(self)
    # A crashed instance can leave a stale socket file behind (non-Windows).
    QLocalServer.removeServer(self._name)
    if not server.listen(self._name):
      logger.warning("Single-instance server failed: {}", server.errorString())
      return True
    server.newConnection.connect(self._on_connection)
    self._server = server
    return True

  def _ask_running(self) -> bytes | None:
    """None: nothing running. Otherwise the running instance's reply (b"" = none)."""
    socket = QLocalSocket()
    socket.connectToServer(self._name)
    if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
      return None
    socket.write(f"show:{self._build_id}\n".encode())
    socket.flush()
    socket.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
    reply = b""
    if socket.waitForReadyRead(_REPLY_TIMEOUT_MS):
      reply = bytes(socket.readAll().data()).strip()
    socket.disconnectFromServer()
    # Finish disconnecting before the socket is freed, or queued events crash Qt.
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
      socket.waitForDisconnected(_CONNECT_TIMEOUT_MS)
    return reply

  def _wait_for_exit(self) -> bool:
    deadline = time.monotonic() + self._takeover_timeout_s
    while time.monotonic() < deadline:
      probe = QLocalSocket()
      probe.connectToServer(self._name)
      if not probe.waitForConnected(200):
        return True
      probe.abort()
      time.sleep(0.3)
    return False

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
    message = bytes(connection.readAll().data()).strip().decode(errors="replace")
    if not message.startswith("show"):
      return
    _, _, their_build = message.partition(":")
    if their_build and their_build != self._build_id:
      connection.write(_REPLACE + b"\n")
      connection.flush()
      logger.info("A newer Ultron started; quitting so it can take over")
      self.replace_requested.emit()
    else:
      connection.write(_SHOWN + b"\n")
      connection.flush()
      self.activation_requested.emit()

  def _on_disconnected(self, connection: QLocalSocket) -> None:
    if connection in self._connections:
      self._connections.discard(connection)
      connection.deleteLater()
