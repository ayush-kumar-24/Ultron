"""Home screen — centered greeting, command input, quick actions."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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


class HomeScreen(QWidget):
  command = Signal(str, str)
  quick_action = Signal(str)
  voice = Signal()

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
    self.command_input.notice.connect(self.store.toast.emit)
    layout.addWidget(self.command_input, alignment=Qt.AlignmentFlag.AlignCenter)

    actions = QHBoxLayout()
    actions.setSpacing(10)
    actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
    for item in store.quick_actions():
      btn = QPushButton(item["label"])
      btn.setObjectName("QuickAction")
      btn.setCursor(Qt.CursorShape.PointingHandCursor)
      btn.clicked.connect(lambda _=False, i=item["id"]: self.quick_action.emit(i))
      actions.addWidget(btn)
    layout.addLayout(actions)

    outer.addStretch(1)
    outer.addWidget(center, alignment=Qt.AlignmentFlag.AlignCenter)
    outer.addStretch(1)
    self.refresh()
    store.changed.connect(self._on_changed)

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
