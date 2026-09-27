"""File tools, limited to the folders the user allowed. Changes are asked first and backed up."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from maira.modules.agent.tools import Tool, ToolError, text_arg

MAX_READ_CHARS = 12_000
MAX_LISTED = 200
MAX_FOUND = 30
MAX_SCANNED = 100_000
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "appdata", "$recycle.bin", ".venv", "venv"}
_TEXT_WRITE_SUFFIXES = {
  ".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml", ".py", ".js", ".ts",
  ".css", ".ini", ".log", ".tsv", ".bat", ".ps1", ".sh", "",
}


def default_folders(home: Path | None = None) -> list[Path]:
  """Desktop, Documents and Downloads — including OneDrive's copies, where Windows 11 often moves them."""
  home = home or Path.home()
  bases = [home] + sorted(p for p in home.glob("OneDrive*") if p.is_dir())
  found = [base / name for name in ("Desktop", "Documents", "Downloads") for base in bases if (base / name).is_dir()]
  return found or [home]


def _size(num: int) -> str:
  for unit in ("B", "KB", "MB", "GB"):
    if num < 1024 or unit == "GB":
      return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
    num /= 1024
  return f"{num} B"


def _stamp() -> str:
  return datetime.now().strftime("%Y%m%d-%H%M%S")


def _read_docx(path: Path) -> str:
  with zipfile.ZipFile(path) as archive:
    xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
  xml = re.sub(r"</w:p>", "\n", xml)
  return re.sub(r"<[^>]+>", "", xml)


