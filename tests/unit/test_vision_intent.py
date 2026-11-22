"""Screen-look intent parsing — narrow on purpose, no capture involved."""

import pytest

from maira.modules.vision.intent import parse_vision_request


@pytest.mark.parametrize(
  "text",
  [
    "what's on my screen?",
    "What's on the screen right now",
    "look at my screen",
    "read my screen",
    "can you see my screen?",
    "check the display",
    "describe my desktop",
    "take a screenshot",
    "grab a screenshot for me",
    "capture the screen",
    "what does this error say?",
    "read this error",
    "what am I looking at",
  ],
)
def test_recognises_a_look_request(text: str) -> None:
  assert parse_vision_request(text)


@pytest.mark.parametrize(
  "text",
  [
    "",
    "   ",
    "open notepad",
    "remind me at 9am to review the roadmap",
    "how much screen time did I have",
    "start recording my screen",
    "keep watching my screen",
    "share my screen on the call",
    "what is the capital of France",
  ],
)
def test_ignores_everything_else(text: str) -> None:
  assert not parse_vision_request(text)


def test_keeps_the_original_question() -> None:
  request = parse_vision_request("what does this error say?")
  assert request.matched
  assert request.question == "what does this error say?"


def test_recording_is_not_vision() -> None:
  """Recording is a separate capability; the look path must never claim it."""
  assert not parse_vision_request("record my screen and tell me what happens")
