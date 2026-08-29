"""Parse natural-language schedule requests (English + light Hinglish)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
)

# Prefer India local time for this product; fall back to system local.
try:
  LOCAL_TZ = ZoneInfo("Asia/Kolkata")
except Exception:  # noqa: BLE001
  LOCAL_TZ = datetime.now().astimezone().tzinfo or timezone.utc

_URL_RE = re.compile(r"https?://\S+", re.I)
_TIME_RE = re.compile(
  r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
  re.I,
)
# "in 5 minutes" | "5 minutes" | "5 min later" | "after 5 mins"
_RELATIVE_RE = re.compile(
  r"(?i)(?:\b(?:in|after)\s+)?(\d+)\s*"
  r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)"
  r"(?:\s+(?:later|baad))?\b"
)
_BAAD_RE = re.compile(
  r"\b(\d+)\s*(second|sec|minute|min|hour|hr)s?\s*baad\b",
  re.I,
)
_EVERY_DAY_RE = re.compile(r"\b(every\s+day|daily|roz)\b", re.I)
_EVERY_WEEK_RE = re.compile(r"\b(every\s+week|weekly)\b", re.I)
_TOMORROW_RE = re.compile(r"\b(tomorrow|kal)\b", re.I)
_TODAY_RE = re.compile(r"\b(today|aaj)\b", re.I)
_DURATION_AFTER_NUM = re.compile(
  r"^\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
  re.I,
)

_SCHEDULE_HINT = re.compile(
  r"(?i)(?:"
  r"remind\s+me|schedule|automate|set\s+a\s+reminder|"
  r"yaad\s+dila|\bremind\b|"
  r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
  r"\b(?:in|after)\s+\d+\s*(?:mins?|minutes?|hours?|hrs?|secs?|seconds?)|"
  r"\d+\s*(?:mins?|minutes?|hours?|hrs?|secs?|seconds?)(?:\s+(?:later|baad|\bremind\b))?|"
  r"\btomorrow\b|\bkal\b|every\s+day|\bdaily\b|\broz\b|"
  r"\bopen\b.+\bat\b|\blaunch\b.+\bat\b"
  r")"
)

_STRIP_LEAD = re.compile(
  r"^\s*(please\s+)?("
  r"remind\s+me\s+to|remind\s+me|schedule|automate|"
  r"set\s+a\s+reminder\s+to|set\s+a\s+reminder|"
  r"yaad\s+dila\s+(dena\s+)?|yaad\s+dilana\s+"
  r")\s*",
  re.I,
)

_KNOWN_URLS = {
  "youtube": "https://www.youtube.com",
  "gmail": "https://mail.google.com",
  "google": "https://www.google.com",
  "github": "https://github.com",
  "whatsapp": "https://web.whatsapp.com",
  "linkedin": "https://www.linkedin.com",
  "twitter": "https://x.com",
  "x.com": "https://x.com",
  "chatgpt": "https://chatgpt.com",
}

_KNOWN_APPS = {
  "notepad": "notepad.exe",
  "calculator": "calc.exe",
  "calc": "calc.exe",
  "explorer": "explorer.exe",
  "file explorer": "explorer.exe",
  "cmd": "cmd.exe",
  "terminal": "wt.exe",
  "paint": "mspaint.exe",
}


@dataclass(frozen=True)
class ParsedSchedule:
  title: str
  instruction: str
  run_at: datetime
  recurrence: AutomationRecurrence
  action_type: AutomationActionType
  action_payload: str
  confirmation: str


def looks_like_schedule_request(text: str) -> bool:
  return bool(_SCHEDULE_HINT.search(text or ""))


def parse_schedule_request(
  text: str,
  *,
  now: datetime | None = None,
) -> ParsedSchedule | None:
  """Return a ParsedSchedule when the message clearly asks to run something later."""
  cleaned = " ".join((text or "").strip().split())
  if not cleaned or not looks_like_schedule_request(cleaned):
    return None

  moment = now or datetime.now(LOCAL_TZ)
  if moment.tzinfo is None:
    moment = moment.replace(tzinfo=LOCAL_TZ)
  else:
    moment = moment.astimezone(LOCAL_TZ)

  recurrence = AutomationRecurrence.NONE
  if _EVERY_WEEK_RE.search(cleaned):
    recurrence = AutomationRecurrence.WEEKLY
  elif _EVERY_DAY_RE.search(cleaned):
    recurrence = AutomationRecurrence.DAILY

  run_at = _parse_run_at(cleaned, moment)
  if run_at is None:
    return None

  instruction = _extract_instruction(cleaned)
  if not instruction:
    # "remind me in 1 minute" → empty after stripping; still a valid ping.
    if re.search(r"\b(remind|yaad|notification|notify)\b", cleaned, re.I):
      instruction = "Reminder"
    else:
      return None

  action_type, payload = infer_action(instruction)
  # Bare "remind" / "Reminder" → toast notify with a clear message.
  if action_type == AutomationActionType.NOTIFY and instruction.lower() in {
    "remind",
    "reminder",
    "yaad",
  }:
    payload = {"message": "Reminder — time hai"}
    instruction = "Reminder"

  title = _title_from(instruction)
  when_label = _format_when(run_at, recurrence)
  confirmation = (
    f"Ho gaya — \"{title}\" schedule kar diya hai for {when_label}. "
    f"Automations tab mein dikhega. "
    f"Ultron chalu rahe toh usi time pe chalega."
  )
  return ParsedSchedule(
    title=title,
    instruction=instruction,
    run_at=run_at.astimezone(timezone.utc),
    recurrence=recurrence,
    action_type=action_type,
    action_payload=json.dumps(payload),
    confirmation=confirmation,
  )


def infer_action(instruction: str) -> tuple[AutomationActionType, dict]:
  text = instruction.strip()
  lower = text.lower()

  url_match = _URL_RE.search(text)
  if url_match:
    return AutomationActionType.OPEN_URL, {"url": url_match.group(0).rstrip(".,)")}

  open_match = re.search(r"\b(?:open|launch|start)\s+([a-z0-9 .+-]+)", lower)
  if open_match:
    target = open_match.group(1).strip(" .")
    for name, url in _KNOWN_URLS.items():
      if target == name or target.startswith(name + " "):
        return AutomationActionType.OPEN_URL, {"url": url}
    for name, app in _KNOWN_APPS.items():
      if target == name or target.startswith(name):
        return AutomationActionType.OPEN_APP, {"app": app}

  if re.search(r"\b(remind|reminder|yaad|notification|notify)\b", lower) and len(text) < 120:
    return AutomationActionType.NOTIFY, {"message": text if text.lower() not in {"remind", "reminder", "yaad"} else "Reminder — time hai"}

  return AutomationActionType.AGENT, {"instruction": text}


def _parse_run_at(text: str, now: datetime) -> datetime | None:
  rel = _RELATIVE_RE.search(text) or _BAAD_RE.search(text)
  if rel:
    amount = int(rel.group(1))
    unit = rel.group(2).lower()
    if unit.startswith("sec"):
      delta = timedelta(seconds=amount)
    elif unit.startswith("min"):
      delta = timedelta(minutes=amount)
    else:
      delta = timedelta(hours=amount)
    return now + delta

  day = now.date()
  if _TOMORROW_RE.search(text):
    day = (now + timedelta(days=1)).date()
  elif _TODAY_RE.search(text):
    day = now.date()

  candidates = list(_TIME_RE.finditer(text))
  time_match = None
  for match in reversed(candidates):
    start = match.start()
    window = text[max(0, start - 10) : start].lower()
    after = text[match.end() : match.end() + 12]
    # "1 minute" / "in 5 hours" — not a clock time
    if "in " in window or "after " in window:
      continue
    if _DURATION_AFTER_NUM.match(after):
      continue
    if "baad" in after.lower():
      continue
    time_match = match
    break

  if time_match is None:
    return None

  hour = int(time_match.group(1))
  minute = int(time_match.group(2) or 0)
  ampm = (time_match.group(3) or "").lower()
  if ampm == "pm" and hour < 12:
    hour += 12
  elif ampm == "am" and hour == 12:
    hour = 0
  if hour > 23 or minute > 59:
    return None

  run_at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=LOCAL_TZ)

  if run_at <= now and not _TOMORROW_RE.search(text):
    # Bare "7:38" in the evening usually means 7:38 PM, not tomorrow morning.
    if not ampm and hour < 12:
      pm_guess = run_at + timedelta(hours=12)
      if pm_guess > now:
        return pm_guess
    run_at = run_at + timedelta(days=1)
  return run_at


def _extract_instruction(text: str) -> str:
  cleaned = _STRIP_LEAD.sub("", text).strip()
  cleaned = _RELATIVE_RE.sub(" ", cleaned)
  cleaned = _BAAD_RE.sub(" ", cleaned)
  cleaned = _EVERY_DAY_RE.sub(" ", cleaned)
  cleaned = _EVERY_WEEK_RE.sub(" ", cleaned)
  cleaned = _TOMORROW_RE.sub(" ", cleaned)
  cleaned = _TODAY_RE.sub(" ", cleaned)
  cleaned = re.sub(
    r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
    " ",
    cleaned,
    flags=re.I,
  )
  cleaned = re.sub(
    r"\b(to|for|please|kar\s+dena|karna|ko|subah|shaam|baje)\b",
    " ",
    cleaned,
    flags=re.I,
  )
  cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
  return cleaned


def _title_from(instruction: str) -> str:
  words = instruction.split()
  if not words:
    return "Automation"
  title = " ".join(words[:8])
  if len(words) > 8:
    title += "…"
  return title[:60]


def _format_when(run_at: datetime, recurrence: AutomationRecurrence) -> str:
  local = run_at.astimezone(LOCAL_TZ)
  stamp = local.strftime("%a %d %b, %I:%M %p").lstrip("0").replace(" 0", " ")
  if recurrence == AutomationRecurrence.DAILY:
    return f"every day at {local.strftime('%I:%M %p').lstrip('0')} (next: {stamp})"
  if recurrence == AutomationRecurrence.WEEKLY:
    return f"every week at {local.strftime('%I:%M %p').lstrip('0')} (next: {stamp})"
  return stamp
