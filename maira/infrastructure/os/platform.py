"""Windows OS helpers for launching apps/paths and focusing windows."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path

from loguru import logger

# Friendly name → launch target (exe, shell command, or startfile path).
KNOWN_APPS: dict[str, str] = {
  "notepad": "notepad.exe",
  "calculator": "calc.exe",
  "calc": "calc.exe",
  "paint": "mspaint.exe",
  "explorer": "explorer.exe",
  "file explorer": "explorer.exe",
  "cmd": "cmd.exe",
  "terminal": "wt.exe",
  "powershell": "powershell.exe",
  "chrome": "chrome",
  "edge": "msedge",
  "firefox": "firefox",
  "vscode": "code",
  "vs code": "code",
  "code": "code",
  "spotify": "spotify",
  "word": "winword",
  "excel": "excel",
  "settings": "ms-settings:",
}


def resolve_app(name_or_path: str) -> str:
  raw = (name_or_path or "").strip().strip('"')
  lower = raw.lower()
  if lower in KNOWN_APPS:
    return KNOWN_APPS[lower]
  if lower.endswith(".exe") and lower[:-4] in KNOWN_APPS:
    return KNOWN_APPS[lower[:-4]]
  return raw


def is_safe_launch_target(name_or_path: str) -> bool:
  """Refuse LLM prose / long sentences that must never hit os.startfile."""
  raw = (name_or_path or "").strip().strip('"')
  if not raw:
    return False
  lower = raw.lower()
  if lower in KNOWN_APPS or (lower.endswith(".exe") and lower[:-4] in KNOWN_APPS):
    return True
  if raw.startswith("ms-"):
    return True
  path = Path(raw).expanduser()
  if path.exists():
    return True
  # Bare executable name on PATH (chrome, code, …)
  if " " not in raw and len(raw) <= 64 and shutil.which(raw):
    return True
  # Single token like notepad.exe
  if re.match(r"^[\w.-]+$", raw) and len(raw) <= 64:
    return True
  return False


def launch_app(name_or_path: str) -> str:
  if not is_safe_launch_target(name_or_path):
    raise ValueError(
      f"Not a valid app name: {name_or_path[:80]!r}. "
      "Try: open notepad · play teri deewani · open youtube"
    )
  target = resolve_app(name_or_path)
  if target.startswith("ms-"):
    if os.name == "nt":
      os.startfile(target)  # type: ignore[attr-defined]
    return target

  which = shutil.which(target)
  if which:
    subprocess.Popen([which], shell=False)  # noqa: S603
    return which

  if os.name == "nt":
    try:
      os.startfile(target)  # type: ignore[attr-defined]
      return target
    except OSError as exc:
      raise ValueError(f"Could not launch {target!r}: {exc}") from exc

  subprocess.Popen([target], shell=False)  # noqa: S603
  return target


def open_url(url: str) -> str:
  cleaned = url.strip()
  if not cleaned.startswith(("http://", "https://", "file:")):
    cleaned = "https://" + cleaned
  webbrowser.open(cleaned)
  return cleaned


def open_path(path: str) -> str:
  p = Path(path).expanduser()
  if os.name == "nt":
    os.startfile(str(p))  # type: ignore[attr-defined]
  else:
    subprocess.Popen(["xdg-open", str(p)], shell=False)  # noqa: S603
  return str(p)


def focus_window_windows(title_substr: str, *, timeout_s: float = 3.0) -> bool:
  """Bring a window whose title contains title_substr to the foreground."""
  if os.name != "nt":
    return False
  try:
    import ctypes
    from ctypes import wintypes
  except Exception:  # noqa: BLE001
    return False

  user32 = ctypes.windll.user32  # type: ignore[attr-defined]
  needle = title_substr.lower()
  found: list[int] = []

  @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
  def _enum(hwnd, _lparam):  # type: ignore[misc]
    if not user32.IsWindowVisible(hwnd):
      return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
      return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    if needle in buf.value.lower():
      found.append(hwnd)
      return False
    return True

  deadline = time.time() + timeout_s
  while time.time() < deadline:
    found.clear()
    user32.EnumWindows(_enum, 0)
    if found:
      hwnd = found[0]
      user32.ShowWindow(hwnd, 9)  # SW_RESTORE
      user32.SetForegroundWindow(hwnd)
      logger.debug("Focused window matching {!r}", title_substr)
      return True
    time.sleep(0.2)
  return False
