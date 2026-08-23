"""Parse chat into an immediate desktop action plan."""

from __future__ import annotations

import re
from dataclasses import dataclass

from maira.core.interfaces.desktop import DesktopStep
from maira.infrastructure.os.platform import KNOWN_APPS
from maira.modules.automation.parser import _KNOWN_URLS
from maira.modules.desktop_controller.youtube import (
  clean_youtube_query,
  resolve_youtube_play_url,
)

_DESKTOP_HINT = re.compile(
  r"(?i)\b("
  r"open|launch|start|type|click|press|hotkey|hit|play|search|"
  r"notepad|calculator|chrome|edge|youtube|gmail|"
  r"ctrl\+|alt\+|win\+|cmd\+"
  r")\b"
)

# Don't steal schedule requests — those go to automation first.
_SCHEDULE_GUARD = re.compile(
  r"(?i)\b(remind|schedule|automate|in\s+\d+\s*(min|minute|hour)|"
  r"\d+\s*(min|minute)s?\s*(baad|remind)|every\s+day|tomorrow|kal|"
  r"at\s+\d{1,2}(?::\d{2})?\s*(am|pm)?)\b"
)

_OPEN_AND_TYPE = re.compile(
  r"(?i)^\s*(?:please\s+)?(?:open|launch|start)\s+(.+?)\s+and\s+type\s+(.+?)\s*$"
)
# open youtube [for me] and play/search QUERY  (filler words allowed)
_OPEN_YT_PLAY = re.compile(
  r"(?i)^\s*(?:please\s+)?(?:open|launch|start)\s+"
  r"(?:youtube|yt)\b(?:\s+\w+){0,6}?\s+and\s+"
  r"(?:play|search|find|put\s+on|laga(?:o|na)?|chala(?:o|na)?)\s+"
  r"(?:the\s+)?(?:song\s+|video\s+)?(.+?)\s*$"
)
_PLAY_ON_YT = re.compile(
  r"(?i)^\s*(?:please\s+)?"
  r"(?:play|search)\s+(?:the\s+)?(?:song\s+|video\s+)?(.+?)\s+"
  r"(?:on\s+)?(?:youtube|yt)\s*$"
)
_PLAY_YT_FIRST = re.compile(
  r"(?i)^\s*(?:please\s+)?"
  r"(?:youtube|yt)\s+(?:pe\s+|par\s+)?(?:play|search|laga(?:o|na)?|chala(?:o|na)?)\s+"
  r"(?:the\s+)?(?:song\s+|video\s+)?(.+?)\s*$"
)
# Bare: "play teri deewani" / "teri deewani chalao" → YouTube by default
_PLAY_BARE = re.compile(
  r"(?i)^\s*(?:please\s+)?"
  r"(?:play|chala(?:o|na)?|laga(?:o|na)?|baja(?:o|na)?)\s+"
  r"(?:the\s+)?(?:song\s+|video\s+|music\s+|gaana\s+)?(.+?)\s*$"
)
_PLAY_EXCLUDE = re.compile(
  r"(?i)^(a\s+)?(game|store|station|with|along|nice|fair|pause|stop)\b"
)
_OPEN_INCOMPLETE = re.compile(
  r"(?i)^\s*(?:please\s+)?(?:open|launch|start)\s+.+\s+and\s*$"
)
_OPEN_ONLY = re.compile(
  r"(?i)^\s*(?:please\s+)?(?:open|launch|start)\s+(.+?)\s*$"
)
_TYPE_ONLY = re.compile(
  r"(?i)^\s*(?:please\s+)?type\s+(.+?)\s*$"
)
_CLICK = re.compile(
  r"(?i)^\s*(?:please\s+)?click(?:\s+(?:at|on))?\s+(\d+)\s*[,\s]\s*(\d+)\s*$"
)
_HOTKEY = re.compile(
  r"(?i)^\s*(?:please\s+)?(?:press|hit|hotkey)\s+(.+?)\s*$"
)
_URL_RE = re.compile(r"https?://\S+", re.I)


