"""Automations screen — live scheduled jobs from AutomationService."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QDialog,
  QDialogButtonBox,
  QFormLayout,
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QPushButton,
  QTextEdit,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.primitives import EmptyState, PageHeader, ToggleSwitch
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class _CreateDialog(QDialog):
  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setWindowTitle("Create automation")
    self.setMinimumWidth(420)
    layout = QVBoxLayout(self)
    form = QFormLayout()
    self.title_edit = QLineEdit()
    self.title_edit.setPlaceholderText("Morning focus")
    self.when_edit = QLineEdit()
    self.when_edit.setPlaceholderText("e.g. tomorrow at 9am · in 10 minutes · every day at 8am")
    self.what_edit = QTextEdit()
    self.what_edit.setPlaceholderText("What should Maira do? e.g. open YouTube, remind me to stretch")
    self.what_edit.setFixedHeight(90)
    form.addRow("Title", self.title_edit)
    form.addRow("When", self.when_edit)
    form.addRow("Do this", self.what_edit)
    layout.addLayout(form)
    hint = QLabel("Tip: you can also say this in Chat — “remind me to stretch in 5 minutes”.")
    hint.setObjectName("Muted")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    buttons = QDialogButtonBox(
      QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

  def values(self) -> tuple[str, str, str]:
    return (
      self.title_edit.text().strip(),
      self.when_edit.text().strip(),
      self.what_edit.toPlainText().strip(),
    )


class AutomationsScreen(QWidget):
  create_requested = Signal(str, str, str)  # title, when, instruction
  toggle_requested = Signal(str, bool)
  delete_requested = Signal(str)

  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    self._live = False
    self._items: list[dict] = []

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)

    top = QHBoxLayout()
    top.addWidget(PageHeader("Automations", "Tell Maira what to do — and when"))
    top.addStretch(1)
    self.create_btn = QPushButton("+ Create Automation")
    self.create_btn.setObjectName("GhostButton")
    self.create_btn.clicked.connect(self._on_create)
    top.addWidget(self.create_btn)
    root.addLayout(top)

    note = QLabel(
      "Runs at the exact time while Maira is open. "
      "Chat examples: “open YouTube at 9pm” · “remind me to call mom in 10 minutes”."
    )
    note.setObjectName("Muted")
    note.setWordWrap(True)
    root.addWidget(note)

    self.host = QVBoxLayout()
    self.host.setSpacing(10)
    root.addLayout(self.host)
    root.addStretch(1)

    self.empty = EmptyState(
      "Nothing scheduled yet.",
      "Create one here or ask in Chat to schedule a task.",
    )
    root.addWidget(self.empty)
    self.empty.hide()

    store.changed.connect(lambda k: k == "automations" and not self._live and self.reload())
    self.reload()

  def set_live_mode(self, enabled: bool) -> None:
    self._live = enabled

  def set_automations(self, items: list[dict]) -> None:
    self._items = list(items)
    self._render(self._items)

  def reload(self) -> None:
    if self._live:
      self._render(self._items)
      return
    items = [] if "automations" in self.store.force_empty else self.store.automations
    self._render(items)

  def _render(self, items: list[dict]) -> None:
    while self.host.count():
      item = self.host.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    for auto in items:
      card = QFrame()
      card.setObjectName("Card")
      layout = QHBoxLayout(card)
      layout.setContentsMargins(18, 16, 18, 16)
      col = QVBoxLayout()
      title = QLabel(auto["title"])
      title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 15px; font-weight: 500;")
      schedule = QLabel(auto.get("schedule", ""))
      schedule.setObjectName("Muted")
      schedule.setWordWrap(True)
      col.addWidget(title)
      col.addWidget(schedule)
      if auto.get("instruction"):
        detail = QLabel(auto["instruction"])
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        col.addWidget(detail)
      layout.addLayout(col, stretch=1)
      state = QLabel("ON" if auto.get("enabled") else "OFF")
      state.setObjectName("Muted")
      layout.addWidget(state)
      toggle = ToggleSwitch(bool(auto.get("enabled")))
      toggle.toggled.connect(
        lambda checked, aid=auto["id"]: self._on_toggle(aid, checked)
      )
      layout.addWidget(toggle)
      delete = QPushButton("Delete")
      delete.setObjectName("GhostButton")
      delete.clicked.connect(lambda _=False, aid=auto["id"]: self._on_delete(aid))
      layout.addWidget(delete)
      self.host.addWidget(card)
    self.empty.setVisible(not items)

  def _on_create(self) -> None:
    if self._live:
      dialog = _CreateDialog(self)
      if dialog.exec() != QDialog.DialogCode.Accepted:
        return
      title, when, instruction = dialog.values()
      if not when or not instruction:
        self.store.toast.emit("Need a time and what to do")
        return
      self.create_requested.emit(title, when, instruction)
      return
    self.store.add_automation()

  def _on_toggle(self, auto_id: str, enabled: bool) -> None:
    if self._live:
      self.toggle_requested.emit(auto_id, enabled)
    else:
      self.store.toggle_automation(auto_id)

  def _on_delete(self, auto_id: str) -> None:
    if self._live:
      self.delete_requested.emit(auto_id)
    else:
      self.store.automations = [a for a in self.store.automations if a["id"] != auto_id]
      self.store.changed.emit("automations")
