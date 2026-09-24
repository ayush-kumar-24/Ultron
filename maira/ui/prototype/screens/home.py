"""Home screen — centered greeting, command input, quick actions."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from maira.ui.prototype.components.command_input import CommandInput
from maira.ui.prototype.components.maira_logo import MairaLogo
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


def _greeting_prefix() -> str:
  hour = datetime.now().hour
  if hour < 12:
    return "Good morning"
  if hour < 18:
    return "Good afternoon"
  return "Good evening"


class _OverviewColumn(QWidget):
  """One column of the Today panel: a clickable header and a few lines."""

  def __init__(self, title: str, empty_text: str, on_open, parent=None) -> None:
    super().__init__(parent)
    self._empty_text = empty_text
    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    self.header = QPushButton(title)
    self.header.setObjectName("GhostButton")
    self.header.setCursor(Qt.CursorShape.PointingHandCursor)
    self.header.setStyleSheet(f"text-align: left; padding: 2px 0; color: {t.TEXT_SECONDARY}; font-size: 12px;")
    self.header.clicked.connect(on_open)
    layout.addWidget(self.header)
    self._rows = QVBoxLayout()
    self._rows.setSpacing(6)
    layout.addLayout(self._rows)
    layout.addStretch(1)

  def set_items(self, items: list, *, header: str | None = None) -> None:
    if header is not None:
      self.header.setText(header)
    while self._rows.count():
      item = self._rows.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    if not items:
      empty = QLabel(self._empty_text)
      empty.setObjectName("Muted")
      empty.setWordWrap(True)
      self._rows.addWidget(empty)
      return
    for entry in items:
      title = QLabel(entry.title)
      title.setWordWrap(True)
      title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px;")
      self._rows.addWidget(title)
      if entry.meta:
        meta = QLabel(entry.meta)
        color = t.STATUS_WARN if entry.warn else t.TEXT_MUTED
        meta.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._rows.addWidget(meta)


class HomeScreen(QWidget):
  command = Signal(str, str)
  quick_action = Signal(str)
  voice = Signal()
  talk = Signal()
  open_screen = Signal(str)

  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    outer = QVBoxLayout(self)
    outer.setContentsMargins(32, 24, 32, 24)

    center = QWidget()
    center.setMaximumWidth(760)
    layout = QVBoxLayout(center)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setSpacing(18)

    self.logo = MairaLogo(size="large", glowing=True, animated=True)
    layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignCenter)

    self.greeting = QLabel()
    self.greeting.setObjectName("Greeting")
    self.greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(self.greeting)

    sub = QLabel("How can I help you today?")
    sub.setObjectName("GreetingSub")
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(sub)

    layout.addSpacing(8)
    self.command_input = CommandInput(compact=False)
    self.command_input.submitted.connect(self.command.emit)
    self.command_input.voice_clicked.connect(self.voice.emit)
    self.command_input.talk_clicked.connect(self.talk.emit)
    self.command_input.notice.connect(self.store.toast.emit)
    layout.addWidget(self.command_input, alignment=Qt.AlignmentFlag.AlignCenter)

    self._actions = QHBoxLayout()
    self._actions.setSpacing(10)
    self._actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addLayout(self._actions)
    self.set_quick_actions(store.quick_actions())

    # Today panel — filled with real data in live mode (see OverviewBridge).
    self.overview = QFrame()
    self.overview.setObjectName("Card")
    panel = QHBoxLayout(self.overview)
    panel.setContentsMargins(18, 14, 18, 14)
    panel.setSpacing(24)
    self.tasks_column = _OverviewColumn(
      "Aaj ke tasks", "Koi task nahi. \"add task …\" likho.", lambda: self.open_screen.emit("tasks")
    )
    self.reminders_column = _OverviewColumn(
      "Aane wale reminders", "Koi reminder nahi.", lambda: self.open_screen.emit("automations")
    )
    self.notes_column = _OverviewColumn(
      "Recent notes", "Abhi koi note nahi.", lambda: self.open_screen.emit("notes")
    )
    for column in (self.tasks_column, self.reminders_column, self.notes_column):
      panel.addWidget(column, stretch=1)
    layout.addSpacing(6)
    layout.addWidget(self.overview)
    self.overview.hide()

    outer.addStretch(1)
    outer.addWidget(center, alignment=Qt.AlignmentFlag.AlignCenter)
    outer.addStretch(1)
    self.refresh()
    store.changed.connect(self._on_changed)

  def set_quick_actions(self, items: list[dict]) -> None:
    while self._actions.count():
      item = self._actions.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    for item in items:
      btn = QPushButton(item["label"])
      btn.setObjectName("QuickAction")
      btn.setCursor(Qt.CursorShape.PointingHandCursor)
      btn.clicked.connect(lambda _=False, i=item["id"]: self.quick_action.emit(i))
      self._actions.addWidget(btn)

  def set_overview(self, overview) -> None:
    """Show today's tasks, upcoming reminders and recent notes (HomeOverview)."""
    total = overview.tasks_total
    header = f"Aaj ke tasks ({total})" if total else "Aaj ke tasks"
    self.tasks_column.set_items(overview.tasks, header=header)
    self.reminders_column.set_items(overview.reminders)
    self.notes_column.set_items(overview.notes)
    self.overview.show()

  def prefill(self, text: str) -> None:
    """Put a starter phrase in the input and focus it (e.g. "add task ")."""
    self.command_input.set_text(text)
    self.command_input.focus_input()

  def _on_changed(self, key: str) -> None:
    if key == "profile":
      self.refresh()

  def refresh(self) -> None:
    name = self.store.greeting_name()
    self.greeting.setText(f"{_greeting_prefix()}, {name}.")

  def focus_command(self) -> None:
    self.command_input.focus_input()
    self.logo.set_intensity(0.7)

  def set_thinking(self, thinking: bool) -> None:
    self.logo.set_animated(True)
    self.logo.set_glowing(thinking)
    self.logo.set_intensity(0.85 if thinking else 0.35)
