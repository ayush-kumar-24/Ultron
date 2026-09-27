"""First-run onboarding flow."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QButtonGroup,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QPushButton,
  QRadioButton,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.maira_logo import MairaLogo
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class OnboardingFlow(QWidget):
  finished = Signal()

  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    self.setStyleSheet(f"background-color: {t.BG_PRIMARY};")
    root = QVBoxLayout(self)
    root.setContentsMargins(40, 40, 40, 40)

    self.stack = QStackedWidget()
    self.stack.addWidget(self._welcome())
    self.stack.addWidget(self._name())
    self.stack.addWidget(self._voice())
    self.stack.addWidget(self._ready())
    self.stack.currentChanged.connect(self._on_page_changed)
    root.addStretch(1)
    root.addWidget(self.stack, alignment=Qt.AlignmentFlag.AlignCenter)
    root.addStretch(1)

  def _on_page_changed(self, index: int) -> None:
    if index == 1:
      self.name_input.setFocus()
      self.name_input.selectAll()
    elif index == 0:
      self.welcome_btn.setFocus()
    elif index == 2:
      self.voice_btn.setFocus()
    elif index == 3:
      self.ready_btn.setFocus()

  def _center_card(self) -> tuple[QWidget, QVBoxLayout]:
    card = QWidget()
    card.setFixedWidth(420)
    layout = QVBoxLayout(card)
    layout.setSpacing(18)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return card, layout

  def _primary_button(self, label: str, slot) -> QPushButton:
    btn = QPushButton(label)
    btn.setObjectName("PrimaryButton")
    btn.setDefault(True)
    btn.setAutoDefault(True)
    btn.clicked.connect(slot)
    return btn

  def _welcome(self) -> QWidget:
    card, layout = self._center_card()
    layout.addWidget(MairaLogo(size="large", glowing=True, animated=True), alignment=Qt.AlignmentFlag.AlignCenter)
    title = QLabel("Welcome to Ultron.")
    title.setObjectName("Greeting")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sub = QLabel("Your personal AI operating system.")
    sub.setObjectName("GreetingSub")
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    layout.addWidget(sub)

    pills = QHBoxLayout()
    for text in ("Private", "Local", "Yours"):
      pill = QLabel(text)
      pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
      pill.setStyleSheet(
        f"color: {t.TEXT_SECONDARY}; border: 1px solid {t.BORDER}; border-radius: 999px; padding: 6px 14px;"
      )
      pills.addWidget(pill)
    layout.addLayout(pills)

    self.welcome_btn = self._primary_button("Get Started", lambda: self.stack.setCurrentIndex(1))
    layout.addWidget(self.welcome_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    return card

  def _name(self) -> QWidget:
    card, layout = self._center_card()
    layout.addWidget(MairaLogo(size="medium", glowing=True), alignment=Qt.AlignmentFlag.AlignCenter)
    title = QLabel("What should I call you?")
    title.setObjectName("Greeting")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    self.name_input = QLineEdit(self.store.greeting_name())
    self.name_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.name_input.setPlaceholderText("Your name")
    self.name_input.returnPressed.connect(self._save_name)
    layout.addWidget(self.name_input)
    self.name_btn = self._primary_button("Continue", self._save_name)
    layout.addWidget(self.name_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    return card

  def _voice(self) -> QWidget:
    card, layout = self._center_card()
    layout.addWidget(MairaLogo(size="medium", glowing=True), alignment=Qt.AlignmentFlag.AlignCenter)
    title = QLabel("Choose your voice")
    title.setObjectName("Greeting")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    self.voice_group = QButtonGroup(self)
    for i, name in enumerate(("Voice A", "Voice B", "Voice C")):
      radio = QRadioButton(name)
      radio.setChecked(i == 0)
      self.voice_group.addButton(radio, i)
      layout.addWidget(radio, alignment=Qt.AlignmentFlag.AlignLeft)
    self.voice_btn = self._primary_button("Continue", self._save_voice)
    layout.addWidget(self.voice_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    return card

  def _ready(self) -> QWidget:
    card, layout = self._center_card()
    layout.addWidget(MairaLogo(size="large", glowing=True, animated=True), alignment=Qt.AlignmentFlag.AlignCenter)
    title = QLabel("Ultron is ready.")
    title.setObjectName("Greeting")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    self.ready_btn = self._primary_button("Start", self._finish)
    layout.addWidget(self.ready_btn, alignment=Qt.AlignmentFlag.AlignCenter)
    return card

  def keyPressEvent(self, event) -> None:  # noqa: N802
    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
      index = self.stack.currentIndex()
      if index == 0:
        self.stack.setCurrentIndex(1)
        return
      if index == 1:
        self._save_name()
        return
      if index == 2:
        self._save_voice()
        return
      if index == 3:
        self._finish()
        return
    super().keyPressEvent(event)

  def showEvent(self, event) -> None:  # noqa: N802
    super().showEvent(event)
    self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    self.setFocus()

  def _save_name(self) -> None:
    self.store.set_profile_name(self.name_input.text())
    self.stack.setCurrentIndex(2)
    self.setFocus()

  def _save_voice(self) -> None:
    btn = self.voice_group.checkedButton()
    if btn:
      self.store.set_voice_choice(btn.text())
    self.stack.setCurrentIndex(3)
    self.setFocus()

  def _finish(self) -> None:
    self.store.complete_onboarding()
    self.finished.emit()
