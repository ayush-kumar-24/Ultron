"""Settings screen with category navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
  QComboBox,
  QFormLayout,
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QPushButton,
  QSlider,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.primitives import PageHeader, ToggleSwitch
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t

CATEGORIES = [
  ("general", "General"),
  ("ai", "AI"),
  ("voice", "Voice"),
  ("memory", "Memory"),
  ("privacy", "Privacy"),
  ("automation", "Automation"),
  ("developer", "Developer"),
  ("status", "System Status"),
]


class SettingsScreen(QWidget):
  def __init__(self, store: MockStore, parent=None) -> None:
    super().__init__(parent)
    self.store = store
    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)
    root.addWidget(PageHeader("Settings", "Shape how Ultron works for you"))

    body = QHBoxLayout()
    body.setSpacing(16)

    self.nav = QListWidget()
    self.nav.setFixedWidth(200)
    for key, label in CATEGORIES:
      item = QListWidgetItem(label)
      item.setData(Qt.ItemDataRole.UserRole, key)
      self.nav.addItem(item)
    self.nav.currentRowChanged.connect(self._switch)
    body.addWidget(self.nav)

    self.stack = QStackedWidget()
    self.pages: dict[str, QWidget] = {}
    for key, _label in CATEGORIES:
      page = self._build_page(key)
      self.pages[key] = page
      self.stack.addWidget(page)
    body.addWidget(self.stack, stretch=1)
    root.addLayout(body, stretch=1)
    self.nav.setCurrentRow(0)

  def _switch(self, index: int) -> None:
    self.stack.setCurrentIndex(max(0, index))

  def show_category(self, key: str) -> None:
    for i, (k, _) in enumerate(CATEGORIES):
      if k == key:
        self.nav.setCurrentRow(i)
        break

  def _card(self) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    return frame

  def _build_page(self, key: str) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    card = self._card()
    form = QFormLayout(card)
    form.setContentsMargins(20, 20, 20, 20)
    form.setSpacing(14)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    s = self.store.settings

    if key == "general":
      name = QLineEdit(s["general"]["name"])
      name.textChanged.connect(lambda v: self._set("general", "name", v))
      theme = QComboBox()
      theme.addItems(["Dark", "System"])
      theme.setCurrentText(s["general"]["theme"])
      startup = QComboBox()
      startup.addItems(["Open Home", "Open Chat", "Start Voice"])
      startup.setCurrentText(s["general"]["startup"])
      lang = QComboBox()
      lang.addItems(["English", "Hindi"])
      form.addRow("Name", name)
      form.addRow("Theme", theme)
      form.addRow("Startup behavior", startup)
      form.addRow("Language", lang)
    elif key == "ai":
      model = QComboBox()
      model.addItems(["llama3.2", "llama3.1", "mistral", "qwen2.5"])
      model.setCurrentText(s["ai"]["model"])
      provider = QComboBox()
      provider.addItems(["Ollama (Local)", "Custom"])
      temp = QSlider(Qt.Orientation.Horizontal)
      temp.setRange(0, 100)
      temp.setValue(int(s["ai"]["temperature"] * 100))
      context = QComboBox()
      context.addItems(["4k", "8k", "16k", "32k"])
      context.setCurrentText(s["ai"]["context"])
      form.addRow("Model", model)
      form.addRow("Provider", provider)
      form.addRow("Temperature", temp)
      form.addRow("Context", context)
    elif key == "voice":
      provider = QComboBox()
      provider.addItems(["Kokoro (Local) — default"])
      provider.setCurrentIndex(0)
      provider.setEnabled(False)
      voice = QComboBox()
      voice.addItems(["af_heart (female)", "af_bella", "af_sarah"])
      voice.setCurrentText("af_heart (female)")
      speed = QSlider(Qt.Orientation.Horizontal)
      speed.setRange(0, 100)
      speed.setValue(s["voice"]["speed"])
      volume = QSlider(Qt.Orientation.Horizontal)
      volume.setRange(0, 100)
      volume.setValue(s["voice"]["volume"])
      auto = ToggleSwitch(s["voice"]["auto_speak"])
      wake = ToggleSwitch(s["voice"]["wake_word"])
      interrupt = ToggleSwitch(s["voice"].get("interrupt_on_speech", True))
      form.addRow("Voice Provider", provider)
      form.addRow("Voice", voice)
      form.addRow("Speed", speed)
      form.addRow("Volume", volume)
      form.addRow("Auto speak responses", auto)
      form.addRow("Interrupt when user speaks", interrupt)
      form.addRow("Wake word", wake)
      hint = QLabel(
        "Chat mic: speak to type (like ChatGPT) · Hold Ctrl+Shift+V · Alt+V · "
        "Full spoken replies paused until a better Indian voice is ready"
      )
      hint.setObjectName("Muted")
      form.addRow("", hint)
    elif key == "memory":
      enable = ToggleSwitch(s["memory"]["enable"])
      automatic = ToggleSwitch(s["memory"]["automatic"])
      retention = QComboBox()
      retention.addItems(["Forever", "30 days", "90 days"])
      clear = QPushButton("Clear memory")
      clear.setObjectName("GhostButton")
      clear.clicked.connect(lambda: self.store.toast.emit("Memory cleared (mock)"))
      form.addRow("Enable memory", enable)
      form.addRow("Automatic memory", automatic)
      form.addRow("Retention", retention)
      form.addRow("", clear)
    elif key == "privacy":
      offline = ToggleSwitch(s["privacy"]["offline_mode"])
      loc = QLineEdit(s["privacy"]["data_location"])
      logs = ToggleSwitch(s["privacy"]["logs"])
      clear = QPushButton("Clear data")
      clear.setObjectName("GhostButton")
      clear.clicked.connect(lambda: self.store.toast.emit("Local data cleared (mock)"))
      form.addRow("Offline mode", offline)
      form.addRow("Data location", loc)
      form.addRow("Logs", logs)
      form.addRow("", clear)
    elif key == "automation":
      perms = QComboBox()
      perms.addItems(["Confirm sensitive", "Confirm all", "Allow safe"])
      confirm = ToggleSwitch(s["automation"]["confirmation"])
      form.addRow("Permissions", perms)
      form.addRow("Confirmation settings", confirm)
      hint = QLabel(
        "Desktop OS control is on via Chat: "
        "“open notepad and type hello” · “press ctrl+s” · “click 400, 300”. "
        "Install input support: pip install -e \".[desktop]\". "
        "Move mouse to a screen corner to abort typing/clicks (failsafe)."
      )
      hint.setObjectName("Muted")
      hint.setWordWrap(True)
      form.addRow(hint)
    elif key == "developer":
      debug = ToggleSwitch(s["developer"]["debug"])
      diag = ToggleSwitch(s["developer"]["diagnostics"])
      offline = QPushButton("Simulate Brain Offline")
      offline.setObjectName("GhostButton")
      offline.clicked.connect(lambda: self.store.set_status_offline(True))
      online = QPushButton("Restore System Healthy")
      online.setObjectName("GhostButton")
      online.clicked.connect(lambda: self.store.set_status_offline(False))
      err = QPushButton("Show Ollama error demo")
      err.setObjectName("GhostButton")
      err.clicked.connect(self._demo_error)
      form.addRow("Debug mode", debug)
      form.addRow("Diagnostics", diag)
      snap = s["developer"].get("diag_snapshot")
      if snap:
        panel = QLabel(str(snap))
        panel.setObjectName("Muted")
        panel.setWordWrap(True)
        form.addRow("ULTRON SYSTEM", panel)
      form.addRow("", offline)
      form.addRow("", online)
      form.addRow("", err)
    elif key == "status":
      status_widget = self._status_panel()
      form.addRow(status_widget)
      self.store.changed.connect(lambda k: k == "status" and self._refresh_status())

    layout.addWidget(card)
    layout.addStretch(1)
    return page

  def _set(self, section: str, key: str, value) -> None:
    self.store.settings[section][key] = value
    if section == "general" and key == "name":
      self.store.set_profile_name(str(value))

  def _demo_error(self) -> None:
    self.store.force_error = "ollama"
    self.store.toast.emit("Open Chat and send a message to see the error")

  def _status_panel(self) -> QWidget:
    wrap = QWidget()
    self._status_layout = QVBoxLayout(wrap)
    self._status_layout.setContentsMargins(0, 0, 0, 0)
    self._refresh_status()
    return wrap

  def _refresh_status(self) -> None:
    if not hasattr(self, "_status_layout"):
      return
    while self._status_layout.count():
      item = self._status_layout.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    healthy = all(s["state"] == "Ready" for s in self.store.status)
    header = QLabel("System Healthy" if healthy else "Attention needed")
    header.setStyleSheet(
      f"color: {t.STATUS_READY if healthy else t.STATUS_OFFLINE}; font-size: 13px; font-weight: 600;"
    )
    self._status_layout.addWidget(header)
    for item in self.store.status:
      row = QHBoxLayout()
      label = QLabel(item["label"])
      label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")
      state = item["state"]
      color = t.STATUS_READY if state == "Ready" else t.STATUS_OFFLINE
      status = QLabel(f"●  {state}")
      status.setStyleSheet(f"color: {color};")
      row.addWidget(label)
      row.addStretch(1)
      row.addWidget(status)
      holder = QWidget()
      holder.setLayout(row)
      self._status_layout.addWidget(holder)
