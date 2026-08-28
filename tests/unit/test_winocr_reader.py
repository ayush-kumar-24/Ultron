"""winocr result parsing — the adapter must handle both result shapes.

winocr returns a plain dict on current builds and a WinRT object on older ones.
An earlier version of this adapter used getattr() only, so the dict shape read as
empty text with no error at all.
"""

from __future__ import annotations

from maira.infrastructure.screen.winocr_reader import (
  _lines_from_result,
  _text_from_result,
)


class _Line:
  def __init__(self, text: str) -> None:
    self.text = text


class _Result:
  def __init__(self, text: str, lines: list[_Line]) -> None:
    self.text = text
    self.lines = lines


DICT_RESULT = {
  "text": "KeyError: alembic_version Build failed",
  "lines": [
    {"text": "KeyError: alembic_version", "words": []},
    {"text": "Build failed", "words": []},
  ],
  "text_angle": None,
}


def test_reads_dict_shape() -> None:
  assert _text_from_result(DICT_RESULT) == "KeyError: alembic_version Build failed"
  assert _lines_from_result(DICT_RESULT) == ("KeyError: alembic_version", "Build failed")


def test_reads_object_shape() -> None:
  result = _Result("one two", [_Line("one"), _Line("two")])
  assert _text_from_result(result) == "one two"
  assert _lines_from_result(result) == ("one", "two")


def test_blank_lines_are_dropped() -> None:
  result = {"text": "a", "lines": [{"text": "a"}, {"text": "   "}, {"text": ""}]}
  assert _lines_from_result(result) == ("a",)


def test_missing_fields_are_safe() -> None:
  assert _text_from_result({}) == ""
  assert _lines_from_result({}) == ()
  assert _text_from_result(object()) == ""
  assert _lines_from_result(object()) == ()


def test_none_text_is_safe() -> None:
  assert _text_from_result({"text": None}) == ""
  assert _lines_from_result({"lines": [{"text": None}]}) == ()
