"""Skill and skill-pack records (what data/skills/skills.json stores)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

KIND_SKILL = "skill"  # a SKILL.md folder (Agent Skills standard)
KIND_COMMAND = "command"  # a slash-command prompt (.claude/commands/*.md, …)
KIND_REPO = "repo"  # any other repo: README / AGENTS.md / CLAUDE.md / rules


@dataclass
class Skill:
  id: str  # "<pack>/<name>", unique
  name: str  # what the user types: /name
  description: str
  kind: str
  pack: str
  folder: str  # skill folder inside the pack ("" = pack root)
  entry: str  # instruction file inside the pack
  license: str = ""
  enabled: bool = True
  scripts_allowed: bool = False  # the user must turn this on in Settings
  scripts: list[str] = field(default_factory=list)  # relative to the skill folder
  warnings: list[str] = field(default_factory=list)  # from the safety scan
  scripts_hash: str = ""  # an update that changes scripts turns scripts_allowed off again

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> Skill:
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SkillPack:
  id: str
  label: str  # owner/repo[/folder]
  source: dict[str, str]  # SkillSource.to_dict()
  web_url: str
  commit: str = ""
  ref: str = ""
  installed_at: str = ""
  updated_at: str = ""
  skills: list[Skill] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    data = asdict(self)
    data["skills"] = [s.to_dict() for s in self.skills]
    return data

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> SkillPack:
    known = {f.name for f in fields(cls)} - {"skills"}
    pack = cls(**{k: v for k, v in data.items() if k in known})
    pack.skills = [Skill.from_dict(s) for s in data.get("skills", [])]
    return pack
