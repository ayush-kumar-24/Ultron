"""Structured desktop actions used by DesktopControllerService."""

from __future__ import annotations

import time

from maira.core.interfaces.desktop import DesktopResult, DesktopStep
from maira.infrastructure.automation.pyautogui import driver as input_driver
from maira.infrastructure.os import platform as os_platform


def execute_step(step: DesktopStep, *, allow_input: bool) -> DesktopResult:
  kind = step.kind
  args = step.args or {}

  if kind == "wait":
    time.sleep(float(args.get("seconds", 0.5)))
    return DesktopResult(True, f"Waited {args.get('seconds', 0.5)}s")

  if kind == "open_app":
    name = str(args.get("name") or "")
    try:
      launched = os_platform.launch_app(name)
    except ValueError as exc:
      return DesktopResult(False, str(exc))
    return DesktopResult(True, f"Launched {launched}")

  if kind == "open_url":
    url = os_platform.open_url(str(args.get("url") or ""))
    return DesktopResult(True, f"Opened {url}")

  if kind == "open_path":
    path = os_platform.open_path(str(args.get("path") or ""))
    return DesktopResult(True, f"Opened {path}")

  if kind == "focus":
    title = str(args.get("title") or "")
    ok = os_platform.focus_window_windows(title)
    if ok:
      return DesktopResult(True, f"Focused window matching '{title}'")
    return DesktopResult(True, f"Could not focus '{title}' — typing into active window")

  if kind in {"type", "hotkey", "press", "click"}:
    if not allow_input:
      return DesktopResult(False, "Desktop input is disabled in settings")
    ok, reason = input_driver.is_available()
    if not ok:
      return DesktopResult(False, reason)

  if kind == "type":
    text = str(args.get("text") or "")
    input_driver.type_text(text, interval=float(args.get("interval", 0.02)))
    return DesktopResult(True, f"Typed {len(text)} characters")

  if kind == "hotkey":
    keys = args.get("keys") or []
    if isinstance(keys, str):
      keys = [k.strip() for k in keys.split("+") if k.strip()]
    input_driver.hotkey(*list(keys))
    return DesktopResult(True, f"Hotkey {'+'.join(keys)}")

  if kind == "press":
    key = str(args.get("key") or "")
    input_driver.press(key)
    return DesktopResult(True, f"Pressed {key}")

  if kind == "click":
    input_driver.click(
      args.get("x"),
      args.get("y"),
      button=str(args.get("button") or "left"),
      clicks=int(args.get("clicks") or 1),
    )
    return DesktopResult(True, "Clicked")

  return DesktopResult(False, f"Unknown desktop step: {kind}")
