"""Vision facade — capture the screen once and read it.

On demand only. Nothing is captured unless something asks, nothing is written to
disk, and frames never leave the device.
"""

from __future__ import annotations

from loguru import logger

from maira.core.interfaces.screen import (
  Screen,
  ScreenCapture,
  ScreenReader,
  ScreenReading,
  ScreenRegion,
)

MAX_TEXT_CHARS = 4000


class VisionService(Screen):
  def __init__(
    self,
    capture: ScreenCapture,
    reader: ScreenReader,
    *,
    enabled: bool = True,
    bus=None,
    max_text_chars: int = MAX_TEXT_CHARS,
  ) -> None:
    self._capture = capture
    self._reader = reader
    self._enabled = enabled
    self._bus = bus
    self._max_text_chars = max_text_chars

  def set_enabled(self, enabled: bool) -> None:
    self._enabled = enabled

  def is_available(self) -> tuple[bool, str]:
    if not self._enabled:
      return False, "Screen vision disabled in settings"
    ok, why = self._capture.is_available()
    if not ok:
      return False, why
    ok, why = self._reader.is_available()
    if not ok:
      return False, why
    return True, "ready"

  def read_screen(
    self,
    *,
    display: int | None = None,
    region: ScreenRegion | None = None,
  ) -> ScreenReading:
    ok, why = self.is_available()
    if not ok:
      logger.warning("read_screen unavailable: {}", why)
      return ScreenReading(ok=False, summary=why)

    self._publish("screen.reading", {})
    try:
      shot = self._capture.capture(display=display, region=region)
    except Exception as exc:  # noqa: BLE001
      message = f"Could not capture the screen: {exc}"
      logger.error(message)
      self._publish("screen.error", {"message": message})
      return ScreenReading(ok=False, summary=message)

    try:
      found = self._reader.read(shot)
    except Exception as exc:  # noqa: BLE001
      message = f"Could not read the screen: {exc}"
      logger.error(message)
      self._publish("screen.error", {"message": message})
      return ScreenReading(
        ok=False, summary=message, width=shot.width, height=shot.height, display=shot.display
      )

    text = found.text.strip()
    truncated = False
    if len(text) > self._max_text_chars:
      text = text[: self._max_text_chars].rstrip()
      truncated = True

    if found.is_empty():
      summary = f"Nothing readable on display {shot.display} ({shot.width}x{shot.height})."
    else:
      summary = (
        f"Read {len(found.lines) or 1} line(s) from display {shot.display} "
        f"({shot.width}x{shot.height})."
      )

    details: list[str] = []
    if truncated:
      details.append(f"Text truncated to {self._max_text_chars} characters")

    reading = ScreenReading(
      ok=True,
      summary=summary,
      text=text,
      lines=found.lines,
      width=shot.width,
      height=shot.height,
      display=shot.display,
      engine=found.engine,
      details=tuple(details),
    )
    self._publish(
      "screen.read",
      {
        "ok": True,
        "chars": len(text),
        "lines": len(found.lines),
        "display": shot.display,
        "engine": found.engine,
      },
    )
    return reading

  def as_context(self, reading: ScreenReading) -> str:
    """Format a reading for an LLM prompt."""
    if not reading.ok:
      return f"[screen unavailable: {reading.summary}]"
    if not reading.text:
      return "[screen is blank or has no readable text]"
    return f"[what is on screen right now]\n{reading.text}"

  def _publish(self, topic: str, payload: dict) -> None:
    if self._bus is None:
      return
    try:
      self._bus.publish(topic, payload)
    except Exception as exc:  # noqa: BLE001
      logger.debug("Vision event {} not published: {}", topic, exc)
