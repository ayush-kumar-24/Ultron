"""Unit tests for Start with Windows (Run key) management."""

from __future__ import annotations

from pathlib import Path

from maira.infrastructure.os.autostart import (
  AutostartManager,
  build_launch_command,
  windowless_python,
)


class FakeRunKey:
  def __init__(self, fail: bool = False) -> None:
    self.values: dict[str, str] = {}
    self.fail = fail

  def get(self, name: str) -> str | None:
    return self.values.get(name)

  def set(self, name: str, value: str) -> None:
    if self.fail:
      raise PermissionError("denied")
    self.values[name] = value

  def delete(self, name: str) -> None:
    self.values.pop(name, None)


def _manager(store: FakeRunKey, command: str = "cmd --background") -> AutostartManager:
  return AutostartManager("Ultron", command=command, store=store, supported=True)


def test_enable_and_disable() -> None:
  store = FakeRunKey()
  manager = _manager(store)
  assert not manager.is_enabled()

  assert manager.set_enabled(True) is True
  assert store.values == {"Ultron": "cmd --background"}

  assert manager.set_enabled(False) is False
  assert store.values == {}


def test_disable_when_missing_is_safe() -> None:
  manager = _manager(FakeRunKey())
  assert manager.set_enabled(False) is False


def test_failed_write_reports_real_state() -> None:
  manager = _manager(FakeRunKey(fail=True))
  assert manager.set_enabled(True) is False


def test_refresh_rewrites_moved_command() -> None:
  store = FakeRunKey()
  store.values["Ultron"] = "old --background"
  _manager(store, command="new --background").refresh()
  assert store.values["Ultron"] == "new --background"


def test_refresh_does_not_enable_when_off() -> None:
  store = FakeRunKey()
  _manager(store).refresh()
  assert store.values == {}


def test_unsupported_platform_is_noop() -> None:
  manager = AutostartManager("Ultron", command="x", store=None, supported=False)
  assert not manager.is_supported()
  assert not manager.is_enabled()
  assert manager.set_enabled(True) is False


def test_launch_command_quotes_paths_and_runs_in_background(tmp_path) -> None:
  python = tmp_path / "My Python" / "python.exe"
  python.parent.mkdir()
  python.touch()
  (python.parent / "pythonw.exe").touch()
  launcher = tmp_path / "Ultron App" / "ultron.pyw"

  command = build_launch_command(str(python), launcher)

  assert command == f'"{python.parent / "pythonw.exe"}" "{launcher}" --background'


def test_windowless_python_keeps_path_when_no_pythonw(tmp_path) -> None:
  python = tmp_path / "python.exe"
  python.touch()
  assert windowless_python(str(python)) == str(python)
  assert windowless_python("/usr/bin/python3") == str(Path("/usr/bin/python3"))


def test_launcher_script_exists() -> None:
  from maira.shared.utils.paths import project_root

  assert (project_root() / "ultron.pyw").is_file()
