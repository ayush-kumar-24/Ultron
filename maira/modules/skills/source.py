"""Understand what the user pasted: owner/repo, a GitHub URL, or a local folder."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_NAME = r"[A-Za-z0-9_.-]+"
_SHORT = re.compile(rf"^({_NAME})/({_NAME})$")
_SSH = re.compile(rf"^git@github\.com:({_NAME})/({_NAME}?)(?:\.git)?/?$")


class SourceError(ValueError):
  """The text is not a GitHub repo or folder Ultron can read."""


@dataclass(frozen=True)
class SkillSource:
  owner: str = ""
  repo: str = ""
  ref: str = ""  # branch, tag or commit; "" = the default branch
  subpath: str = ""  # only this folder of the repo
  local_path: str = ""  # a folder on this PC instead of GitHub

  @property
  def is_local(self) -> bool:
    return bool(self.local_path)

  @property
  def clone_url(self) -> str:
    return f"https://github.com/{self.owner}/{self.repo}.git"

  @property
  def web_url(self) -> str:
    if self.is_local:
      return self.local_path
    url = f"https://github.com/{self.owner}/{self.repo}"
    if self.ref or self.subpath:
      url += f"/tree/{self.ref or 'HEAD'}"
      if self.subpath:
        url += f"/{self.subpath}"
    return url

  @property
  def label(self) -> str:
    if self.is_local:
      return Path(self.local_path).name
    base = f"{self.owner}/{self.repo}"
    return f"{base}/{self.subpath}" if self.subpath else base

  def to_dict(self) -> dict:
    return {
      "owner": self.owner,
      "repo": self.repo,
      "ref": self.ref,
      "subpath": self.subpath,
      "local_path": self.local_path,
    }

  @classmethod
  def from_dict(cls, data: dict) -> SkillSource:
    return cls(**{k: str(data.get(k) or "") for k in ("owner", "repo", "ref", "subpath", "local_path")})


def _clean_repo(name: str) -> str:
  return name[:-4] if name.endswith(".git") else name


def _safe_subpath(parts: list[str]) -> str:
  clean = [p for p in parts if p not in ("", ".")]
  if any(p == ".." for p in clean):
    raise SourceError("That folder path is not allowed.")
  return "/".join(clean)


def parse_source(text: str) -> SkillSource:
  """Accepts owner/repo, github.com URLs (tree/blob links too), git@ URLs, or a local folder."""
  raw = text.strip()
  while raw and (raw[0] in "<\"'`(" or raw[-1] in ">\"'`),."):
    raw = raw[1:] if raw[0] in "<\"'`(" else raw[:-1]
  if not raw:
    raise SourceError("Give a GitHub repo, like anthropics/skills.")

  local = Path(raw).expanduser()
  looks_like_path = raw.startswith(("~", ".", "/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", raw)
  if looks_like_path or (local.is_absolute() and local.exists()):
    if not local.is_dir():
      raise SourceError(f"Folder not found: {raw}")
    return SkillSource(local_path=str(local.resolve()))

  match = _SSH.match(raw)
  if match:
    return SkillSource(owner=match.group(1), repo=_clean_repo(match.group(2)))

  match = _SHORT.match(raw)
  if match and "." not in match.group(1):
    return SkillSource(owner=match.group(1), repo=_clean_repo(match.group(2)))

  url = raw if "://" in raw else f"https://{raw}"
  parsed = urlparse(url)
  host = parsed.netloc.lower().removeprefix("www.")
  if host != "github.com":
    raise SourceError("Only GitHub repos are supported (github.com/owner/repo).")
  parts = [p for p in parsed.path.split("/") if p]
  if len(parts) < 2:
    raise SourceError("That link has no repo in it. Use github.com/owner/repo.")
  owner, repo = parts[0], _clean_repo(parts[1])
  if not re.fullmatch(_NAME, owner) or not re.fullmatch(_NAME, repo):
    raise SourceError("That doesn't look like a GitHub repo name.")
  rest = parts[2:]
  if len(rest) >= 2 and rest[0] in ("tree", "blob"):
    ref = rest[1]
    sub = rest[2:]
    if rest[0] == "blob" and sub:
      sub = sub[:-1]  # a file link (e.g. .../SKILL.md) means its folder
    return SkillSource(owner=owner, repo=repo, ref=ref, subpath=_safe_subpath(sub))
  return SkillSource(owner=owner, repo=repo)
