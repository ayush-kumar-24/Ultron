"""A quick safety read of a skill's scripts, shown before the user allows them to run."""

from __future__ import annotations

import re
from pathlib import Path

_CHECKS: list[tuple[str, re.Pattern]] = [
  ("runs other programs", re.compile(
    r"\bsubprocess\b|os\.system|os\.popen|child_process|\bexecSync\b|\bspawn\(|Start-Process|"
    r"Invoke-Expression|\biex\b|\bShellExecute", re.IGNORECASE)),
  ("uses the internet", re.compile(
    r"\brequests\.(get|post|put)|urllib\.request|\bhttpx\b|http\.client|\bfetch\(|\bcurl\b|\bwget\b|"
    r"Invoke-WebRequest|Invoke-RestMethod|\bsocket\.|\baxios\b", re.IGNORECASE)),
  ("deletes files", re.compile(
    r"rmtree|os\.remove|os\.unlink|\.unlink\(|\brm\s+-[a-z]*r|Remove-Item|\bdel\s+/|fs\.rm|rimraf",
    re.IGNORECASE)),
  ("changes system settings", re.compile(
    r"\breg\s+add|Set-ItemProperty|schtasks|crontab|HKEY_|winreg|systemctl|\bsudo\b|chmod\s+777",
    re.IGNORECASE)),
  ("runs hidden or generated code", re.compile(
    r"\beval\(|\bexec\(|-EncodedCommand|marshal\.loads|FromBase64String|base64\s+-d|atob\(",
    re.IGNORECASE)),
  ("reads passwords or keys", re.compile(
    r"\.ssh|id_rsa|\.aws/credentials|keyring|Login Data|\bcookies\.sqlite|\bpasswords?\b|api[_-]?key",
    re.IGNORECASE)),
]
_BINARY = {".exe", ".dll", ".so", ".dylib", ".msi", ".scr", ".com", ".jar"}


def scan_skill(folder: Path, scripts: list[str]) -> list[str]:
  """Plain-English warnings like "runs other programs (scripts/a.py, scripts/b.sh)"."""
  hits: dict[str, list[str]] = {}
  for rel in scripts:
    try:
      text = (folder / rel).read_text(encoding="utf-8", errors="replace")[:500_000]
    except OSError:
      continue
    for label, pattern in _CHECKS:
      if pattern.search(text):
        hits.setdefault(label, []).append(rel)
  warnings = []
  for label, _ in _CHECKS:
    files = hits.get(label)
    if files:
      shown = ", ".join(files[:3]) + (f" +{len(files) - 3} more" if len(files) > 3 else "")
      warnings.append(f"{label} ({shown})")
  binaries = [p.name for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in _BINARY][:3]
  if binaries:
    warnings.append(f"contains programs ({', '.join(binaries)})")
  return warnings
