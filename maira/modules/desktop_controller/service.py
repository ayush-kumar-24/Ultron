"""Desktop controller facade — open apps/URLs and simulate input."""

from __future__ import annotations

from loguru import logger

from maira.core.interfaces.desktop import DesktopController, DesktopResult, DesktopStep
from maira.infrastructure.automation.pyautogui import driver as input_driver
from maira.modules.desktop_controller.actions import execute_step


class DesktopControllerService(DesktopController):
  def __init__(
    self,
    *,
    enabled: bool = True,
    allow_input: bool = True,
  ) -> None:
    self._enabled = enabled
    self._allow_input = allow_input

  def is_available(self) -> tuple[bool, str]:
    if not self._enabled:
      return False, "Desktop control disabled in settings"
    # Open app/url works without pyautogui; input needs it.
    return True, "ready"

  def set_enabled(self, enabled: bool) -> None:
    self._enabled = enabled

  def set_allow_input(self, allow: bool) -> None:
    self._allow_input = allow

  def open_app(self, name_or_path: str) -> DesktopResult:
    return self.run_steps([DesktopStep("open_app", {"name": name_or_path})])

  def open_url(self, url: str) -> DesktopResult:
    return self.run_steps([DesktopStep("open_url", {"url": url})])

  def open_path(self, path: str) -> DesktopResult:
    return self.run_steps([DesktopStep("open_path", {"path": path})])

  def type_text(self, text: str, *, interval: float = 0.02) -> DesktopResult:
    return self.run_steps([DesktopStep("type", {"text": text, "interval": interval})])

  def hotkey(self, *keys: str) -> DesktopResult:
    return self.run_steps([DesktopStep("hotkey", {"keys": list(keys)})])

  def press(self, key: str) -> DesktopResult:
    return self.run_steps([DesktopStep("press", {"key": key})])

  def click(
    self,
    x: int | None = None,
    y: int | None = None,
    *,
    button: str = "left",
    clicks: int = 1,
  ) -> DesktopResult:
    return self.run_steps(
      [DesktopStep("click", {"x": x, "y": y, "button": button, "clicks": clicks})]
    )

  def focus_window(self, title_substr: str) -> DesktopResult:
    return self.run_steps([DesktopStep("focus", {"title": title_substr})])

  def input_available(self) -> tuple[bool, str]:
    if not self._allow_input:
      return False, "Desktop input disabled"
    return input_driver.is_available()

  def run_steps(self, steps: list[DesktopStep]) -> DesktopResult:
    if not self._enabled:
      return DesktopResult(False, "Desktop control is disabled in settings")
    if not steps:
      return DesktopResult(False, "No desktop steps")

    details: list[str] = []
    for step in steps:
      logger.info("[MAIRA DESKTOP] step={} args={}", step.kind, step.args)
      result = execute_step(step, allow_input=self._allow_input)
      details.append(result.message)
      if not result.ok:
        return DesktopResult(False, result.message, tuple(details))
    return DesktopResult(True, details[-1] if details else "Done", tuple(details))
