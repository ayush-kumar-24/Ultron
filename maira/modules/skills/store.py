"""Installed skills: data/skills/skills.json plus one folder per repo (a "pack")."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from maira.modules.skills.discover import discover, slugify
from maira.modules.skills.fetch import Progress, fetch, rmtree
from maira.modules.skills.models import Skill, SkillPack
from maira.modules.skills.scan import scan_skill
from maira.modules.skills.source import SkillSource, parse_source


class SkillError(RuntimeError):
  """A skill operation failed; the message is shown to the user."""


@dataclass
class InstallReport:
  pack: SkillPack
  added: list[str] = field(default_factory=list)
  updated: list[str] = field(default_factory=list)
  removed: list[str] = field(default_factory=list)
  was_installed: bool = False

  @property
  def summary(self) -> str:
    count = len(self.pack.skills)
    what = "Updated" if self.was_installed else "Installed"
    names = ", ".join(s.name for s in self.pack.skills[:6])
    more = f" and {count - 6} more" if count > 6 else ""
    text = f"{what} {self.pack.label}: {count} skill{'s' if count != 1 else ''} ({names}{more})."
    if self.was_installed and (self.added or self.removed):
      text += f" New: {len(self.added)}, removed: {len(self.removed)}."
    return text


def _now() -> str:
  return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_scripts(folder: Path, scripts: list[str]) -> str:
  digest = hashlib.sha256()
  for rel in scripts:
    digest.update(rel.encode())
    try:
      digest.update((folder / rel).read_bytes())
    except OSError:
      pass
  return digest.hexdigest()[:16] if scripts else ""


class SkillStore:
  def __init__(self, root: Path) -> None:
    self.root = Path(root)
    self.packs_dir = self.root / "packs"
    self.work_dir = self.root / "work"
    self._registry = self.root / "skills.json"
    self._lock = threading.RLock()
    self._listeners: list[Callable[[], None]] = []
    self._packs: dict[str, SkillPack] = {}
    self._load()

  # --- reading ----------------------------------------------------------------------------

  def _load(self) -> None:
    try:
      data = json.loads(self._registry.read_text(encoding="utf-8"))
      self._packs = {p["id"]: SkillPack.from_dict(p) for p in data.get("packs", [])}
    except FileNotFoundError:
      self._packs = {}
    except (OSError, ValueError, KeyError, TypeError):
      logger.exception("Skill registry is unreadable; starting empty")
      self._packs = {}

  def packs(self) -> list[SkillPack]:
    with self._lock:
      return sorted(self._packs.values(), key=lambda p: p.label.lower())

  def skills(self, *, enabled_only: bool = False) -> list[Skill]:
    with self._lock:
      items = [s for p in self.packs() for s in p.skills]
    return [s for s in items if s.enabled] if enabled_only else items

  def get(self, skill_id: str) -> Skill | None:
    pack_id = skill_id.split("/", 1)[0]
    with self._lock:
      pack = self._packs.get(pack_id)
      return next((s for s in pack.skills if s.id == skill_id), None) if pack else None

  def pack(self, pack_id: str) -> SkillPack | None:
    with self._lock:
      return self._packs.get(pack_id)

  def find(self, text: str) -> list[Skill]:
    """Skills called ``text`` (name or id; "pdf", "/pdf", "anthropics-skills/pdf")."""
    key = text.strip().lstrip("/").lower()
    slug = slugify(key, "")
    return [s for s in self.skills() if key in (s.id.lower(), s.name) or (slug and s.name == slug)]

  def find_pack(self, text: str) -> SkillPack | None:
    key = text.strip().lower()
    packs = self.packs()
    for pack in packs:
      if key in (pack.id, pack.label.lower(), pack.web_url.lower().rstrip("/")):
        return pack
    try:
      pack_id = self._pack_id(parse_source(text))
      if pack_id in self._packs:
        return self._packs[pack_id]
    except ValueError:
      pass
    matches = [p for p in packs if p.label.lower().split("/")[-1] == key or p.id.endswith(f"-{slugify(key, '?')}")]
    return matches[0] if len(matches) == 1 else None

  def skill_dir(self, skill: Skill) -> Path:
    return (self.packs_dir / skill.pack / skill.folder).resolve()

  def pack_dir(self, pack_id: str) -> Path:
    return (self.packs_dir / pack_id).resolve()

  def read_entry(self, skill: Skill, limit: int = 200_000) -> str:
    if not skill.entry:
      return ""
    path = (self.packs_dir / skill.pack / skill.entry).resolve()
    if not path.is_relative_to(self.pack_dir(skill.pack)):
      return ""
    try:
      with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)
    except OSError:
      return ""

  # --- changes -------------------------------------------------------------------------

  def on_change(self, listener: Callable[[], None]) -> None:
    self._listeners.append(listener)

  def _changed(self) -> None:
    self._save()
    for listener in list(self._listeners):
      try:
        listener()
      except Exception:  # noqa: BLE001
        logger.exception("Skill change listener failed")

  def _save(self) -> None:
    self.root.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "packs": [p.to_dict() for p in self.packs()]}
    fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".skills-", suffix=".json")
    try:
      with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
      os.replace(tmp, self._registry)
    except BaseException:
      Path(tmp).unlink(missing_ok=True)
      raise

  @staticmethod
  def _pack_id(source: SkillSource) -> str:
    if source.is_local:
      return slugify(f"local-{Path(source.local_path).name}")
    return slugify(f"{source.owner}-{source.repo}-{source.subpath}".rstrip("-"))

  def install(self, text: str | SkillSource, progress: Progress | None = None) -> InstallReport:
    """Download and add every skill in a repo. Installing it again updates it."""
    source = text if isinstance(text, SkillSource) else parse_source(text)
    say = progress or (lambda _m: None)
    pack_id = self._pack_id(source)
    self.packs_dir.mkdir(parents=True, exist_ok=True)
    staging = self.packs_dir / f".{pack_id}.new"
    result = fetch(source, staging, say)
    try:
      found = discover(staging, name_hint=source.repo or Path(source.local_path).name)
      say(f"Found {len(found)} skill{'s' if len(found) != 1 else ''}. Checking scripts…")
      with self._lock:
        old = self._packs.get(pack_id)
        previous = {s.name: s for s in old.skills} if old else {}
        pack = SkillPack(
          id=pack_id,
          label=source.label,
          source=source.to_dict(),
          web_url=source.web_url,
          commit=result.commit,
          ref=result.ref,
          installed_at=old.installed_at if old else _now(),
          updated_at=_now(),
        )
        report = InstallReport(pack=pack, was_installed=old is not None)
        for item in found:
          folder = staging / item.folder if item.folder else staging
          scripts_hash = _hash_scripts(folder, item.scripts)
          before = previous.get(item.name)
          skill = Skill(
            id=f"{pack_id}/{item.name}",
            name=item.name,
            description=item.description,
            kind=item.kind,
            pack=pack_id,
            folder=item.folder,
            entry=item.entry,
            license=item.license,
            enabled=before.enabled if before else True,
            # Changed scripts must be approved again.
            scripts_allowed=bool(before and before.scripts_allowed and before.scripts_hash == scripts_hash),
            scripts=item.scripts,
            warnings=scan_skill(folder, item.scripts),
            scripts_hash=scripts_hash,
          )
          pack.skills.append(skill)
          (report.updated if before else report.added).append(skill.name)
        report.removed = sorted(set(previous) - {s.name for s in pack.skills})

        final = self.packs_dir / pack_id
        retired = self.packs_dir / f".{pack_id}.old"
        rmtree(retired)
        if final.exists():
          final.rename(retired)
        try:
          staging.rename(final)
        except OSError:
          if retired.exists():
            retired.rename(final)  # keep the working version
          raise
        rmtree(retired)
        self._packs[pack_id] = pack
        self._changed()
      logger.info("Skills {}: {}", "updated" if report.was_installed else "installed", report.summary)
      return report
    finally:
      rmtree(staging)

  def update(self, pack_id: str, progress: Progress | None = None) -> InstallReport:
    pack = self.pack(pack_id)
    if pack is None:
      raise SkillError(f"No skill pack called {pack_id}.")
    return self.install(SkillSource.from_dict(pack.source), progress)

  def remove_pack(self, pack_id: str) -> SkillPack:
    with self._lock:
      pack = self._packs.pop(pack_id, None)
      if pack is None:
        raise SkillError(f"No skill pack called {pack_id}.")
      rmtree(self.packs_dir / pack_id)
      self._changed()
    logger.info("Removed skills from {}", pack.label)
    return pack

  def _set(self, skill_id: str, **changes) -> Skill:
    with self._lock:
      skill = self.get(skill_id)
      if skill is None:
        raise SkillError(f"No skill called {skill_id}.")
      for key, value in changes.items():
        setattr(skill, key, value)
      self._changed()
      return skill

  def set_enabled(self, skill_id: str, enabled: bool) -> Skill:
    return self._set(skill_id, enabled=bool(enabled))

  def set_pack_enabled(self, pack_id: str, enabled: bool) -> None:
    with self._lock:
      pack = self._packs.get(pack_id)
      if pack is None:
        raise SkillError(f"No skill pack called {pack_id}.")
      for skill in pack.skills:
        skill.enabled = bool(enabled)
      self._changed()

  def set_scripts_allowed(self, skill_id: str, allowed: bool) -> Skill:
    """Only the Settings screen calls this (never chat), after showing the warnings."""
    return self._set(skill_id, scripts_allowed=bool(allowed))
