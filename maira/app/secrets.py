"""Small secrets (e.g. the Gmail app password): Windows Credential Manager when available.

Falls back to data/secrets.json, which never leaves this PC (data/ is git-ignored).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from maira.shared.utils.paths import data_dir

_SERVICE = "Ultron"


def _file() -> Path:
  return data_dir() / "secrets.json"


def _keyring():
  try:
    import keyring  # noqa: PLC0415

    return keyring
  except ImportError:
    return None


def get_secret(name: str) -> str:
  keyring = _keyring()
  if keyring is not None:
    try:
      value = keyring.get_password(_SERVICE, name)
      if value:
        return value
    except Exception:  # noqa: BLE001 — no usable backend
      pass
  try:
    return str(json.loads(_file().read_text(encoding="utf-8")).get(name) or "")
  except (OSError, ValueError):
    return ""


def set_secret(name: str, value: str) -> None:
  keyring = _keyring()
  if keyring is not None:
    try:
      if value:
        keyring.set_password(_SERVICE, name, value)
      else:
        keyring.delete_password(_SERVICE, name)
      return
    except Exception:  # noqa: BLE001
      logger.info("Credential Manager unavailable; storing {} in data/secrets.json", name)
  path = _file()
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    data = {}
  if value:
    data[name] = value
  else:
    data.pop(name, None)
  path.write_text(json.dumps(data, indent=2), encoding="utf-8")
  if os.name != "nt":
    path.chmod(0o600)
