"""Recognise a request to look at the screen.

Deliberately narrow: the user must be pointing at the screen. Anything vaguer
should reach the LLM instead of silently taking a screenshot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "screen" alone is too loose (screen recording, screen time), so every pattern
# pairs a look-verb with a screen/display noun, or names a screen-bound object.
_SCREEN_NOUN = r"(?:my\s+|the\s+|this\s+)?(?:screen|display|monitor|desktop)"
_LOOK_VERB = r"(?:look\s+at|see|read|check|scan|analyse|analyze|describe|what'?s\s+on)"

_PATTERNS = (
  # look at / read / what's on my screen
  re.compile(rf"(?i)\b{_LOOK_VERB}\s+{_SCREEN_NOUN}\b"),
  # can you see my screen / are you seeing my screen
  re.compile(rf"(?i)\b(?:can|could)\s+you\s+see\s+{_SCREEN_NOUN}\b"),
  # take a screenshot / capture the screen
  re.compile(r"(?i)\b(?:take|grab|capture)\s+a?\s*(?:screenshot|screen\s?grab)\b"),
  re.compile(rf"(?i)\bcapture\s+{_SCREEN_NOUN}\b"),
  # what does this error say / read this error
  re.compile(r"(?i)\b(?:what\s+does\s+)?this\s+(?:error|message|dialog|popup|window)\b"),
  # what am I looking at
  re.compile(r"(?i)\bwhat\s+am\s+i\s+looking\s+at\b"),
)

# Recording and continuous watching are separate capabilities — never claim them here.
_NOT_VISION = re.compile(
  r"(?i)\b(record|recording|keep\s+watching|watch\s+continuously|monitor\s+me|"
  r"screen\s+time|share\s+(?:my\s+)?screen)\b"
)


@dataclass(frozen=True)
class VisionRequest:
  """A recognised ask to look at the screen."""

  matched: bool
  question: str = ""

  def __bool__(self) -> bool:
    return self.matched


def parse_vision_request(text: str) -> VisionRequest:
  """Return a matched VisionRequest when the user is asking Ultron to look."""
  cleaned = (text or "").strip()
  if not cleaned:
    return VisionRequest(False)
  if _NOT_VISION.search(cleaned):
    return VisionRequest(False)
  for pattern in _PATTERNS:
    if pattern.search(cleaned):
      return VisionRequest(True, question=cleaned)
  return VisionRequest(False)
