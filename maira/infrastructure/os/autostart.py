"""Start Ultron when the user signs in to Windows (HKCU Run key)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

from loguru import logger

from maira.shared.utils.paths import project_root

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
BACKGROUND_FLAG = "--background"


class RunKeyStore(Protocol):
  def get(self, name: str) -> str | None: ...
  def set(self, name: str, value: str) -> None: ...
  def delete(self, name: str) -> None: ...


class WindowsRunKey:
  """HKCU Run key — per-user, no admin rights needed."""

  def get(self, name: str) -> str | None:
    import winreg  # noqa: PLC0415

    try:
      with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        value, _ = winreg.QueryValueEx(key, name)
        return str(value)
    except FileNotFoundError:
      return None

  def set(self, name: str, value: str) -> None:
    import winreg  # noqa: PLC0415

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
      winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

  def delete(self, name: str) -> None:
    import winreg  # noqa: PLC0415

    try:
      with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, name)
    except FileNotFoundError:
      pass


def windowless_python(executable: str) -> str:
  """Prefer pythonw.exe so no console window opens at sign-in."""
  path = Path(executable)
  if path.name.lower() == "python.exe":
    candidate = path.with_name("pythonw.exe")
    if candidate.exists():
      return str(candidate)
  return str(path)


def build_launch_command(executable: str | None = None, launcher: Path | None = None) -> str:
  python = windowless_python(executable or sys.executable)
  script = launcher or project_root() / "ultron.pyw"
  return f'"{python}" "{script}" {BACKGROUND_FLAG}'


class AutostartManager:
  def __init__(
    self,
    app_name: str = "Ultron",
    *,
    command: str | None = None,
    store: RunKeyStore | None = None,
    supported: bool | None = None,
  ) -> None:
    self._name = app_name
    self._command = command or build_launch_command()
    self._supported = (os.name == "nt") if supported is None else supported
    self._store = store if store is not None else (WindowsRunKey() if self._supported else None)

  def is_supported(self) -> bool:
    return self._supported and self._store is not None

  def is_enabled(self) -> bool:
    if not self.is_supported():
      return False
    return self._store.get(self._name) is not None

  def set_enabled(self, enabled: bool) -> bool:
    """Turn start-at-sign-in on or off. Returns the resulting state."""
    if not self.is_supported():
      return False
    try:
      if enabled:
        self._store.set(self._name, self._command)
        logger.info("Start with Windows enabled: {}", self._command)
      else:
        self._store.delete(self._name)
        logger.info("Start with Windows disabled")
    except OSError:
      logger.exception("Could not update Start with Windows")
    return self.is_enabled()

  def refresh(self) -> None:
    """Rewrite the entry if the project or Python moved since it was enabled."""
    if not self.is_supported():
      return
    current = self._store.get(self._name)
    if current is not None and current != self._command:
      try:
        self._store.set(self._name, self._command)
        logger.info("Start with Windows path updated")
      except OSError:
        logger.exception("Could not refresh Start with Windows")
