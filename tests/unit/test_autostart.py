"""Windows Startup folder launcher — isolated to a temp directory."""

from pathlib import Path

from maira.infrastructure.os.autostart import (
  disable_autostart,
  enable_autostart,
  is_autostart_enabled,
)


def test_enable_and_disable_autostart(tmp_path: Path) -> None:
  root = tmp_path / "ultron"
  root.mkdir()
  python = tmp_path / "python.exe"
  python.write_text("", encoding="utf-8")
  startup = tmp_path / "Startup"

  path = enable_autostart(root, python_exe=python, startup_dir=startup)
  assert path.is_file()
  assert is_autostart_enabled(startup)
  body = path.read_text(encoding="utf-8")
  assert str(root.resolve()) in body
  assert "-m maira" in body

  disable_autostart(startup)
  assert not is_autostart_enabled(startup)
