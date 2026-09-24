"""Real Settings screen: every control saves to data/config.yaml."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, Qt, QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
  QComboBox,
  QDoubleSpinBox,
  QFileDialog,
  QFormLayout,
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QMessageBox,
  QPlainTextEdit,
  QPushButton,
  QScrollArea,
  QSpinBox,
  QStackedWidget,
  QTimeEdit,
  QVBoxLayout,
  QWidget,
)

from maira.app.settings_schema import CATEGORIES, Field, fields_for
from maira.app.user_config import UserConfig
from maira.shared.utils.paths import project_root
from maira.ui.prototype.components.primitives import PageHeader, ToggleSwitch
from maira.ui.prototype.theme import tokens as t


@dataclass
class SettingsActions:
  """What the screen can ask the running app to do (all optional)."""

  restart: Callable[[], None] | None = None
  send_test_notification: Callable[[], str] | None = None  # returns a short result
  status: Callable[[], list[tuple[str, bool, str]]] | None = None
  ollama_models: Callable[[str], list[str] | None] | None = None
  autostart_supported: Callable[[], bool] | None = None
  autostart_enabled: Callable[[], bool] | None = None
  set_autostart: Callable[[bool], bool] | None = None
  preview_voice: Callable[[str, dict], Any] | None = None
  is_voice_installed: Callable[[str], bool] | None = None
  install_command: Callable[[str], list[str]] | None = None
  diagnostics: Callable[[], list[str]] | None = None
  data_dir: Path | None = None
  logs_dir: Path | None = None
  live: dict[str, Callable[[Any], None]] = field(default_factory=dict)  # path -> apply now
  skills: Any = None  # SkillService: the Skills page lists and installs skills


def _muted(text: str) -> QLabel:
  label = QLabel(text)
  label.setObjectName("Muted")
  label.setWordWrap(True)
  return label


class LiveSettingsScreen(QWidget):
  changed = Signal(str, object)  # path, value
  _background_done = Signal(object, object, str)  # callback, result, error

  def __init__(self, config: UserConfig, actions: SettingsActions | None = None, parent=None) -> None:
    super().__init__(parent)
    self.config = config
    self.actions = actions or SettingsActions()
    self._widgets: dict[str, QWidget] = {}
    self._rows: dict[str, tuple[QLabel, QWidget, QLabel | None]] = {}
    self._install: QProcess | None = None
    self._status_busy = False
    # Emitted from worker threads; Qt queues it onto the UI thread.
    self._background_done.connect(self._on_background_done)

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(12)
    root.addWidget(PageHeader("Settings", "Changes save automatically"))

    # Shown after a change that needs a restart.
    self.restart_bar = QFrame()
    self.restart_bar.setObjectName("Card")
    bar = QHBoxLayout(self.restart_bar)
    bar.setContentsMargins(14, 8, 14, 8)
    bar.addWidget(QLabel("Some changes apply after a restart."), stretch=1)
    self.restart_btn = QPushButton("Restart now")
    self.restart_btn.setObjectName("GhostButton")
    self.restart_btn.clicked.connect(self._restart)
    bar.addWidget(self.restart_btn)
    root.addWidget(self.restart_bar)
    self.restart_bar.hide()

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
    self._refresh_visibility()
    self.nav.setCurrentRow(0)

  # --- background work ---------------------------------------------------------------

  def _in_background(self, work: Callable[[], Any], done: Callable[[Any, str], None]) -> None:
    def run() -> None:
      try:
        result, error = work(), ""
      except Exception as exc:  # noqa: BLE001
        result, error = None, str(exc) or type(exc).__name__
      self._background_done.emit(done, result, error)

    threading.Thread(target=run, name="ultron-settings", daemon=True).start()

  def _on_background_done(self, done, result, error: str) -> None:
    done(result, error)

  # --- navigation -------------------------------------------------------------------

  def show_category(self, key: str) -> None:
    for i, (k, _) in enumerate(CATEGORIES):
      if k == key:
        self.nav.setCurrentRow(i)
        break

  def _switch(self, index: int) -> None:
    self.stack.setCurrentIndex(max(0, index))
    key = CATEGORIES[max(0, index)][0]
    if key == "status":
      self.refresh_status()
    elif key == "ai":
      self.refresh_models()
    elif key == "voice":
      self._refresh_install_state()

  # --- pages ------------------------------------------------------------------------

  def _build_page(self, key: str) -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    page = QWidget()
    page.setObjectName("SettingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    extra = {
      "skills": self._skills_tools,
      "voice": self._voice_tools,
      "ai": self._ai_tools,
      "developer": self._developer_tools,
      "status": self._status_panel,
    }.get(key)
    if key == "skills" and extra is not None:
      layout.addWidget(extra())  # the skill list first, options below
      extra = None

    fields = fields_for(key)
    if fields or key == "general":
      card = QFrame()
      card.setObjectName("Card")
      form = QFormLayout(card)
      form.setContentsMargins(20, 18, 20, 18)
      form.setSpacing(10)
      form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
      for f in fields:
        self._add_field(form, f)
      if key == "general":
        self._add_autostart(form)
      layout.addWidget(card)

    if extra is not None:
      layout.addWidget(extra())
    layout.addStretch(1)
    scroll.setWidget(page)
    return scroll

  def _add_field(self, form: QFormLayout, f: Field) -> None:
    widget = self._make_widget(f)
    label = QLabel(f.label)
    label.setObjectName("Secondary")
    help_label = _muted(f.help) if f.help else None
    form.addRow(label, widget)
    if help_label is not None:
      form.addRow("", help_label)
    self._widgets[f.path] = widget
    self._rows[f.path] = (label, widget, help_label)

  def _make_widget(self, f: Field) -> QWidget:
    value = self.config.get(f.path)
    if f.kind == "bool":
      w = ToggleSwitch(bool(value))
      w.toggled.connect(lambda v, f=f: self._save(f, bool(v)))
      return w
    if f.kind == "choice":
      w = QComboBox()
      w.setEditable(f.editable)
      for option, text in f.options:
        w.addItem(text, option)
      self._select(w, value)
      if f.editable:
        w.lineEdit().editingFinished.connect(lambda f=f, w=w: self._save(f, self._combo_value(w)))
        w.activated.connect(lambda _i, f=f, w=w: self._save(f, self._combo_value(w)))
      else:
        w.currentIndexChanged.connect(lambda _i, f=f, w=w: self._save(f, w.currentData()))
      return w
    if f.kind == "int":
      w = QSpinBox()
      w.setRange(int(f.minimum), int(f.maximum))
      w.setSingleStep(int(f.step))
      w.setValue(int(value if value is not None else f.minimum))
      w.editingFinished.connect(lambda f=f, w=w: self._save(f, w.value()))
      return w
    if f.kind == "float":
      w = QDoubleSpinBox()
      w.setRange(f.minimum, f.maximum)
      w.setSingleStep(f.step)
      w.setDecimals(2)
      w.setValue(float(value if value is not None else f.minimum))
      w.editingFinished.connect(lambda f=f, w=w: self._save(f, round(w.value(), 2)))
      return w
    if f.kind == "time":
      w = QTimeEdit()
      w.setDisplayFormat("HH:mm")
      parsed = QTime.fromString(str(value or "08:00"), "H:mm")
      w.setTime(parsed if parsed.isValid() else QTime(8, 0))
      w.editingFinished.connect(lambda f=f, w=w: self._save(f, w.time().toString("HH:mm")))
      return w
    if f.kind == "file":
      box = QWidget()
      row = QHBoxLayout(box)
      row.setContentsMargins(0, 0, 0, 0)
      edit = QLineEdit(str(value or ""))
      edit.setPlaceholderText("No file")
      edit.editingFinished.connect(lambda f=f, e=edit: self._save(f, e.text().strip()))
      browse = QPushButton("Browse…")
      browse.setObjectName("GhostButton")
      browse.clicked.connect(lambda _=False, f=f, e=edit: self._browse(f, e))
      clear = QPushButton("Clear")
      clear.setObjectName("GhostButton")
      clear.clicked.connect(lambda _=False, f=f, e=edit: (e.setText(""), self._save(f, "")))
      row.addWidget(edit, stretch=1)
      row.addWidget(browse)
      row.addWidget(clear)
      box.line_edit = edit  # type: ignore[attr-defined]
      return box
    w = QLineEdit(str(value or ""))
    w.editingFinished.connect(lambda f=f, w=w: self._save(f, w.text().strip()))
    return w

  @staticmethod
  def _select(combo: QComboBox, value: Any) -> None:
    index = combo.findData(value)
    if index < 0 and value not in (None, ""):
      combo.addItem(str(value), value)
      index = combo.count() - 1
    combo.setCurrentIndex(max(0, index))

  @staticmethod
  def _combo_value(combo: QComboBox) -> Any:
    text = combo.currentText().strip()
    index = combo.findText(text)
    if index >= 0 and combo.itemData(index) is not None:
      return combo.itemData(index)
    return text

  def _browse(self, f: Field, edit: QLineEdit) -> None:
    path, _ = QFileDialog.getOpenFileName(self, f.label, str(Path.home()), "Audio (*.wav *.mp3 *.flac)")
    if path:
      edit.setText(path)
      self._save(f, path)

  # --- saving -----------------------------------------------------------------------

  def _save(self, f: Field, value: Any) -> None:
    if value == self.config.get(f.path):
      return
    self.config.set(f.path, value)
    for path, extra in (f.also_sets(value) if f.also_sets else {}).items():
      self.config.set(path, extra)
    live = self.actions.live.get(f.path)
    if live is not None:
      live(value)
    if f.restart:
      self.restart_bar.show()
    self.changed.emit(f.path, value)
    self._refresh_visibility()
    if f.path == "voice.tts.provider":
      self._refresh_install_state()

  def _refresh_visibility(self) -> None:
    for path, (label, widget, help_label) in self._rows.items():
      f = next(x for x in fields_for(self._category_of(path)) if x.path == path)
      visible = True
      if f.visible_when is not None:
        other, values = f.visible_when
        visible = self.config.get(other) in values
      for part in (label, widget, help_label):
        if part is not None:
          part.setVisible(visible)

  @staticmethod
  def _category_of(path: str) -> str:
    from maira.app.settings_schema import field_by_path  # noqa: PLC0415

    return field_by_path(path).category

  def _restart(self) -> None:
    if self.actions.restart is not None:
      self.actions.restart()

  # --- General: Start with Windows ------------------------------------------------------

  def _add_autostart(self, form: QFormLayout) -> None:
    supported = self.actions.autostart_supported() if self.actions.autostart_supported else False
    toggle = ToggleSwitch(bool(self.actions.autostart_enabled()) if supported and self.actions.autostart_enabled else False)
    toggle.setEnabled(supported)
    label = QLabel("Start with Windows")
    label.setObjectName("Secondary")
    form.addRow(label, toggle)
    form.addRow("", _muted("Starts hidden in the tray when you sign in." if supported else "Available on Windows."))
    if supported and self.actions.set_autostart is not None:
      toggle.toggled.connect(lambda on: toggle.setChecked(bool(self.actions.set_autostart(bool(on)))))
    self.autostart_toggle = toggle

  # --- Voice: install + preview -----------------------------------------------------------

  def _voice_tools(self) -> QWidget:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)

    install_row = QHBoxLayout()
    self.install_state = QLabel("")
    install_row.addWidget(self.install_state, stretch=1)
    self.install_btn = QPushButton("Install")
    self.install_btn.setObjectName("GhostButton")
    self.install_btn.clicked.connect(self._install_voice)
    install_row.addWidget(self.install_btn)
    layout.addLayout(install_row)
    self.install_log = QPlainTextEdit()
    self.install_log.setReadOnly(True)
    self.install_log.setMaximumHeight(160)
    self.install_log.hide()
    layout.addWidget(self.install_log)

    layout.addWidget(_muted("Hear the selected voice before restarting:"))
    preview_row = QHBoxLayout()
    self.preview_text = QLineEdit("Hello Ayush, main Ultron hoon. Aaj aapke do tasks hain.")
    preview_row.addWidget(self.preview_text, stretch=1)
    self.preview_btn = QPushButton("▶ Preview")
    self.preview_btn.setObjectName("GhostButton")
    self.preview_btn.clicked.connect(self._preview)
    preview_row.addWidget(self.preview_btn)
    layout.addLayout(preview_row)
    self.preview_state = _muted("First preview of a voice loads it (can take a minute).")
    layout.addWidget(self.preview_state)
    self._refresh_install_state()
    return card

  def _provider(self) -> str:
    return str(self.config.get("voice.tts.provider") or "kokoro")

  def _refresh_install_state(self) -> None:
    if not hasattr(self, "install_state"):
      return
    provider = self._provider()
    installed = self.actions.is_voice_installed(provider) if self.actions.is_voice_installed else True
    busy = self._install is not None
    names = {"kokoro": "Kokoro", "chatterbox": "Chatterbox", "indic_parler": "Indic Parler"}
    if installed:
      self.install_state.setText(f"● {names.get(provider, provider)} is installed")
      self.install_state.setStyleSheet(f"color: {t.STATUS_READY};")
    else:
      how = 'run: pip install -e ".[voice]"' if provider == "kokoro" else "click Install (downloads a few GB)"
      self.install_state.setText(f"● {names.get(provider, provider)} is not installed — {how}")
      self.install_state.setStyleSheet(f"color: {t.STATUS_WARN};")
    self.install_btn.setVisible(provider != "kokoro" and (not installed or busy))
    self.install_btn.setEnabled(not busy)
    self.install_btn.setText("Installing…" if busy else "Install")

  def _install_voice(self) -> None:
    provider = self._provider()
    if self.actions.install_command is None or self._install is not None:
      return
    command = self.actions.install_command(provider)
    process = QProcess(self)
    process.setWorkingDirectory(str(project_root()))
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    process.readyReadStandardOutput.connect(
      lambda: self.install_log.appendPlainText(bytes(process.readAllStandardOutput().data()).decode(errors="replace").rstrip())
    )
    process.finished.connect(lambda code, _status: self._install_finished(provider, code))
    self._install = process
    self.install_log.clear()
    self.install_log.show()
    self.install_log.appendPlainText(f"Installing {provider}. This can take 10–30 minutes; you can keep using Ultron.")
    self._refresh_install_state()
    process.start(command[0], command[1:])

  def _install_finished(self, provider: str, code: int) -> None:
    self._install = None
    if code == 0:
      self.install_log.appendPlainText("\n✓ Installed. Click Preview to hear it, then Restart now to use it.")
      self.restart_bar.show()
    else:
      self.install_log.appendPlainText(f"\n✗ Install failed (code {code}). The log above shows why.")
    self._refresh_install_state()

  def _preview(self) -> None:
    if self.actions.preview_voice is None:
      return
    provider = self._provider()
    values = {key: self.config.get(f"voice.tts.{key}") for key in
              ("voice", "speaker", "language", "reference_audio", "exaggeration", "device")}
    text = self.preview_text.text().strip() or "Hello, main Ultron hoon."
    self.preview_btn.setEnabled(False)
    self.preview_state.setText("Loading voice and speaking…")
    preview = self.actions.preview_voice
    self._in_background(lambda: preview(provider, dict(values, text=text)), self._preview_done)

  def _preview_done(self, result, error: str) -> None:
    self.preview_btn.setEnabled(True)
    if error:
      self.preview_state.setText(f"Preview failed: {error}")
    elif result is not None:
      self.preview_state.setText(result.message)

  # --- Skills ------------------------------------------------------------------------------

  def _skills_tools(self) -> QWidget:
    if self.actions.skills is None:
      return _muted("Skills are available when Ultron runs normally.")
    from maira.ui.prototype.screens.skills_panel import SkillsPanel  # noqa: PLC0415

    self.skills_panel = SkillsPanel(self.actions.skills)
    return self.skills_panel

  # --- AI: models from Ollama --------------------------------------------------------------

  def _ai_tools(self) -> QWidget:
    card = QFrame()
    card.setObjectName("Card")
    layout = QHBoxLayout(card)
    layout.setContentsMargins(20, 12, 20, 12)
    self.ollama_state = QLabel("")
    layout.addWidget(self.ollama_state, stretch=1)
    refresh = QPushButton("Refresh models")
    refresh.setObjectName("GhostButton")
    refresh.clicked.connect(self.refresh_models)
    layout.addWidget(refresh)
    return card

  def refresh_models(self) -> None:
    if self.actions.ollama_models is None or not hasattr(self, "ollama_state"):
      return
    host = str(self.config.get("ollama.host") or "")
    lookup = self.actions.ollama_models
    self.ollama_state.setText("Checking Ollama…")
    self._in_background(lambda: lookup(host), self._models_done)

  def _models_done(self, models: list[str] | None, _error: str) -> None:
    combo = self._widgets.get("ollama.model")
    if models is None:
      self.ollama_state.setText("● Ollama is not running — start it to list models.")
      self.ollama_state.setStyleSheet(f"color: {t.STATUS_OFFLINE};")
      return
    self.ollama_state.setText(f"● Ollama running · {len(models)} model(s) installed")
    self.ollama_state.setStyleSheet(f"color: {t.STATUS_READY};")
    if isinstance(combo, QComboBox):
      current = self.config.get("ollama.model")
      combo.blockSignals(True)
      combo.clear()
      for name in models:
        combo.addItem(name, name)
      self._select(combo, current)
      combo.blockSignals(False)

  # --- Developer ------------------------------------------------------------------------------

  def _developer_tools(self) -> QWidget:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    buttons = QHBoxLayout()

    def add(text: str, handler) -> None:
      btn = QPushButton(text)
      btn.setObjectName("GhostButton")
      btn.clicked.connect(handler)
      buttons.addWidget(btn)

    add("Open settings file", lambda: self._open(self.config.path))
    if self.actions.data_dir is not None:
      add("Open data folder", lambda: self._open(self.actions.data_dir))
    if self.actions.logs_dir is not None:
      add("Open logs", lambda: self._open(self.actions.logs_dir))
    if self.actions.send_test_notification is not None:
      add("Test notification", self._test_notification)
    add("Reset all settings", self._reset_all)
    buttons.addStretch(1)
    layout.addLayout(buttons)
    self.dev_state = _muted("")
    self.dev_state.hide()
    layout.addWidget(self.dev_state)

    if self.actions.diagnostics is not None:
      self.diagnostics = QPlainTextEdit()
      self.diagnostics.setReadOnly(True)
      self.diagnostics.setMaximumHeight(200)
      layout.addWidget(_muted("Diagnostics"))
      layout.addWidget(self.diagnostics)
      refresh = QPushButton("Refresh diagnostics")
      refresh.setObjectName("GhostButton")
      refresh.clicked.connect(self._refresh_diagnostics)
      layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
      self._refresh_diagnostics()
    return card

  def _test_notification(self) -> None:
    try:
      message = self.actions.send_test_notification() or "Test notification sent."
    except Exception as exc:  # noqa: BLE001
      message = f"Test notification failed: {exc}"
    self.dev_state.setText(message)
    self.dev_state.show()

  def _refresh_diagnostics(self) -> None:
    self.diagnostics.setPlainText("Collecting…")
    self._in_background(self.actions.diagnostics, self._diagnostics_done)

  def _diagnostics_done(self, lines: list[str] | None, error: str) -> None:
    if error:
      self.diagnostics.setPlainText(f"Diagnostics unavailable: {error}")
    else:
      self.diagnostics.setPlainText("\n".join(lines or []))

  @staticmethod
  def _open(path: Path) -> None:
    target = Path(path)
    if not target.exists():
      if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
      else:
        target.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

  def _reset_all(self) -> None:
    answer = QMessageBox.question(self, "Reset settings", "Reset every setting to its default?")
    if answer != QMessageBox.StandardButton.Yes:
      return
    for path in [f.path for key, _ in CATEGORIES for f in fields_for(key)] + ["voice.tts_lang"]:
      self.config.reset(path)
    self.restart_bar.show()
    self.reload_values()

  def reload_values(self) -> None:
    """Refresh every control from the saved config (after a reset)."""
    for key, _ in CATEGORIES:
      for f in fields_for(key):
        widget = self._widgets.get(f.path)
        value = self.config.get(f.path)
        if widget is None:
          continue
        widget.blockSignals(True)
        if isinstance(widget, ToggleSwitch):
          widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
          self._select(widget, value)
        elif isinstance(widget, QSpinBox):
          widget.setValue(int(value))
        elif isinstance(widget, QDoubleSpinBox):
          widget.setValue(float(value))
        elif isinstance(widget, QTimeEdit):
          widget.setTime(QTime.fromString(str(value), "H:mm"))
        elif isinstance(widget, QLineEdit):
          widget.setText(str(value or ""))
        elif hasattr(widget, "line_edit"):
          widget.line_edit.setText(str(value or ""))
        widget.blockSignals(False)
    self._refresh_visibility()
    self._refresh_install_state()

  # --- System status ---------------------------------------------------------------------------

  def _status_panel(self) -> QWidget:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    self._status_rows = QVBoxLayout()
    self._status_rows.setSpacing(8)
    layout.addLayout(self._status_rows)
    refresh = QPushButton("Refresh")
    refresh.setObjectName("GhostButton")
    refresh.clicked.connect(self.refresh_status)
    layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
    return card

  def refresh_status(self) -> None:
    """Checks run in the background: an Ollama check can take a few seconds."""
    if self.actions.status is None or not hasattr(self, "_status_rows") or self._status_busy:
      return
    self._status_busy = True
    self._show_status_rows([("Checking", True, "…")])
    self._in_background(self.actions.status, self._status_done)

  def _status_done(self, rows: list, error: str) -> None:
    self._status_busy = False
    self._show_status_rows(rows or [] if not error else [("Status", False, error)])

  def _show_status_rows(self, rows: list) -> None:
    while self._status_rows.count():
      item = self._status_rows.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    for name, ok, detail in rows:
      line = QLabel(f"{'●'}  {name} — {detail}")
      line.setWordWrap(True)
      line.setStyleSheet(f"color: {t.STATUS_READY if ok else t.STATUS_WARN};")
      self._status_rows.addWidget(line)
