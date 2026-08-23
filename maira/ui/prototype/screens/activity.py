"""Activity timeline screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from maira.ui.prototype.components.primitives import EmptyState, PageHeader
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class ActivityScreen(QWidget):
  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)
    root.addWidget(PageHeader("Activity", "A calm timeline of what Maira has done"))

    self.scroll = QScrollArea()
    self.scroll.setWidgetResizable(True)
    self.host = QWidget()
    self.layout_host = QVBoxLayout(self.host)
    self.layout_host.setSpacing(0)
    self.scroll.setWidget(self.host)
    root.addWidget(self.scroll, stretch=1)

    self.empty = EmptyState("Nothing here yet.", "Activity will appear as Maira works with you.")
    root.addWidget(self.empty)
    self.empty.hide()
    store.changed.connect(lambda k: k == "activity" and self.reload())
    self.reload()

  def reload(self) -> None:
    while self.layout_host.count():
      item = self.layout_host.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    items = [] if "activity" in self.store.force_empty else self.store.activity
    for i, event in enumerate(items):
      row = QFrame()
      row_layout = QHBoxLayout(row)
      row_layout.setContentsMargins(8, 10, 8, 10)
      row_layout.setSpacing(16)

      rail = QVBoxLayout()
      rail.setSpacing(0)
      dot = QLabel("●")
      dot.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 10px;")
      rail.addWidget(dot, alignment=Qt.AlignmentFlag.AlignHCenter)
      if i < len(items) - 1:
        line = QFrame()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {t.BORDER};")
        line.setMinimumHeight(28)
        rail.addWidget(line, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter)
      row_layout.addLayout(rail)

      col = QVBoxLayout()
      time = QLabel(event["time"])
      time.setObjectName("Muted")
      text = QLabel(event["text"])
      text.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 14px;")
      text.setWordWrap(True)
      col.addWidget(time)
      col.addWidget(text)
      row_layout.addLayout(col, stretch=1)
      self.layout_host.addWidget(row)

    self.layout_host.addStretch(1)
    self.empty.setVisible(not items)
    self.scroll.setVisible(bool(items))
