"""Settings → Agent & actions: folders, Gmail app password, model check."""

from __future__ import annotations

import pytest

from maira.app.user_config import UserConfig
from maira.shared.utils.paths import default_config_path
from maira.ui.prototype.screens.agent_panel import AgentPanel


@pytest.fixture
def panel(qtbot, tmp_path):
  secrets: dict[str, str] = {}
  picks = iter([str(tmp_path / "Projects"), str(tmp_path / "Bills")])
  widget = AgentPanel(
    UserConfig(user_path=tmp_path / "config.yaml", default_path=default_config_path()),
    get_secret=lambda k: secrets.get(k, ""),
    set_secret=lambda k, v: secrets.__setitem__(k, v) if v else secrets.pop(k, None),
    installed_models=lambda: ["qwen3.5:4b", "llama3.2:latest"],
    contacts_path=tmp_path / "contacts.json",
    pick_folder=lambda: next(picks),
  )
  qtbot.addWidget(widget)
  widget.secrets = secrets
  return widget


def _items(panel) -> list[str]:
  return [panel.folders.item(i).text() for i in range(panel.folders.count())]


def test_folders_start_from_defaults_and_save(panel, tmp_path) -> None:
  assert "default folders" in panel.folders_hint.text()
  defaults = _items(panel)
  panel.add_folder()
  assert _items(panel) == [*defaults, str(tmp_path / "Projects")]
  assert panel.config.get("agent.folders")[-1] == str(tmp_path / "Projects")
  for _ in range(len(defaults)):
    panel.folders.setCurrentRow(0)
    panel.remove_folder()
  assert _items(panel) == [str(tmp_path / "Projects")]
  panel.folders.setCurrentRow(0)
  panel.remove_folder()  # the last one stays
  assert _items(panel) == [str(tmp_path / "Projects")] and "at least one" in panel.folders_hint.text()


def test_app_password_is_saved_as_a_secret(panel) -> None:
  assert "Not set" in panel.password_state.text()
  panel.password.setText("short")
  panel.save_password()
  assert panel.secrets == {}
  panel.password.setText("abcd efgh ijkl mnop")
  panel.save_password()
  assert panel.secrets == {"gmail_app_password": "abcdefghijklmnop"} and panel.password.text() == ""
  assert "saved" in panel.password_state.text()
  panel.clear_password()
  assert panel.secrets == {}


def test_model_check(panel) -> None:
  assert "qwen3.5:4b is installed" in panel.model_state.text()
  panel.config.set("agent.model", "gemma4:e4b")
  panel.refresh_model()
  assert "ollama pull gemma4:e4b" in panel.model_state.text()
  panel._installed_models = lambda: None  # noqa: SLF001
  panel.refresh_model()
  assert "Ollama is not running" in panel.model_state.text()
