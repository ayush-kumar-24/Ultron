"""VisionService behaviour with fake capture/OCR adapters — no real screen touched."""

from __future__ import annotations

import pytest

from maira.core.interfaces.screen import (
  ScreenCapture,
  ScreenReader,
  ScreenRegion,
  ScreenShot,
  ScreenText,
)
from maira.modules.vision.service import VisionService

REGION = ScreenRegion(left=0, top=0, width=1920, height=1080)


class FakeCapture(ScreenCapture):
  def __init__(self, *, available: bool = True, raises: Exception | None = None) -> None:
    self._available = available
    self._raises = raises
    self.calls: list[tuple[int | None, ScreenRegion | None]] = []

  def is_available(self) -> tuple[bool, str]:
    return (True, "ready") if self._available else (False, "mss unavailable")

  def displays(self):
    return []

  def capture(self, *, display=None, region=None) -> ScreenShot:
    self.calls.append((display, region))
    if self._raises is not None:
      raise self._raises
    return ScreenShot(png=b"PNG", width=1920, height=1080, region=REGION, display=1)


class FakeReader(ScreenReader):
  def __init__(self, text: str = "", *, available: bool = True, raises: Exception | None = None) -> None:
    self._text = text
    self._available = available
    self._raises = raises

  def is_available(self) -> tuple[bool, str]:
    return (True, "ready") if self._available else (False, "winocr unavailable")

  def read(self, shot: ScreenShot) -> ScreenText:
    if self._raises is not None:
      raise self._raises
    lines = tuple(l for l in self._text.split("\n") if l.strip())
    return ScreenText(text=self._text, lines=lines, region=shot.region, display=shot.display, engine="fake")


class RecordingBus:
  def __init__(self) -> None:
    self.events: list[tuple[str, dict]] = []

  def publish(self, topic: str, payload: dict) -> None:
    self.events.append((topic, payload))


def test_reads_text_from_the_screen() -> None:
  service = VisionService(FakeCapture(), FakeReader("Traceback\nKeyError: 'id'"))
  reading = service.read_screen()
  assert reading.ok
  assert "KeyError" in reading.text
  assert reading.lines == ("Traceback", "KeyError: 'id'")
  assert reading.width == 1920
  assert reading.engine == "fake"


def test_disabled_never_captures() -> None:
  capture = FakeCapture()
  service = VisionService(capture, FakeReader("hi"), enabled=False)
  reading = service.read_screen()
  assert not reading.ok
  assert "disabled" in reading.summary.lower()
  assert capture.calls == []


def test_unavailable_capture_reports_why_and_does_not_raise() -> None:
  service = VisionService(FakeCapture(available=False), FakeReader("hi"))
  reading = service.read_screen()
  assert not reading.ok
  assert "mss unavailable" in reading.summary


def test_unavailable_ocr_reports_why() -> None:
  service = VisionService(FakeCapture(), FakeReader(available=False))
  ok, why = service.is_available()
  assert not ok
  assert "winocr unavailable" in why


def test_capture_failure_is_handled() -> None:
  service = VisionService(FakeCapture(raises=RuntimeError("no display")), FakeReader("hi"))
  reading = service.read_screen()
  assert not reading.ok
  assert "no display" in reading.summary


def test_ocr_failure_is_handled() -> None:
  service = VisionService(FakeCapture(), FakeReader(raises=RuntimeError("ocr blew up")))
  reading = service.read_screen()
  assert not reading.ok
  assert "ocr blew up" in reading.summary


def test_blank_screen_is_ok_but_empty() -> None:
  service = VisionService(FakeCapture(), FakeReader("   "))
  reading = service.read_screen()
  assert reading.ok
  assert reading.text == ""
  assert "nothing readable" in reading.summary.lower()


def test_long_text_is_truncated() -> None:
  service = VisionService(FakeCapture(), FakeReader("x" * 9000), max_text_chars=100)
  reading = service.read_screen()
  assert len(reading.text) == 100
  assert any("truncated" in d.lower() for d in reading.details)


def test_region_is_passed_through() -> None:
  capture = FakeCapture()
  service = VisionService(capture, FakeReader("hi"))
  region = ScreenRegion(left=10, top=20, width=100, height=50)
  service.read_screen(display=2, region=region)
  assert capture.calls == [(2, region)]


def test_publishes_lifecycle_events() -> None:
  bus = RecordingBus()
  service = VisionService(FakeCapture(), FakeReader("hello"), bus=bus)
  service.read_screen()
  topics = [t for t, _ in bus.events]
  assert topics == ["screen.reading", "screen.read"]
  assert bus.events[-1][1]["ok"] is True


def test_publishes_error_event_on_failure() -> None:
  bus = RecordingBus()
  service = VisionService(FakeCapture(raises=RuntimeError("boom")), FakeReader(), bus=bus)
  service.read_screen()
  assert [t for t, _ in bus.events] == ["screen.reading", "screen.error"]


def test_as_context_formats_for_the_prompt() -> None:
  service = VisionService(FakeCapture(), FakeReader("Build failed"))
  reading = service.read_screen()
  block = service.as_context(reading)
  assert "what is on screen" in block
  assert "Build failed" in block


def test_as_context_explains_an_unavailable_screen() -> None:
  service = VisionService(FakeCapture(available=False), FakeReader())
  block = service.as_context(service.read_screen())
  assert block.startswith("[screen unavailable")


def test_a_bus_that_throws_does_not_break_the_read() -> None:
  class BadBus:
    def publish(self, topic, payload):
      raise RuntimeError("bus down")

  service = VisionService(FakeCapture(), FakeReader("fine"), bus=BadBus())
  assert service.read_screen().ok
