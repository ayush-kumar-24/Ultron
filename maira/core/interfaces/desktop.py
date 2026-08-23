"""Desktop controller port — OS-level open / type / click / hotkey."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DesktopResult:
  ok: bool
  message: str
  details: tuple[str, ...] = ()


@dataclass(frozen=True)
class DesktopStep:
  """One atomic desktop action."""

  kind: str  # open_app | open_url | open_path | type | hotkey | press | click | wait | focus
  args: dict[str, Any] = field(default_factory=dict)


class DesktopController(ABC):
  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Whether OS control can run, plus reason."""

  @abstractmethod
  def open_app(self, name_or_path: str) -> DesktopResult:
    ...

  @abstractmethod
  def open_url(self, url: str) -> DesktopResult:
    ...

  @abstractmethod
  def open_path(self, path: str) -> DesktopResult:
    ...

  @abstractmethod
  def type_text(self, text: str, *, interval: float = 0.02) -> DesktopResult:
    ...

  @abstractmethod
  def hotkey(self, *keys: str) -> DesktopResult:
    ...

  @abstractmethod
  def press(self, key: str) -> DesktopResult:
    ...

  @abstractmethod
  def click(
    self,
    x: int | None = None,
    y: int | None = None,
    *,
    button: str = "left",
    clicks: int = 1,
  ) -> DesktopResult:
    ...

  @abstractmethod
  def focus_window(self, title_substr: str) -> DesktopResult:
    ...

  @abstractmethod
  def run_steps(self, steps: list[DesktopStep]) -> DesktopResult:
    """Run a sequenced plan (open → wait → type, etc.)."""
