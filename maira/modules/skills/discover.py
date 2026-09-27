"""Find the skills in a downloaded repo, whatever its layout."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from maira.modules.skills.models import KIND_COMMAND, KIND_REPO, KIND_SKILL

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox", ".mypy_cache"}
SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".bat", ".cmd", ".rb", ".pl"}
MAX_SCRIPTS_LISTED = 200
# Agent instruction files many repos ship (used when a repo has no SKILL.md).
INSTRUCTION_FILES = (
  "AGENTS.md", "CLAUDE.md", "GEMINI.md", "llms.txt", ".cursorrules", ".windsurfrules",
  ".github/copilot-instructions.md",
)
README_NAMES = ("README.md", "README.markdown", "README.rst", "README.txt", "README", "readme.md", "Readme.md")


@dataclass
class FoundSkill:
  name: str
  description: str
  kind: str
  folder: str  # relative to the repo root, posix
  entry: str  # relative to the repo root, posix
  license: str = ""
  scripts: list[str] = field(default_factory=list)


def slugify(text: str, fallback: str = "skill") -> str:
  slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
  return slug[:64].strip("-") or fallback


def split_frontmatter(text: str) -> tuple[dict, str]:
  """(metadata, body) for a Markdown file with optional --- YAML --- front matter."""
  text = text.lstrip("﻿")
  match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
  if not match:
    return {}, text
  block, body = match.group(1), text[match.end():]
  try:
    data = yaml.safe_load(block)
    if isinstance(data, dict):
      return {str(k): v for k, v in data.items()}, body
  except yaml.YAMLError:
    pass
  # Broken YAML (e.g. an unquoted colon in the description): read simple "key: value" lines.
  data: dict = {}
  for line in block.splitlines():
    kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
    if kv:
      data[kv.group(1)] = kv.group(2).strip().strip("'\"")
  return data, body


def _text(path: Path, limit: int = 400_000) -> str:
  try:
    with open(path, encoding="utf-8", errors="replace") as handle:
      return handle.read(limit)
  except OSError:
    return ""


def _walk(root: Path):
  stack = [root]
  while stack:
    folder = stack.pop()
    try:
      entries = sorted(folder.iterdir(), key=lambda p: p.name)
    except OSError:
      continue
    for entry in entries:
      if entry.is_symlink():
        continue
      if entry.is_dir():
        if entry.name not in SKIP_DIRS:
          stack.append(entry)
      else:
        yield entry


def first_paragraph(markdown: str, limit: int = 300) -> str:
  """A plain-text summary: the first real paragraph (no headings, badges or HTML)."""
  text = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
  text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
  for block in re.split(r"\n\s*\n", text):
    lines = [ln.strip() for ln in block.strip().splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith(("#", "|", "---", "===", "[!", "!["))]
    plain = " ".join(lines)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", plain)
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", plain)
    plain = re.sub(r"[*_`]+", "", plain).strip()
    if len(plain) >= 20 and not plain.lower().startswith(("table of contents", "contents")):
      if len(plain) <= limit:
        return plain
      return plain[:limit].rsplit(" ", 1)[0] + "…"
  return ""


def _scripts_in(folder: Path, repo: Path) -> list[str]:
  scripts: list[str] = []
  for path in _walk(folder):
    if path.suffix.lower() in SCRIPT_SUFFIXES:
      scripts.append(path.relative_to(folder).as_posix())
      if len(scripts) >= MAX_SCRIPTS_LISTED:
        break
  return sorted(scripts)


def _describe(meta: dict, body: str) -> str:
  description = meta.get("description")
  if isinstance(description, str) and description.strip():
    return " ".join(description.split())[:1024]
  return first_paragraph(body)


def _find_skill_files(repo: Path) -> list[FoundSkill]:
  found: list[FoundSkill] = []
  for path in _walk(repo):
    if path.name.lower() != "skill.md":
      continue
    meta, body = split_frontmatter(_text(path))
    folder = path.parent
    name = meta.get("name") if isinstance(meta.get("name"), str) else ""
    fallback = folder.name if folder != repo else repo.name
    found.append(
      FoundSkill(
        name=slugify(name or fallback),
        description=_describe(meta, body),
        kind=KIND_SKILL,
        folder=folder.relative_to(repo).as_posix() if folder != repo else "",
        entry=path.relative_to(repo).as_posix(),
        license=str(meta.get("license") or "")[:120],
        scripts=_scripts_in(folder, repo),
      )
    )
  real = [s for s in found if Path(s.folder).name.lower() not in ("template", "templates", "skill-template")]
  return real or found


def _command_dirs(repo: Path) -> list[Path]:
  dirs: list[Path] = []
  for folder in [repo, *[p for p in repo.rglob("*") if p.is_dir() and not (set(p.parts) & SKIP_DIRS)]]:
    if (folder / ".claude" / "commands").is_dir():
      dirs.append(folder / ".claude" / "commands")
    if (folder / ".claude-plugin").is_dir() and (folder / "commands").is_dir():
      dirs.append(folder / "commands")
  prompts = repo / ".github" / "prompts"
  if prompts.is_dir():
    dirs.append(prompts)
  return sorted(set(dirs))


def _find_commands(repo: Path) -> list[FoundSkill]:
  found: list[FoundSkill] = []
  for folder in _command_dirs(repo):
    for path in sorted(folder.rglob("*.md")):
      meta, body = split_frontmatter(_text(path))
      stem = path.name.removesuffix(".prompt.md").removesuffix(".md")
      nested = path.parent.relative_to(folder).parts
      found.append(
        FoundSkill(
          name=slugify("-".join([*nested, stem])),
          description=_describe(meta, body) or f"The /{stem} command",
          kind=KIND_COMMAND,
          folder=path.parent.relative_to(repo).as_posix(),
          entry=path.relative_to(repo).as_posix(),
        )
      )
  return found


def repo_instruction_files(repo: Path) -> list[Path]:
  files = [repo / name for name in INSTRUCTION_FILES if (repo / name).is_file()]
  rules = repo / ".cursor" / "rules"
  if rules.is_dir():
    files.extend(sorted(p for p in rules.rglob("*") if p.suffix in (".md", ".mdc") and p.is_file())[:10])
  return files


def find_readme(repo: Path) -> Path | None:
  for name in README_NAMES:
    if (repo / name).is_file():
      return repo / name
  for path in repo.iterdir() if repo.is_dir() else []:
    if path.is_file() and path.name.lower().startswith("readme"):
      return path
  return None


def _repo_skill(repo: Path, name_hint: str, description_hint: str) -> FoundSkill:
  readme = find_readme(repo)
  instructions = repo_instruction_files(repo)
  entry = readme or (instructions[0] if instructions else None)
  description = description_hint
  if not description and readme is not None:
    description = first_paragraph(_text(readme))
  if not description and instructions:
    description = first_paragraph(split_frontmatter(_text(instructions[0]))[1])
  return FoundSkill(
    name=slugify(name_hint or repo.name, "repo"),
    description=description or f"Knowledge from the {name_hint or repo.name} repo",
    kind=KIND_REPO,
    folder="",
    entry=entry.relative_to(repo).as_posix() if entry else "",
    scripts=_scripts_in(repo, repo),
  )


def _unique_names(skills: list[FoundSkill]) -> list[FoundSkill]:
  seen: dict[str, int] = {}
  for skill in skills:
    base = skill.name
    if base in seen:
      parent = slugify(Path(skill.folder).parent.name or skill.kind)
      candidate = slugify(f"{parent}-{base}")
      while candidate in seen:
        seen[base] += 1
        candidate = f"{base}-{seen[base]}"
      skill.name = candidate
    seen.setdefault(skill.name, 1)
  return skills


def discover(repo: Path, *, name_hint: str = "", description_hint: str = "") -> list[FoundSkill]:
  """Every skill in the repo. A repo without SKILL.md or commands becomes one "repo" skill."""
  repo = Path(repo)
  skills = _find_skill_files(repo) + _find_commands(repo)
  if not skills:
    skills = [_repo_skill(repo, name_hint, description_hint)]
  skills.sort(key=lambda s: (s.kind != KIND_SKILL, s.entry.lower()))
  return _unique_names(skills)
