"""Chat bubbles must show their whole message (no clipped lines)."""

from __future__ import annotations

import pytest

from maira.ui.prototype.screens.chat import ChatBubble, ChatScreen

LONG = (
  'Ho gaya — "drink water" schedule kar diya hai for Wed 23 Sep, 10:58 AM. '
  "Window band kar do toh bhi chalega — Ultron tray mein rehta hai."
)


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_bubble_label_gets_full_text_height(qtbot, role) -> None:
  screen = ChatScreen()
  qtbot.addWidget(screen)
  screen.resize(1400, 900)
  screen.show()
  bubble = screen._add_bubble(role, LONG)  # noqa: SLF001
  qtbot.waitExposed(screen)

  label = bubble.body
  assert label.height() >= label.heightForWidth(label.width())
  assert label.width() <= bubble._max_text_width  # noqa: SLF001
  assert label.height() > label.fontMetrics().height()  # wrapped to 2+ lines


def test_streamed_bubble_grows_with_tokens(qtbot) -> None:
  bubble = ChatBubble("assistant", "")
  qtbot.addWidget(bubble)
  short_height = bubble.body.height()
  for word in LONG.split():
    bubble.append_content(word + " ")
  label = bubble.body
  assert label.height() > short_height
  assert label.height() >= label.heightForWidth(label.width())


def test_short_message_stays_compact(qtbot) -> None:
  bubble = ChatBubble("user", "hi")
  qtbot.addWidget(bubble)
  assert bubble.body.width() < 100
