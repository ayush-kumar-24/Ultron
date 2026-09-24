"""Pick the skill for a message: asked for by name, or the best match."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from maira.modules.skills.discover import slugify
from maira.modules.skills.models import KIND_COMMAND, Skill

_STOP = set("""
a an the and or but if then than so to of in on at by for from with without into onto about as is are was were be
been being it its this that these those there here i me my we our you your he she they them their what which who whom
when where why how can could should would will shall may might must do does did done have has had not no yes please
any all some more most other such only own same too very just also use used using uses user users want wants wanted
ask asks asked skill skills help helps need needs like make makes made get gets let lets new one two via etc e g eg ie
whenever anything something everything thing things way ways work works file files task tasks request requests
include includes including trigger triggers mention mentions mentioned whether also able provide provides
create creates creating write writes writing make build builds generate generates produce give show kind sort
set sets list lists good best better great nice start starts starting check checks look looks
mujhe mera meri mere hai hain ho karo kar karna kya ka ki ke ko se me mein aur ya toh bhi yeh ye woh wo ek do
""".split())

_EXPLICIT = [
  re.compile(r"^/(?P<name>[\w.-]+)(?:\s+(?P<rest>.*))?$", re.DOTALL),
  re.compile(r"^(?:please\s+)?(?:use|using|with|apply|run)\s+(?:the\s+|my\s+)?(?P<name>[\w.-]+)\s+skill\b[\s,:-]*(?:to\s+|for\s+|and\s+)?(?P<rest>.*)$", re.IGNORECASE | re.DOTALL),
  re.compile(r"^(?P<name>[\w.-]+)\s+skill\s+(?:se|use\s+karke|use\s+kar\s+ke|ke\s+saath|with)\b[\s,:-]*(?P<rest>.*)$", re.IGNORECASE | re.DOTALL),
  re.compile(r"^skill\s+(?P<name>[\w.-]+)\s*[:,-]\s*(?P<rest>.*)$", re.IGNORECASE | re.DOTALL),
]

MIN_SCORE = 4.0


_ALIASES = {
  "powerpoint": "pptx presentation slide deck",
  "ppt": "pptx presentation slide",
  "excel": "xlsx spreadsheet",
  "sheet": "spreadsheet xlsx",
  "word": "docx document",
  "doc": "docx document",
  "gif": "animation",
  "debug": "bug",
}


def _stem(word: str) -> str:
  word = word.lower().strip("'")
  if word.endswith("'s"):
    word = word[:-2]
  if len(word) > 4 and word.endswith("ies"):
    word = word[:-3] + "y"
  elif len(word) > 4 and word.endswith(("sses", "shes", "ches", "xes")):
    word = word[:-2]
  elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
    word = word[:-1]
  for suffix in ("ing", "ed"):
    if len(word) > len(suffix) + 3 and word.endswith(suffix):
      word = word[: -len(suffix)]
      if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":
        word = word[:-1]  # debugging -> debug
      break
  if len(word) > 4 and word.endswith("e"):
    word = word[:-1]  # create / creating -> creat
  return word[:8]


def _words(text: str) -> list[str]:
  words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#]*", text.lower())
  return [_stem(w) for w in words if len(w) > 1 and w not in _STOP]


def tokens(text: str) -> set[str]:
  return set(_words(text)) - _STOP


def _query_tokens(text: str) -> set[str]:
  found = tokens(text)
  for word in re.findall(r"[a-zA-Z]+", text.lower()):
    if word in _ALIASES:
      found |= tokens(_ALIASES[word])
  return found


@dataclass(frozen=True)
class SkillMatch:
  skill: Skill
  request: str  # the message without the "/name" or "use X skill" part
  explicit: bool
  score: float = 0.0


@dataclass(frozen=True)
class UnknownSkill:
  name: str  # asked for by name, but not installed / turned off


def explicit_request(text: str, skills: list[Skill]) -> SkillMatch | UnknownSkill | None:
  by_name: dict[str, Skill] = {}
  for skill in skills:
    by_name.setdefault(skill.name, skill)
    by_name.setdefault(skill.id.lower(), skill)
  for index, pattern in enumerate(_EXPLICIT):
    match = pattern.match(text.strip())
    if not match:
      continue
    raw = match.group("name").lower()
    skill = by_name.get(raw) or by_name.get(slugify(raw, ""))
    if skill is not None:
      return SkillMatch(skill, (match.group("rest") or "").strip(), explicit=True)
    if index == 0 or index == 1:
      # "/foo …" or "use foo skill …" clearly asks for a skill.
      return UnknownSkill(raw)
  return None


class SkillMatcher:
  """Lexical match on name + description, weighted by how rare each word is."""

  def __init__(self, skills: list[Skill]) -> None:
    self._skills = [s for s in skills if s.enabled]
    self._docs: list[tuple[Skill, set[str], dict[str, int], int]] = []
    df: dict[str, int] = {}
    for skill in self._skills:
      name_tokens = tokens(skill.name.replace("-", " "))
      counts: dict[str, int] = {}
      for word in _words(skill.description):
        counts[word] = counts.get(word, 0) + 1
      name_words = len([w for w in re.split(r"[-_\s]+", skill.name) if w])
      self._docs.append((skill, name_tokens, counts, name_words))
      for token in name_tokens | set(counts):
        df[token] = df.get(token, 0) + 1
    count = max(1, len(self._skills))
    self._idf = {t: math.log(1 + count / n) + 1.0 for t, n in df.items()}

  def match(self, text: str) -> SkillMatch | UnknownSkill | None:
    asked = explicit_request(text, self._skills)
    if asked is not None:
      return asked
    return self.best(text)

  def best(self, text: str) -> SkillMatch | None:
    query = _query_tokens(text)
    if not query:
      return None
    best: tuple[float, Skill] | None = None
    for skill, name_tokens, counts, name_words in self._docs:
      if skill.kind == KIND_COMMAND:
        continue  # commands run only when called: /name
      name_hits = query & name_tokens
      desc_hits = (query & set(counts)) - name_hits
      repeated = any(counts[t] >= 2 for t in desc_hits)
      if name_hits:
        # One common word of a longer name ("plan" in writing-plans) is not enough on its own.
        whole_name = len(name_hits) == name_words
        strong = whole_name or len(name_hits) >= 2 or len(desc_hits) >= 2
      else:
        strong = len(desc_hits) >= 2 or repeated
      if not strong:
        continue
      score = sum(self._idf.get(t, 1.0) * 3 for t in name_hits)
      score += sum(self._idf.get(t, 1.0) * (1 + math.log(counts[t])) for t in desc_hits)
      if best is None or score > best[0]:
        best = (score, skill)
    if best is None or best[0] < MIN_SCORE:
      return None
    return SkillMatch(best[1], text.strip(), explicit=False, score=round(best[0], 2))
