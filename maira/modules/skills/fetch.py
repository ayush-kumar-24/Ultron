"""Download a repo into a folder: git when installed, else the GitHub zip."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from loguru import logger

from maira.modules.skills.source import SkillSource

MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 400 * 1024 * 1024
MAX_FILES = 30_000
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

Progress = Callable[[str], None]


class FetchError(RuntimeError):
  """The repo could not be downloaded."""


@dataclass(frozen=True)
class FetchResult:
  path: Path  # folder with the repo (or its subfolder)
  commit: str  # "" when unknown (zip download / local folder)
  ref: str  # the ref that worked ("" = default branch)


def _quiet(_message: str) -> None:
  pass


def rmtree(path: Path) -> None:
  """Delete a folder, including git's read-only files on Windows."""
  import stat  # noqa: PLC0415

  def make_writable(func, target, _exc) -> None:
    try:
      os.chmod(target, stat.S_IWRITE)
      func(target)
    except OSError:
      pass

  if not Path(path).exists():
    return
  if sys.version_info >= (3, 12):
    shutil.rmtree(path, onexc=make_writable)
  else:
    shutil.rmtree(path, onerror=make_writable)


def _git_env() -> dict[str, str]:
  env = dict(os.environ)
  env["GIT_TERMINAL_PROMPT"] = "0"  # a private/missing repo fails instead of asking for a password
  env["GCM_INTERACTIVE"] = "never"
  return env


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
  return subprocess.run(
    ["git", "-c", "core.symlinks=false", "-c", "advice.detachedHead=false", *args],
    cwd=str(cwd) if cwd else None,
    env=_git_env(),
    capture_output=True,
    text=True,
    timeout=timeout,
    check=False,
  )


def _ref_candidates(source: SkillSource) -> list[tuple[str, str]]:
  """(ref, subpath) pairs to try; a branch may contain '/' (tree/feature/x/path)."""
  if not source.ref:
    return [("", source.subpath)]
  pairs = [(source.ref, source.subpath)]
  parts = source.subpath.split("/") if source.subpath else []
  for i in range(1, len(parts) + 1):
    pairs.append(("/".join([source.ref, *parts[:i]]), "/".join(parts[i:])))
  return pairs


def _clone(source: SkillSource, dest: Path, progress: Progress) -> tuple[str, str, str]:
  errors: list[str] = []
  for ref, subpath in _ref_candidates(source):
    if dest.exists():
      rmtree(dest)
    args = ["clone", "--depth", "1", "--single-branch"]
    if ref:
      args += ["--branch", ref]
    progress(f"Cloning {source.clone_url}{f' ({ref})' if ref else ''}…")
    result = _run_git([*args, source.clone_url, str(dest)])
    if result.returncode == 0:
      return _head(dest), ref, subpath
    errors.append(result.stderr.strip())
    if ref and len(ref) >= 7 and all(c in "0123456789abcdef" for c in ref.lower()):
      # A commit: fetch just that commit.
      rmtree(dest)
      dest.mkdir(parents=True)
      steps = [["init", "-q"], ["remote", "add", "origin", source.clone_url],
               ["fetch", "--depth", "1", "origin", ref], ["checkout", "-q", "FETCH_HEAD"]]
      if all(_run_git(step, cwd=dest).returncode == 0 for step in steps):
        return _head(dest), ref, subpath
  raise FetchError(_explain_git_error("\n".join(errors)))


def _head(repo: Path) -> str:
  result = _run_git(["rev-parse", "HEAD"], cwd=repo, timeout=30)
  return result.stdout.strip() if result.returncode == 0 else ""


def _explain_git_error(text: str) -> str:
  lowered = text.lower()
  if "not found" in lowered or "could not read username" in lowered or "authentication" in lowered:
    return "Repo not found (or it is private). Check the name."
  if "remote branch" in lowered and "not found" in lowered:
    return "That branch or tag does not exist."
  if "could not resolve host" in lowered or "unable to access" in lowered:
    return "Can't reach GitHub. Check your internet connection."
  last = [line for line in text.splitlines() if line.strip()]
  return f"git failed: {last[-1] if last else 'unknown error'}"


