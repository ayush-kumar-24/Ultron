"""Restart Ultron in place (used by Settings → "Restart now")."""

from __future__ import annotations

import sys

from loguru import logger

from maira.infrastructure.os.autostart import BACKGROUND_FLAG
from maira.shared.utils.paths import project_root


def relaunch_arguments(orig_argv: list[str] | None = None) -> list[str]:
  """Arguments to start the same way again, but with the window shown."""
  argv = list(orig_argv if orig_argv is not None else getattr(sys, "orig_argv", sys.argv))
  args = [a for a in argv[1:] if a != BACKGROUND_FLAG]
  # Interpreter options such as -X faulthandler are kept; so is "-m maira" or "ultron.pyw".
  return args or ["-m", "maira"]


def restart_app(qt_app, guard) -> None:
  """Start a new Ultron and quit this one.

  The single-instance lock is released first, otherwise the new process would
  only bring this (closing) window forward and exit.
  """
  from PySide6.QtCore import QProcess  # noqa: PLC0415

  guard.release()
  args = relaunch_arguments()
  started = QProcess.startDetached(sys.executable, args, str(project_root()))
  ok = started[0] if isinstance(started, tuple) else bool(started)
  if not ok:
    logger.error("Restart failed to launch {} {}", sys.executable, args)
    return
  logger.info("Restarting Ultron")
  qt_app.quit()
