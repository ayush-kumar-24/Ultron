"""Screen port — capture what is on the display and read it as text.

Capture is on demand only. Ultron looks when a task needs it; it never watches
continuously (Product Vision 16). Frames stay on the device.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScreenRegion:
  """A rectangle in virtual-desktop pixels."""

  left: int
  top: int
  width: int
  height: int

  def is_valid(self) -> bool:
    return self.width > 0 and self.height > 0


@dataclass(frozen=True)
class Display:
  index: int
  region: ScreenRegion
  primary: bool = False


@dataclass(frozen=True)
class ScreenShot:
  """One captured frame. `png` is the encoded image; nothing is written to disk."""

  png: bytes
  width: int
  height: int
  region: ScreenRegion
  display: int = 0

  def is_empty(self) -> bool:
    return not self.png or self.width <= 0 or self.height <= 0


@dataclass(frozen=True)
class ScreenText:
  """Text recognised on screen, plus where it came from."""

  text: str
  lines: tuple[str, ...] = ()
  region: ScreenRegion | None = None
  display: int = 0
  engine: str = ""

  def is_empty(self) -> bool:
    return not self.text.strip()


@dataclass(frozen=True)
class ScreenReading:
  """What `read_screen` gives back: a description Ultron can reason over."""

  ok: bool
  summary: str
  text: str = ""
  lines: tuple[str, ...] = ()
  width: int = 0
  height: int = 0
  display: int = 0
  engine: str = ""
  details: tuple[str, ...] = field(default_factory=tuple)


class ScreenCapture(ABC):
  """Grabs pixels."""

  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Whether capture can run, plus reason."""

  @abstractmethod
  def displays(self) -> list[Display]:
    """Attached displays, primary first when it can be determined."""

  @abstractmethod
  def capture(
    self,
    *,
    display: int | None = None,
    region: ScreenRegion | None = None,
  ) -> ScreenShot:
    """Capture one frame. `region` wins over `display` when both are given."""


class ScreenReader(ABC):
  """Turns pixels into text."""

  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Whether OCR can run, plus reason."""

  @abstractmethod
  def read(self, shot: ScreenShot) -> ScreenText:
    """Recognise text in a captured frame."""


class Screen(ABC):
  """Facade the rest of Ultron talks to."""

  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Whether Ultron can look at the screen, plus reason."""

  @abstractmethod
  def read_screen(
    self,
    *,
    display: int | None = None,
    region: ScreenRegion | None = None,
  ) -> ScreenReading:
    """Look at the screen once and return what is on it."""
