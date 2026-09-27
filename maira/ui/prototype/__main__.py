"""Standalone Maira UI prototype entrypoint.

Launch:
  python -m maira.ui.prototype

This prototype uses mock data only. It does not connect to Ollama,
SQLite, ChromaDB, or any existing backend services.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.shell.main_window import PrototypeWindow
from maira.ui.prototype.theme.stylesheet import build_stylesheet


def main() -> int:
  app = QApplication.instance() or QApplication(sys.argv)
  app.setApplicationName("Ultron")
  app.setStyleSheet(build_stylesheet())

  store = MockStore()
  # Fresh prototype sessions show onboarding once per process.
  store.profile["onboarded"] = False

  window = PrototypeWindow(store)
  window.show()
  return app.exec()


if __name__ == "__main__":
  raise SystemExit(main())
