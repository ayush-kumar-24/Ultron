"""Turn a skill into the instructions the local model follows."""

from __future__ import annotations

import re
from pathlib import Path

from maira.modules.skills.discover import find_readme, repo_instruction_files, split_frontmatter
from maira.modules.skills.matcher import tokens
from maira.modules.skills.models import KIND_COMMAND, KIND_REPO, Skill
from maira.modules.skills.store import SkillStore

_LINKED = re.compile(r"(?:\]\(|`|\b)([\w./-]+\.(?:md|txt|mdc))\b", re.IGNORECASE)
MAX_FILES_LISTED = 40


def _read(path: Path, limit: int) -> str:
  try:
    with open(path, encoding="utf-8", errors="replace") as handle:
      return handle.read(limit)
  except OSError:
    return ""


def _clip(text: str, limit: int) -> tuple[str, bool]:
  text = text.strip()
  if len(text) <= limit:
    return text, False
  cut = text[:limit]
  cut = cut[: cut.rfind("\n")] if "\n" in cut[limit // 2 :] else cut
  return cut.rstrip() + "\n…(shortened)", True


def _file_list(folder: Path) -> list[str]:
  files: list[str] = []
  for path in sorted(folder.rglob("*")):
    rel = path.relative_to(folder)
    if path.is_file() and not any(part.startswith(".") or part == "node_modules" for part in rel.parts):
      files.append(rel.as_posix())
      if len(files) > MAX_FILES_LISTED:
        break
  return files


def _linked_files(body: str, folder: Path, request: str, entry: Path) -> list[Path]:
  """Other docs the instructions point to (reference.md, forms.md …), most relevant first."""
  wanted = tokens(request)
  found: list[Path] = []
  for name in dict.fromkeys(m.group(1) for m in _LINKED.finditer(body)):
    for candidate in (folder / name, folder / name.lower(), folder / name.upper()):
      path = candidate.resolve()
      if path.is_file() and path.is_relative_to(folder) and path != entry and path not in found:
        found.append(path)
        break
  return sorted(found, key=lambda p: -len(wanted & tokens(p.stem.replace("_", " "))))


def _instructions(store: SkillStore, skill: Skill, request: str, budget: int) -> str:
  folder = store.skill_dir(skill)
  if skill.kind == KIND_REPO:
    pack = store.pack_dir(skill.pack)
    parts: list[tuple[str, str]] = []
    for path in repo_instruction_files(pack):
      parts.append((path.relative_to(pack).as_posix(), _read(path, 60_000)))
    readme = find_readme(pack)
    if readme is not None:
      parts.append((readme.name, _read(readme, 120_000)))
    if not parts:
      return "This repo has no README. Its files:\n" + "\n".join(_file_list(pack))
    share = max(800, budget // len(parts))
    return "\n\n".join(f"--- {name} ---\n{_clip(text, share)[0]}" for name, text in parts)

  _meta, body = split_frontmatter(store.read_entry(skill))
  if skill.kind == KIND_COMMAND:
    args = request.strip()
    body = body.replace("$ARGUMENTS", args or "(none)")
    for i, word in enumerate(args.split()[:9], start=1):
      body = body.replace(f"${i}", word)
  text, shortened = _clip(body, budget)
  remaining = budget - len(text)
  entry = (store.pack_dir(skill.pack) / skill.entry).resolve()
  if not shortened and remaining > 1200:
    for path in _linked_files(body, folder, request, entry):
      extra, _ = _clip(_read(path, 100_000), remaining - 200)
      text += f"\n\n--- {path.relative_to(folder).as_posix()} ---\n{extra}"
      remaining = budget - len(text)
      if remaining < 1200:
        break
  return text


def build_skill_prompt(store: SkillStore, skill: Skill, request: str, max_chars: int) -> str:
  pack = store.pack(skill.pack)
  where = pack.label if pack else skill.pack
  lines = [
    f'You are using the skill "{skill.name}" from {where}.',
    f"What it is for: {skill.description}" if skill.description else "",
    "Follow the skill's instructions below to help with the user's request. The instructions may "
    "mention tools you don't have (such as editing files, web browsing or sub-agents): skip those "
    "parts and give the best answer you can in your reply.",
    "",
    "=== SKILL INSTRUCTIONS ===",
    _instructions(store, skill, request, max_chars),
    "=== END OF SKILL ===",
  ]
  folder = store.skill_dir(skill)
  if skill.kind != KIND_REPO:
    files = _file_list(folder)
    if len(files) > 1:
      shown = ", ".join(files[:MAX_FILES_LISTED]) + (" …" if len(files) > MAX_FILES_LISTED else "")
      lines += ["", f"Files in this skill: {shown}"]
  if skill.scripts and skill.scripts_allowed:
    lines += [
      "",
      "You may run this skill's scripts. To run one, explain in one line why, then write exactly one block:",
      "```run",
      f"python {skill.scripts[0]} <arguments>",
      "```",
      "Script paths are relative to the skill folder. Output files go to: "
      f"{store.work_dir}. Ultron asks the user before running and then shows you the output.",
    ]
  elif skill.scripts:
    lines += [
      "",
      "This skill has scripts, but running them is turned off. Do not write commands to run them; "
      "if one is needed, tell the user they can allow scripts in Settings → Skills.",
    ]
  return "\n".join(line for line in lines if line is not None).strip()
