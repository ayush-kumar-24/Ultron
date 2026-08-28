"""Windows login autostart via the current-user Startup folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SHORTCUT_NAME = "Ultron.cmd"


def default_startup_dir() -> Path:
  appdata = os.environ.get("APPDATA", "")
  if not appdata:
    raise RuntimeError("APPDATA is not set; cannot locate the Windows Startup folder")
  return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def autostart_path(startup_dir: Path | None = None) -> Path:
  return (startup_dir or default_startup_dir()) / SHORTCUT_NAME


def is_autostart_enabled(startup_dir: Path | None = None) -> bool:
  return autostart_path(startup_dir).is_file()


def _launcher_lines(project_root: Path, python_exe: Path) -> str:
  pythonw = python_exe.with_name("pythonw.exe")
  interpreter = pythonw if pythonw.is_file() else python_exe
  root = str(project_root.resolve())
  exe = str(interpreter.resolve())
  return (
    "@echo off\r\n"
    f'cd /d "{root}"\r\n'
    f'start "" "{exe}" -m maira\r\n'
  )


def enable_autostart(
  project_root: Path,
  *,
  python_exe: Path | None = None,
  startup_dir: Path | None = None,
) -> Path:
  target = autostart_path(startup_dir)
  target.parent.mkdir(parents=True, exist_ok=True)
  interpreter = Path(python_exe or sys.executable)
  target.write_text(_launcher_lines(project_root, interpreter), encoding="utf-8")
  return target


def disable_autostart(startup_dir: Path | None = None) -> None:
  path = autostart_path(startup_dir)
  if path.is_file():
    path.unlink()
