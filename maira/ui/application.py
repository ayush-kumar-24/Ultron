"""QApplication factory — DPI, theme, and global Qt settings."""

import sys

from PySide6.QtWidgets import QApplication

from maira.app.settings import Settings
from maira.ui.prototype.theme.stylesheet import build_stylesheet


def create_qt_application(settings: Settings) -> QApplication:
  app = QApplication.instance()
  if app is None:
    app = QApplication(sys.argv)
  app.setApplicationName(settings.app_name)
  app.setStyleSheet(build_stylesheet())
  return app