@dataclass(frozen=True)
class ParsedDesktop:
  steps: tuple[DesktopStep, ...]
  confirmation: str


def looks_like_desktop_request(text: str) -> bool:
  cleaned = (text or "").strip()
  if not cleaned or _SCHEDULE_GUARD.search(cleaned):
    return False
  return bool(_DESKTOP_HINT.search(cleaned))


def parse_desktop_request(text: str) -> ParsedDesktop | None:
  cleaned = " ".join((text or "").strip().split())
  if not cleaned or not looks_like_desktop_request(cleaned):
    return None

  if _OPEN_INCOMPLETE.match(cleaned):
    return ParsedDesktop(
      steps=(),
      confirmation="Poora command bhejo — jaise: open youtube and play teri deewani",
    )

  match = _OPEN_AND_TYPE.match(cleaned)
  if match:
    target = match.group(1).strip().strip('"')
    typed = _strip_quotes(match.group(2))
    steps = _open_steps(target)
    if not steps:
      return None
    focus = _focus_hint(target)
    steps.append(DesktopStep("wait", {"seconds": 1.2}))
    if focus:
      steps.append(DesktopStep("focus", {"title": focus}))
      steps.append(DesktopStep("wait", {"seconds": 0.3}))
    steps.append(DesktopStep("type", {"text": typed}))
    return ParsedDesktop(
      steps=tuple(steps),
      confirmation=f"Ho gaya — {target} open karke type kar raha hoon.",
    )

  for pattern in (_OPEN_YT_PLAY, _PLAY_ON_YT, _PLAY_YT_FIRST):
    match = pattern.match(cleaned)
    if match:
      query = _strip_quotes(match.group(1))
      query = re.sub(r"\s+", " ", query).strip(" .,!")
      if not query:
        return ParsedDesktop(
          steps=(),
          confirmation="Kaunsa gaana/video? Jaise: play teri deewani",
        )
      return _youtube_search_plan(query)

  match = _PLAY_BARE.match(cleaned)
  if match:
    query = _strip_quotes(match.group(1))
    query = re.sub(r"\s+", " ", query).strip(" .,!")
    if not query or _PLAY_EXCLUDE.match(query):
      return None
    return _youtube_search_plan(query)

  match = _TYPE_ONLY.match(cleaned)
  if match:
    typed = _strip_quotes(match.group(1))
    return ParsedDesktop(
      steps=(DesktopStep("type", {"text": typed}),),
      confirmation="Typing now — active window pe likh raha hoon.",
    )

  match = _CLICK.match(cleaned)
  if match:
    x, y = int(match.group(1)), int(match.group(2))
    return ParsedDesktop(
      steps=(DesktopStep("click", {"x": x, "y": y}),),
      confirmation=f"Click kar raha hoon at ({x}, {y}).",
    )

  match = _HOTKEY.match(cleaned)
  if match:
    keys = _parse_hotkey(match.group(1))
    if not keys:
      return None
    return ParsedDesktop(
      steps=(DesktopStep("hotkey", {"keys": keys}),),
      confirmation=f"Pressing {'+'.join(keys)}.",
    )

  match = _OPEN_ONLY.match(cleaned)
  if match:
    target = match.group(1).strip().strip('"')
    # Reject LLM prose accidentally sent as an open command
    if re.search(r"(?i)\b(i'?ll|i will|\*opens\*|\*starts\*|make sure to)\b", target):
      # Still try to salvage youtube+play intent inside the prose
      salvage = re.search(
        r"(?i)(?:youtube|yt).{0,40}?\b(?:play|search)\s+(?:the\s+)?(?:song\s+)?"
        r"(.+?)(?:\.|$|\*|#)",
        cleaned,
      )
      if salvage:
        return _youtube_search_plan(_strip_quotes(salvage.group(1)))
      return ParsedDesktop(
        steps=(),
        confirmation="Woh LLM text thi, command nahi. Seedha likho: play teri deewani",
      )
    yt_play = re.match(
      r"(?i)^(youtube|yt)\b(?:\s+\w+){0,6}?\s+and\s+"
      r"(?:play|search|find)\s+(?:the\s+)?(?:song\s+|video\s+)?(.+)$",
      target,
    )
    if yt_play:
      return _youtube_search_plan(_strip_quotes(yt_play.group(2)))
    steps = _open_steps(target)
    if not steps:
      return None
    # Don't confirm "Opening <essay>."
    label = target if len(target) < 40 else target.split()[0]
    return ParsedDesktop(
      steps=tuple(steps),
      confirmation=f"Opening {label}.",
    )

  return None


