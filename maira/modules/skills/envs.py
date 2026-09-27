"""Per-pack Python environments, so a skill's packages never touch Ultron's own."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# import name -> pip package, for the common cases where they differ
PIP_NAMES = {
  "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "docx": "python-docx", "pptx": "python-pptx",
  "fitz": "pymupdf", "bs4": "beautifulsoup4", "sklearn": "scikit-learn", "dateutil": "python-dateutil",
  "dotenv": "python-dotenv", "magic": "python-magic", "Crypto": "pycryptodome", "skimage": "scikit-image",
  "attr": "attrs", "google": "google-api-python-client", "win32com": "pywin32", "pdfplumber": "pdfplumber",
}
_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def pip_name(module: str) -> str:
  return PIP_NAMES.get(module, module)


def env_python(envs_dir: Path, pack_id: str) -> Path:
  folder = envs_dir / pack_id
  return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_env(envs_dir: Path, pack_id: str, timeout: int = 300) -> Path:
  """Create the pack's venv (it can still import Ultron's installed packages)."""
  python = env_python(envs_dir, pack_id)
  if python.exists():
    return python
  envs_dir.mkdir(parents=True, exist_ok=True)
  subprocess.run(
    [sys.executable, "-m", "venv", "--system-site-packages", str(envs_dir / pack_id)],
    check=True, capture_output=True, timeout=timeout,
  )
  return python


def pip_install(envs_dir: Path, pack_id: str, package: str, timeout: int = 900) -> tuple[bool, str]:
  if not _PACKAGE.match(package):
    return False, f"'{package}' is not a valid package name."
  try:
    python = ensure_env(envs_dir, pack_id)
    done = subprocess.run(
      [str(python), "-m", "pip", "install", "--disable-pip-version-check", package],
      capture_output=True, text=True, timeout=timeout, check=False,
      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
  except (OSError, subprocess.SubprocessError) as exc:
    return False, str(exc)
  tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-3:])
  return done.returncode == 0, tail
