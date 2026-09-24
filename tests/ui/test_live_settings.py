"""Settings screen: saves to config.yaml, restart bar, voice tools, wiring."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import yaml
from PySide6.QtWidgets import QComboBox, QLineEdit, QMessageBox

from maira.app.settings import load_settings
from maira.app.user_config import UserConfig
from maira.shared.utils.paths import default_config_path
from maira.ui.prototype.screens.live_settings import LiveSettingsScreen, SettingsActions


@pytest.fixture
def config(tmp_path) -> UserConfig:
  return UserConfig(user_path=tmp_path / "config.yaml", default_path=default_config_path())


def _saved(config: UserConfig) -> dict:
  return yaml.safe_load(config.path.read_text(encoding="utf-8")) if config.path.exists() else {}


def _pick(combo: QComboBox, data) -> None:
  """Choose like a user does (editable boxes save on "activated")."""
  index = combo.findData(data)
  combo.setCurrentIndex(index)
  if combo.isEditable():
    combo.activated.emit(index)


def test_changing_voice_engine_saves_and_asks_for_restart(qtbot, config) -> None:
  screen = LiveSettingsScreen(config, SettingsActions(is_voice_installed=lambda p: p == "kokoro"))
  qtbot.addWidget(screen)
  screen.show_category("voice")
  assert screen.restart_bar.isHidden()

  _pick(screen._widgets["voice.tts.provider"], "indic_parler")  # noqa: SLF001

  assert _saved(config)["voice"]["tts"]["provider"] == "indic_parler"
  assert not screen.restart_bar.isHidden()
  # Only the chosen engine's options are shown.
  assert screen._widgets["voice.tts.speaker"].isVisibleTo(screen)  # noqa: SLF001
  assert not screen._widgets["voice.tts.voice"].isVisibleTo(screen)  # noqa: SLF001
  # Not installed yet: the Install button is offered.
  assert "not installed" in screen.install_state.text()
  assert screen.install_btn.isVisibleTo(screen)


def test_saved_values_reach_the_app_settings(qtbot, config, monkeypatch) -> None:
  screen = LiveSettingsScreen(config, SettingsActions())
  qtbot.addWidget(screen)
  _pick(screen._widgets["voice.tts.provider"], "indic_parler")  # noqa: SLF001
  _pick(screen._widgets["voice.tts.speaker"], "Leela")  # noqa: SLF001
  time_edit = screen._widgets["briefing.time"]  # noqa: SLF001
  time_edit.setTime(time_edit.time().fromString("07:30", "HH:mm"))
  time_edit.editingFinished.emit()

  monkeypatch.setattr("maira.app.settings.user_config_path", lambda: config.path)
  settings = load_settings()
  assert settings.voice.tts_provider == "indic_parler"
  assert settings.voice.tts_speaker == "Leela"
  assert settings.briefing.time == "07:30"
  assert '"07:30"' in config.path.read_text(encoding="utf-8")  # quoted, not read back as a number


def test_name_applies_live_without_restart(qtbot, config) -> None:
  names: list = []
  screen = LiveSettingsScreen(config, SettingsActions(live={"briefing.name": names.append}))
  qtbot.addWidget(screen)
  edit = screen._widgets["briefing.name"]  # noqa: SLF001
  assert isinstance(edit, QLineEdit)
  edit.setText("Ayush")
  edit.editingFinished.emit()
  assert names == ["Ayush"]
  assert screen.restart_bar.isHidden()
  edit.editingFinished.emit()  # unchanged: nothing saved again
  assert names == ["Ayush"]


def test_restart_button_calls_the_app(qtbot, config) -> None:
  calls: list = []
  screen = LiveSettingsScreen(config, SettingsActions(restart=lambda: calls.append(1)))
  qtbot.addWidget(screen)
  screen.restart_btn.click()
  assert calls == [1]


def test_reset_all_restores_defaults(qtbot, config, monkeypatch) -> None:
  screen = LiveSettingsScreen(config, SettingsActions())
  qtbot.addWidget(screen)
  _pick(screen._widgets["voice.tts.provider"], "chatterbox")  # noqa: SLF001
  assert _saved(config)["voice"]["tts"]["provider"] == "chatterbox"
  monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
  screen._reset_all()  # noqa: SLF001
  assert not _saved(config)
  default = UserConfig(user_path=config.path.with_name("none.yaml")).get("voice.tts.provider")
  assert screen._widgets["voice.tts.provider"].currentData() == default  # noqa: SLF001


@dataclass
class _Result:
  message: str


def test_preview_runs_in_background_and_reports(qtbot, config) -> None:
  calls: list = []

  def preview(provider, values):
    calls.append((provider, values))
    return _Result("Played 2.0s of audio")

  screen = LiveSettingsScreen(config, SettingsActions(preview_voice=preview))
  qtbot.addWidget(screen)
  screen.preview_text.setText("Namaste")
  screen.preview_btn.click()
  qtbot.waitUntil(lambda: screen.preview_btn.isEnabled(), timeout=3000)
  assert screen.preview_state.text() == "Played 2.0s of audio"
  provider, values = calls[0]
  assert provider == config.get("voice.tts.provider")
  assert values["text"] == "Namaste"


def test_install_streams_log_and_marks_installed(qtbot, config) -> None:
  import sys

  installed = {"done": False}
  screen = LiveSettingsScreen(
    config,
    SettingsActions(
      is_voice_installed=lambda p: installed["done"],
      install_command=lambda p: [sys.executable, "-c", "print('downloading'); print('ok')"],
    ),
  )
  qtbot.addWidget(screen)
  _pick(screen._widgets["voice.tts.provider"], "chatterbox")  # noqa: SLF001
  screen.install_btn.click()
  assert screen.install_btn.text() == "Installing…"
  installed["done"] = True
  qtbot.waitUntil(lambda: screen._install is None, timeout=10000)  # noqa: SLF001
  log = screen.install_log.toPlainText()
  assert "downloading" in log and "Installed" in log
  assert "is installed" in screen.install_state.text()


def test_status_and_models(qtbot, config) -> None:
  screen = LiveSettingsScreen(
    config,
    SettingsActions(
      status=lambda: [("AI (Ollama)", True, "ready"), ("Voice", False, "not installed")],
      ollama_models=lambda host: ["llama3.2:3b", "qwen2.5:7b"],
    ),
  )
  qtbot.addWidget(screen)
  screen.show_category("status")
  qtbot.waitUntil(lambda: not screen._status_busy, timeout=3000)  # noqa: SLF001
  texts = [screen._status_rows.itemAt(i).widget().text() for i in range(screen._status_rows.count())]  # noqa: SLF001
  assert any("AI (Ollama) — ready" in x for x in texts)
  screen.show_category("ai")
  combo = screen._widgets["ollama.model"]  # noqa: SLF001
  qtbot.waitUntil(lambda: combo.findData("qwen2.5:7b") >= 0, timeout=3000)
  assert "2 model(s)" in screen.ollama_state.text()


def test_test_notification_shows_result(qtbot, config) -> None:
  screen = LiveSettingsScreen(config, SettingsActions(send_test_notification=lambda: "Test notification sent (fake)."))
  qtbot.addWidget(screen)
  screen._test_notification()  # noqa: SLF001
  assert screen.dev_state.text() == "Test notification sent (fake)."


def test_window_uses_live_settings_with_backend(qtbot, tmp_path, monkeypatch) -> None:
  """The real app swaps the demo Settings page for the live one."""
  from maira.app.container import Container
  from maira.modules.planner.briefing import BriefingService
  from maira.ui.prototype.integration.settings_actions import build_settings_actions, status_rows
  from maira.ui.prototype.shell.main_window import PrototypeWindow

  monkeypatch.setattr("maira.app.user_config.user_config_path", lambda: tmp_path / "config.yaml")
  window = PrototypeWindow(skip_onboarding=True)
  qtbot.addWidget(window)

  container = Container()
  container.register_instance("settings", load_settings())

  class _Planner:
    def list_tasks(self):
      return []

  briefing = BriefingService(_Planner())
  container.register_instance("briefing", briefing)
  window._install_live_settings(container)  # noqa: SLF001
  live = window.screens["settings"]
  assert isinstance(live, LiveSettingsScreen)
  assert window.stack.indexOf(live) == list(window.screens).index("settings")
  window._run_command("status")  # noqa: SLF001
  assert window.stack.currentWidget() is live

  edit = live._widgets["briefing.name"]  # noqa: SLF001
  edit.setText("Riya")
  edit.editingFinished.emit()
  assert window.store.greeting_name() == "Riya"
  assert briefing.build().text.startswith(("Good morning, Riya", "Good afternoon, Riya", "Good evening, Riya"))

  rows = status_rows(container)  # missing services are reported, not raised
  assert rows[0][0] == "AI (Ollama)" and rows[0][1] is False
  assert build_settings_actions(container).restart is None