def _youtube_search_plan(query: str) -> ParsedDesktop:
  wants_skip_ad = bool(
    re.search(r"(?i)\bskip(?:\s+the)?\s+ads?\b|\bad\s*free\b|\bwithout\s+ads?\b", query)
  )
  cleaned = clean_youtube_query(query)
  url = resolve_youtube_play_url(cleaned)
  is_watch = "/watch?v=" in url
  steps: list[DesktopStep] = [DesktopStep("open_url", {"url": url})]
  if is_watch and wants_skip_ad:
    steps.extend(
      [
        DesktopStep("wait", {"seconds": 5.5}),
        DesktopStep("focus", {"title": "youtube"}),
        DesktopStep("hotkey", {"keys": ["tab"]}),
        DesktopStep("press", {"key": "enter"}),
        DesktopStep("wait", {"seconds": 1.0}),
        DesktopStep("hotkey", {"keys": ["tab"]}),
        DesktopStep("press", {"key": "enter"}),
      ]
    )
  if is_watch:
    confirmation = f"Playing \"{cleaned}\" on YouTube."
    if wants_skip_ad:
      confirmation += " Ad skip try karunga."
  else:
    confirmation = (
      f"YouTube pe \"{cleaned}\" search khol diya — pehli video resolve nahi hui."
    )
  return ParsedDesktop(steps=tuple(steps), confirmation=confirmation)


def _open_steps(target: str) -> list[DesktopStep]:
  lower = target.lower().strip()
  url_match = _URL_RE.search(target)
  if url_match:
    return [DesktopStep("open_url", {"url": url_match.group(0).rstrip(".,)")})]

  for name, url in _KNOWN_URLS.items():
    if lower == name:
      return [DesktopStep("open_url", {"url": url})]

  if re.match(r"^[a-zA-Z]:\\", target) or target.startswith("\\\\") or lower.startswith("file "):
    path = re.sub(r"(?i)^file\s+", "", target).strip()
    return [DesktopStep("open_path", {"path": path})]

  for name in KNOWN_APPS:
    if lower == name or lower.startswith(name + " "):
      return [DesktopStep("open_app", {"name": name})]

  # Never launch free-form sentences as apps
  from maira.infrastructure.os.platform import is_safe_launch_target

  if is_safe_launch_target(target):
    return [DesktopStep("open_app", {"name": target})]
  return []


def _focus_hint(target: str) -> str | None:
  lower = target.lower()
  mapping = {
    "notepad": "notepad",
    "calculator": "calculator",
    "calc": "calculator",
    "paint": "paint",
    "cmd": "command prompt",
    "powershell": "powershell",
    "terminal": "terminal",
    "chrome": "chrome",
    "edge": "edge",
    "firefox": "firefox",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "code": "visual studio code",
    "youtube": "youtube",
  }
  for name, title in mapping.items():
    if lower == name or lower.startswith(name):
      return title
  return target.split()[0] if target else None


def _parse_hotkey(raw: str) -> list[str]:
  text = raw.strip().lower().replace(" ", "")
  text = text.replace("control", "ctrl").replace("windows", "win").replace("command", "cmd")
  if "+" in text:
    return [p for p in text.split("+") if p]
  parts = re.split(r"[+\-]", raw.strip().lower())
  keys = []
  for p in parts:
    p = p.strip()
    if not p:
      continue
    p = p.replace("control", "ctrl").replace("windows", "win")
    keys.append(p)
  return keys


def _strip_quotes(text: str) -> str:
  t = text.strip()
  if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
    return t[1:-1]
  return t