def _download_zip(source: SkillSource, dest: Path, progress: Progress) -> tuple[str, str, str]:
  import httpx  # noqa: PLC0415

  errors: list[str] = []
  for ref, subpath in _ref_candidates(source):
    url = f"https://github.com/{source.owner}/{source.repo}/archive/{ref or 'HEAD'}.zip"
    progress(f"Downloading {url}…")
    try:
      data = bytearray()
      with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        if response.status_code == 404:
          errors.append("not found")
          continue
        response.raise_for_status()
        for chunk in response.iter_bytes():
          data.extend(chunk)
          if len(data) > MAX_DOWNLOAD_BYTES:
            raise FetchError("The repo is too big (over 200 MB).")
    except FetchError:
      raise
    except Exception as exc:  # noqa: BLE001
      raise FetchError(f"Can't download from GitHub: {exc}") from exc
    safe_extract_zip(bytes(data), dest)
    return "", ref, subpath
  raise FetchError("Repo not found (or it is private). Check the name.")


def safe_extract_zip(data: bytes, dest: Path) -> None:
  """Unpack a GitHub archive (one top folder) without escaping ``dest``."""
  dest.mkdir(parents=True, exist_ok=True)
  root = dest.resolve()
  total = 0
  with zipfile.ZipFile(io.BytesIO(data)) as archive:
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > MAX_FILES:
      raise FetchError(f"The repo has too many files (over {MAX_FILES}).")
    for member in members:
      if (member.external_attr >> 16) & 0o170000 == 0o120000:
        continue  # symlink
      parts = PurePosixPath(member.filename.replace("\\", "/")).parts[1:]  # drop "repo-branch/"
      if not parts or any(p in ("..", "") or ":" in p for p in parts) or parts[0].startswith("/"):
        continue
      total += member.file_size
      if total > MAX_TOTAL_BYTES:
        raise FetchError("The repo is too big once unpacked (over 400 MB).")
      target = (root / Path(*parts)).resolve()
      if not target.is_relative_to(root):
        continue
      target.parent.mkdir(parents=True, exist_ok=True)
      with archive.open(member) as src, open(target, "wb") as out:
        shutil.copyfileobj(src, out)


def _copy_tree(src: Path, dest: Path) -> None:
  total = 0
  count = 0
  for path in sorted(src.rglob("*")):
    rel = path.relative_to(src)
    if any(part in _SKIP_DIRS for part in rel.parts) or path.is_symlink() or not path.is_file():
      continue
    count += 1
    total += path.stat().st_size
    if count > MAX_FILES or total > MAX_TOTAL_BYTES:
      raise FetchError("That folder is too big to adopt as a skill.")
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _require_files(dest: Path) -> None:
  if not dest.is_dir() or not any(dest.iterdir()):
    raise FetchError("That repo or folder is empty.")


def fetch(source: SkillSource, dest: Path, progress: Progress | None = None) -> FetchResult:
  """Put the repo (only its subfolder, if one was given) into ``dest``."""
  say = progress or _quiet
  dest = Path(dest)
  rmtree(dest)
  work = dest.with_name(dest.name + ".download")
  rmtree(work)

  try:
    if source.is_local:
      if not Path(source.local_path).is_dir():
        raise FetchError(f"Folder not found: {source.local_path}")
      say(f"Copying {source.local_path}…")
      _copy_tree(Path(source.local_path), dest)
      _require_files(dest)
      return FetchResult(dest, "", "")
    if shutil.which("git"):
      commit, ref, subpath = _clone(source, work, say)
    else:
      commit, ref, subpath = _download_zip(source, work, say)

    rmtree(work / ".git")
    chosen = work
    if subpath:
      chosen = (work / subpath).resolve()
      if not chosen.is_relative_to(work.resolve()) or not chosen.is_dir():
        raise FetchError(f"Folder '{subpath}' is not in that repo.")
    _copy_tree(chosen, dest)
    _require_files(dest)
    logger.info("Fetched {} ({}) into {}", source.label, commit[:8] or ref or "default", dest)
    return FetchResult(dest, commit, ref)
  except subprocess.TimeoutExpired as exc:
    raise FetchError("Download took too long (over 5 minutes).") from exc
  except OSError as exc:
    raise FetchError(f"Could not save the repo: {exc}") from exc
  finally:
    rmtree(work)
