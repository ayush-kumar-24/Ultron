"""Reminders from chat without the AI: "my reminders", "remove reminder <name>", "cancel all reminders"."""

from __future__ import annotations

import re

from maira.core.domain.entities import AutomationJob
from maira.core.domain.value_objects import AutomationStatus
from maira.core.interfaces.automation import Automation
from maira.modules.automation.parser import _format_when

_NOUN = r"(?:reminders?|alarms?|automations?|scheduled\s+jobs?)"
_VERB = r"(?:remove|delete|cancel|stop|clear)"
_LIST = re.compile(
  rf"^(?:(?:show|list|see)\s+(?:me\s+)?(?:all\s+|my\s+)*{_NOUN}|(?:my|all|pending)\s+{_NOUN}|{_NOUN}"
  rf"|{_NOUN}\s+(?:dikhao|batao|list)|(?:kaunse|konse|kon\s+se|kaun\s+se)\s+{_NOUN}\s+(?:hain|hai|h))\s*\??$",
  re.IGNORECASE,
)
_ALL = re.compile(rf"^{_VERB}\s+(?:all|every|sab|sabhi)\s+(?:(?:my|the)\s+)?{_NOUN}\s*$|^(?:sab|sabhi|all)\s+{_NOUN}\s+(?:hatao|cancel\s+karo|delete\s+karo)\s*$", re.IGNORECASE)
_REMOVE = [
  re.compile(rf"^{_VERB}\s+(?:the\s+|my\s+)?{_NOUN}\s+(?P<ref>.+?)\s*$", re.IGNORECASE),
  re.compile(rf"^(?P<ref>.+?)\s+(?:wala\s+)?{_NOUN}\s+(?:hatao|hata\s+do|cancel\s+karo|delete\s+karo|band\s+karo)\s*$", re.IGNORECASE),
]
_MAX_LISTED = 15
_TIME_TAIL = re.compile(r"\s+(?:at|for|on|in|of|by)\s+.*$|\s+(?:today|tomorrow|aaj|kal)$", re.IGNORECASE)


def _words(text: str) -> set[str]:
  return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 1}


class ReminderChat:
  def __init__(self, automation: Automation) -> None:
    self._automation = automation
    self._last_listing: list[str] = []

  def handle(self, text: str) -> str | None:
    """A reply, or None when the message is not about managing reminders."""
    cleaned = " ".join(text.strip().split()).rstrip(".!")
    if _LIST.match(cleaned):
      return self._list()
    if _ALL.match(cleaned):
      return self._remove_all()
    for pattern in _REMOVE:
      match = pattern.match(cleaned)
      if match:
        return self._remove(match.group("ref").strip(" \"'"))
    return None

  def _pending(self) -> list[AutomationJob]:
    jobs = self._automation.list_jobs(include_done=False)
    return [j for j in jobs if j.status == AutomationStatus.PENDING]

  def _list(self) -> str:
    jobs = self._pending()
    if not jobs:
      self._last_listing = []
      return "Koi reminder pending nahi hai."
    shown = jobs[:_MAX_LISTED]
    self._last_listing = [j.id for j in shown]
    lines = [f"Pending reminders ({len(jobs)}):"]
    for number, job in enumerate(shown, start=1):
      lines.append(f"{number}. {job.title} — {_format_when(job.run_at, job.recurrence)}")
    if len(jobs) > len(shown):
      lines.append(f"…aur {len(jobs) - len(shown)} more")
    lines.append('Hatane ke liye bolo: "remove reminder 1".')
    return "\n".join(lines)

  def _remove_all(self) -> str:
    jobs = self._pending()
    for job in jobs:
      self._automation.delete(job.id)
    self._last_listing = []
    if not jobs:
      return "Koi reminder pending nahi tha."
    return f"Sab {len(jobs)} reminder hata diye."

  def _remove(self, ref: str) -> str:
    jobs = self._pending()
    found = self._resolve(ref, jobs)
    if not found:
      # "call mom at 6pm" / "drink water kal" -> the name without its time.
      bare = _TIME_TAIL.sub("", ref).strip()
      if bare and bare != ref:
        found = self._resolve(bare, jobs)
    if isinstance(found, AutomationJob):
      self._automation.delete(found.id)
      self._last_listing = [i for i in self._last_listing if i != found.id]
      return f'Reminder hata diya: "{found.title}".'
    if found:
      shown = found[:5]
      self._last_listing = [j.id for j in shown]
      options = "\n".join(f"{n}. {j.title}" for n, j in enumerate(shown, start=1))
      return f'Kaunsa reminder? Ek se zyada match hue:\n{options}\nBolo: "remove reminder 1".'
    if ref.isdigit():
      return 'Pehle "my reminders" bolo, phir number (jaise "remove reminder 1").'
    return f'"{ref}" naam ka koi pending reminder nahi mila. "My reminders" bolke list dekho.'

  def _resolve(self, ref: str, jobs: list[AutomationJob]) -> AutomationJob | list[AutomationJob]:
    if ref.isdigit():
      index = int(ref) - 1
      if 0 <= index < len(self._last_listing):
        wanted = self._last_listing[index]
        return next((j for j in jobs if j.id == wanted), [])
      return []
    lowered = ref.lower()
    exact = [j for j in jobs if j.title.lower().rstrip("…") == lowered]
    if len(exact) == 1:
      return exact[0]
    query = _words(ref)
    if not query:
      return []
    # Every word the user gave must appear in the reminder, or it is a prefix of the title.
    matches = [
      j for j in jobs
      if query <= _words(j.title + " " + j.instruction) or j.title.lower().startswith(lowered)
    ]
    return matches[0] if len(matches) == 1 else matches
