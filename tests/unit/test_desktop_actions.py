"""Unit tests for desktop intent + controller (mocked OS/input)."""

from __future__ import annotations

from maira.core.interfaces.desktop import DesktopStep
from maira.modules.desktop_controller.intent import parse_desktop_request
from maira.modules.desktop_controller.service import DesktopControllerService


def test_parse_open_youtube_for_me_and_play() -> None:
  parsed = parse_desktop_request(
    "open YouTube for me and play Teri Deewani from Rockstar"
  )
  assert parsed is not None
  assert parsed.steps[0].kind == "open_url"
  assert "youtube.com" in parsed.steps[0].args["url"]


def test_refuse_llm_prose_as_app() -> None:
  from maira.infrastructure.os.platform import is_safe_launch_target

  assert not is_safe_launch_target(
    "YouTube for me and play Teri Deewani from Rockstar. I'll make sure to skip any ads"
  )
  assert is_safe_launch_target("notepad")

  parsed = parse_desktop_request("open youtube and play teri deewani")
  assert parsed is not None
  assert parsed.steps[0].kind == "open_url"
  url = parsed.steps[0].args["url"]
  assert "youtube.com" in url
  assert "/watch?v=" in url or "search_query=" in url


def test_resolve_youtube_play_url_returns_watch_or_search() -> None:
  from maira.modules.desktop_controller.youtube import resolve_youtube_play_url

  url = resolve_youtube_play_url("teri deewani")
  assert "youtube.com" in url
  # Prefer direct watch; search fallback still acceptable offline/blocked.
  assert "/watch?v=" in url or "search_query=" in url


def test_parse_play_on_youtube() -> None:
  parsed = parse_desktop_request("play teri deewani on youtube")
  assert parsed is not None
  url = parsed.steps[0].args["url"]
  assert "youtube.com" in url
  assert "/watch?v=" in url or "search_query=" in url


def test_parse_open_youtube_incomplete() -> None:
  parsed = parse_desktop_request("open youtube and")
  assert parsed is not None
  assert parsed.steps == ()
  assert "Poora" in parsed.confirmation or "command" in parsed.confirmation.lower()


def test_parse_open_and_type() -> None:
  parsed = parse_desktop_request('open notepad and type hello world')
  assert parsed is not None
  kinds = [s.kind for s in parsed.steps]
  assert "open_app" in kinds
  assert "type" in kinds
  assert any(s.args.get("text") == "hello world" for s in parsed.steps if s.kind == "type")


def test_parse_hotkey() -> None:
  parsed = parse_desktop_request("press ctrl+s")
  assert parsed is not None
  assert parsed.steps[0].kind == "hotkey"
  assert parsed.steps[0].args["keys"] == ["ctrl", "s"]


def test_parse_click() -> None:
  parsed = parse_desktop_request("click 100, 200")
  assert parsed is not None
  assert parsed.steps[0].args["x"] == 100
  assert parsed.steps[0].args["y"] == 200


def test_schedule_guard_skips_desktop() -> None:
  assert parse_desktop_request("open youtube at 9pm") is None
  assert parse_desktop_request("remind me in 1 minute") is None


def test_controller_disabled() -> None:
  desk = DesktopControllerService(enabled=False, allow_input=True)
  result = desk.open_app("notepad")
  assert result.ok is False


def test_run_steps_mocked(monkeypatch) -> None:
  calls: list[str] = []

  def fake_execute(step: DesktopStep, *, allow_input: bool):
    del allow_input
    calls.append(step.kind)
    from maira.core.interfaces.desktop import DesktopResult

    return DesktopResult(True, step.kind)

  monkeypatch.setattr(
    "maira.modules.desktop_controller.service.execute_step",
    fake_execute,
  )
  desk = DesktopControllerService(enabled=True, allow_input=True)
  result = desk.run_steps(
    [DesktopStep("open_app", {"name": "notepad"}), DesktopStep("type", {"text": "hi"})]
  )
  assert result.ok
  assert calls == ["open_app", "type"]
