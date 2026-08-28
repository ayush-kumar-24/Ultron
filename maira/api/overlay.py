"""JSON overlay for /me and /settings — UI prefs the frozen YAML settings don't cover."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_USER: dict[str, Any] = {
  "id": "local",
  "name": "Ayush",
  "initials": "AY",
  "email": "",
  "timezone": "Asia/Kolkata",
  "language": "English",
  "role": "",
}

DEFAULT_SETTINGS: dict[str, Any] = {
  "general": {
    "theme": "dark",
    "language": "English",
    "timezone": "Asia/Kolkata",
    "dateFormat": "DD MMM YYYY",
  },
  "ai": {
    "responseStyle": "concise",
    "model": "llama3.2:latest",
    "cloudEscalation": False,
    "temperature": 0.3,
    "reasoning": "balanced",
    "defaultAgent": "a_core",
  },
  "memory": {
    "enabled": True,
    "automatic": True,
    "review": "weekly",
    "retentionDays": 365,
  },
  "voice": {
    "voice": "en_US-lessac-medium",
    "speed": 1.0,
    "wakeWord": True,
    "pushToTalk": "Alt+Space",
    "interruptions": True,
  },
  "notifications": {
    "reminders": True,
    "tasks": True,
    "agents": True,
    "automations": True,
    "quietHours": "23:00–08:00",
  },
  "privacy": {
    "localOnly": True,
    "telemetry": False,
    "recordingDefault": False,
  },
}

SETTINGS_SECTIONS = tuple(DEFAULT_SETTINGS.keys())


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
  merged = deepcopy(base)
  for key, value in override.items():
    if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
      merged[key] = _deep_merge(merged[key], value)
    else:
      merged[key] = value
  return merged


class OverlayStore:
  """Tiny JSON file for profile + settings sections. Thread-safe enough for local use."""

  def __init__(self, path: Path) -> None:
    self._path = path
    self._lock = threading.Lock()

  def read(self) -> dict[str, Any]:
    with self._lock:
      return self._read_unlocked()

  def user(self) -> dict[str, Any]:
    data = self.read()
    return _deep_merge(DEFAULT_USER, data.get("user") or {})

  def settings(self, *, model: str | None = None) -> dict[str, Any]:
    data = self.read()
    merged = _deep_merge(DEFAULT_SETTINGS, data.get("settings") or {})
    if model:
      merged["ai"]["model"] = model
    return merged

  def patch_user(self, patch: dict[str, Any]) -> dict[str, Any]:
    with self._lock:
      data = self._read_unlocked()
      user = _deep_merge(DEFAULT_USER, data.get("user") or {})
      for key, value in patch.items():
        if value is not None:
          user[key] = value
      if patch.get("name") and not patch.get("initials"):
        parts = str(user["name"]).split()
        user["initials"] = "".join(p[0] for p in parts if p)[:2].upper() or user["initials"]
      data["user"] = user
      self._write_unlocked(data)
      return _deep_merge(DEFAULT_USER, user)

  def patch_section(self, section: str, patch: dict[str, Any]) -> dict[str, Any]:
    if section not in SETTINGS_SECTIONS:
      raise KeyError(section)
    with self._lock:
      data = self._read_unlocked()
      settings = _deep_merge(DEFAULT_SETTINGS, data.get("settings") or {})
      settings[section] = {**settings[section], **patch}
      data["settings"] = settings
      self._write_unlocked(data)
      return deepcopy(settings[section])

  def _read_unlocked(self) -> dict[str, Any]:
    if not self._path.exists():
      return {}
    try:
      raw = json.loads(self._path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
      logger.warning("Could not read overlay {}: {}", self._path, exc)
      return {}
    return raw if isinstance(raw, dict) else {}

  def _write_unlocked(self, data: dict[str, Any]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(self._path)