class FileAccess:
  def __init__(self, roots: list[Path], data_dir: Path) -> None:
    self.roots = [Path(os.path.expandvars(str(r))).expanduser().resolve() for r in roots]
    self.backups = data_dir / "agent" / "backups"
    self.trash = data_dir / "agent" / "trash"

  # --- paths -------------------------------------------------------------------------------

  def describe_roots(self) -> str:
    return ", ".join(str(r) for r in self.roots) or "(none)"

  def resolve(self, raw: str, *, must_exist: bool = False) -> Path:
    text = os.path.expandvars(raw.strip().strip("\"'")).replace("\\", "/")
    if not text:
      raise ToolError("No path given.")
    candidate = Path(text).expanduser()
    options: list[Path] = []
    if re.match(r"^[A-Za-z]:/", text) and not candidate.is_absolute():
      # A Windows drive path on another OS can never be inside the allowed folders.
      raise ToolError(f'"{raw}" is outside the folders Ultron may use: {self.describe_roots()}.')
    if candidate.is_absolute():
      options.append(candidate)
    else:
      first = candidate.parts[0].lower()
      for root in self.roots:
        # "Downloads/report.pdf" -> <home>/Downloads/report.pdf
        if root.name.lower() == first:
          options.append(root.joinpath(*candidate.parts[1:]))
      if ".." not in candidate.parts:  # never reinterpret an attempt to climb out of a folder
        options += [root / candidate for root in self.roots]
    for option in options:
      resolved = option.resolve()
      if self._allowed(resolved) and (not must_exist or resolved.exists()):
        return resolved
    if must_exist and any(self._allowed(o.resolve()) for o in options):
      raise ToolError(f'"{raw}" does not exist. Use find_files or list_folder to get the exact path.')
    raise ToolError(f'"{raw}" is outside the folders Ultron may use: {self.describe_roots()}.')

  def _allowed(self, path: Path) -> bool:
    return any(path == root or path.is_relative_to(root) for root in self.roots)

  # --- read-only ------------------------------------------------------------------------------

  def list_folder(self, args: dict[str, Any]) -> str:
    raw = text_arg(args, "path")
    if not raw:
      return "Allowed folders:\n" + "\n".join(str(r) for r in self.roots)
    folder = self.resolve(raw, must_exist=True)
    if not folder.is_dir():
      raise ToolError(f"{folder} is a file, not a folder.")
    entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = [f"{folder} ({len(entries)} items):"]
    for entry in entries[:MAX_LISTED]:
      try:
        if entry.is_dir():
          lines.append(f"[folder] {entry.name}")
        else:
          info = entry.stat()
          when = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d")
          lines.append(f"{entry.name}  ({_size(info.st_size)}, {when})")
      except OSError:
        continue
    if len(entries) > MAX_LISTED:
      lines.append(f"… and {len(entries) - MAX_LISTED} more")
    return "\n".join(lines)

  def find_files(self, args: dict[str, Any]) -> str:
    query = text_arg(args, "query").lower()
    if not query:
      raise ToolError("Say what to search for (part of the file name).")
    start = [self.resolve(text_arg(args, "folder"), must_exist=True)] if text_arg(args, "folder") else self.roots
    pattern = any(ch in query for ch in "*?")
    words = [w for w in re.split(r"[\s_\-.]+", query) if w]
    found: list[Path] = []
    scanned = 0
    for base in start:
      for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames + dirnames:
          scanned += 1
          lower = name.lower()
          if (fnmatch.fnmatch(lower, query) if pattern else all(w in lower for w in words)):
            found.append(Path(dirpath) / name)
        if scanned > MAX_SCANNED:
          break
    if not found:
      return f'No files matching "{query}" in {", ".join(str(s) for s in start)}.'

    def modified(path: Path) -> float:
      try:
        return path.stat().st_mtime
      except OSError:
        return 0.0

    found.sort(key=modified, reverse=True)
    lines = [f"Found {len(found)} (newest first):"]
    lines += [str(p) + ("  [folder]" if p.is_dir() else "") for p in found[:MAX_FOUND]]
    if len(found) > MAX_FOUND:
      lines.append(f"… and {len(found) - MAX_FOUND} more; narrow the search.")
    return "\n".join(lines)

  def read_file(self, args: dict[str, Any]) -> str:
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    if path.is_dir():
      raise ToolError(f"{path} is a folder; use list_folder.")
    suffix = path.suffix.lower()
    try:
      if suffix == ".docx":
        text = _read_docx(path)
      else:
        from maira.shared.utils.attachments import AttachmentError, read_attachment  # noqa: PLC0415

        try:
          text = read_attachment(path)
        except AttachmentError as exc:
          raise ToolError(str(exc)) from exc
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
      raise ToolError(f"Could not read {path.name}: {exc}") from exc
    if len(text) > MAX_READ_CHARS:
      text = text[:MAX_READ_CHARS] + f"\n…(shortened; file has {len(text)} characters)"
    return f"{path}:\n{text}"

  # --- changes (always asked first) -----------------------------------------------------------------

  def _backup(self, path: Path) -> Path:
    target = self.backups / _stamp() / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target

  def check_write(self, args: dict[str, Any]) -> None:
    path = self.resolve(text_arg(args, "path"))
    if path.suffix.lower() not in _TEXT_WRITE_SUFFIXES:
      raise ToolError(f"write_file makes text files only; {path.suffix} needs a skill (e.g. docx, xlsx).")
    if path.is_dir():
      raise ToolError(f"{path} is a folder.")

  def confirm_write(self, args: dict[str, Any]) -> str:
    path = self.resolve(text_arg(args, "path"))
    size = _size(len(text_arg(args, "content").encode()))
    verb = "Replace" if path.exists() else "Create"
    extra = " (the old version is backed up)" if path.exists() else ""
    return f"{verb} the file {path} ({size}){extra}"

  def write_file(self, args: dict[str, Any]) -> str:
    self.check_write(args)
    path = self.resolve(text_arg(args, "path"))
    backup = self._backup(path) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(args.get("content") or ""), encoding="utf-8")
    return f"Saved {path}" + (f" (backup: {backup})" if backup else "")

  def check_edit(self, args: dict[str, Any]) -> None:
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    find = str(args.get("find") or "")
    if not find:
      raise ToolError("Say which text to replace (find).")
    self.check_write({"path": str(path)})
    if find not in path.read_text(encoding="utf-8", errors="replace"):
      raise ToolError(f'"{find[:60]}" is not in {path.name}; read_file it first to copy the exact text.')

  def confirm_edit(self, args: dict[str, Any]) -> str:
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    count = path.read_text(encoding="utf-8", errors="replace").count(str(args.get("find")))
    old, new = str(args.get("find"))[:60], str(args.get("replace") or "")[:60]
    return f'In {path}, replace "{old}" with "{new}" ({count} place{"s" if count != 1 else ""}; backed up first)'

  def edit_file(self, args: dict[str, Any]) -> str:
    self.check_edit(args)
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    text = path.read_text(encoding="utf-8", errors="replace")
    count = text.count(str(args["find"]))
    backup = self._backup(path)
    path.write_text(text.replace(str(args["find"]), str(args.get("replace") or "")), encoding="utf-8")
    return f"Replaced {count} place(s) in {path} (backup: {backup})"

  def _move_paths(self, args: dict[str, Any]) -> tuple[Path, Path]:
    source = self.resolve(text_arg(args, "source"), must_exist=True)
    destination = self.resolve(text_arg(args, "destination"))
    if destination.is_dir():
      destination = destination / source.name
    if destination.exists():
      raise ToolError(f"{destination} already exists; choose another name.")
    return source, destination

  def check_move(self, args: dict[str, Any]) -> None:
    self._move_paths(args)

  def confirm_move(self, args: dict[str, Any]) -> str:
    source, destination = self._move_paths(args)
    verb = "Copy" if args.get("copy") else "Move"
    return f"{verb} {source} → {destination}"

  def move_file(self, args: dict[str, Any]) -> str:
    source, destination = self._move_paths(args)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if args.get("copy"):
      if source.is_dir():
        shutil.copytree(source, destination)
      else:
        shutil.copy2(source, destination)
      return f"Copied to {destination}"
    shutil.move(str(source), str(destination))
    return f"Moved to {destination}"

  def check_delete(self, args: dict[str, Any]) -> None:
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    if path in self.roots:
      raise ToolError("Ultron will not delete one of its allowed folders itself.")

  def confirm_delete(self, args: dict[str, Any]) -> str:
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    what = "folder" if path.is_dir() else "file"
    return f"Delete the {what} {path} (it goes to the Recycle Bin, so it can be restored)"

  def delete_file(self, args: dict[str, Any]) -> str:
    self.check_delete(args)
    path = self.resolve(text_arg(args, "path"), must_exist=True)
    try:
      from send2trash import send2trash  # noqa: PLC0415

      send2trash(str(path))
      return f"Moved {path} to the Recycle Bin"
    except ImportError:
      target = self.trash / f"{_stamp()}_{path.name}"
      target.parent.mkdir(parents=True, exist_ok=True)
      shutil.move(str(path), str(target))
      return f"Moved {path} to Ultron's trash: {target}"

  def make_folder(self, args: dict[str, Any]) -> str:
    path = self.resolve(text_arg(args, "path"))
    path.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {path}"

  # --- the tools ----------------------------------------------------------------------------------

  def tools(self) -> list[Tool]:
    path = {"type": "string", "description": "Full path, or a path inside an allowed folder like Downloads/report.pdf"}
    return [
      Tool("list_folder", "List what is inside a folder. With no path, lists the allowed folders.",
           {"path": path}, self.list_folder),
      Tool("find_files", "Search file and folder names (all words must appear; * and ? work).",
           {"query": {"type": "string", "description": "Words from the file name"},
            "folder": {"type": "string", "description": "Optional folder to search in"}},
           self.find_files, required=("query",)),
      Tool("read_file", "Read a text, PDF, Word (.docx) or image file (images and scans are OCR'd).",
           {"path": path}, self.read_file, required=("path",)),
      Tool("write_file", "Create or replace a text file (txt, md, csv, json, html, code…).",
           {"path": path, "content": {"type": "string", "description": "The whole file content"}},
           self.write_file, required=("path", "content"), confirm=self.confirm_write, check=self.check_write),
      Tool("edit_file", "Replace exact text inside a text file.",
           {"path": path, "find": {"type": "string"}, "replace": {"type": "string"}},
           self.edit_file, required=("path", "find", "replace"), confirm=self.confirm_edit, check=self.check_edit),
      Tool("move_file", "Move, rename or copy a file or folder.",
           {"source": path, "destination": {"type": "string", "description": "New path or target folder"},
            "copy": {"type": "boolean", "description": "true to copy instead of move"}},
           self.move_file, required=("source", "destination"), confirm=self.confirm_move, check=self.check_move),
      Tool("delete_file", "Delete a file or folder (to the Recycle Bin).",
           {"path": path}, self.delete_file, required=("path",), confirm=self.confirm_delete, check=self.check_delete),
      Tool("make_folder", "Create a folder.", {"path": path}, self.make_folder, required=("path",)),
    ]
