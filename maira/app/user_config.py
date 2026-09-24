"""Read and write the user's overrides in data/config.yaml.

Only values the user changed are stored; everything else comes from
config/default.yaml, so updates to defaults still reach the user.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from maira.infrastructure.config.yaml_loader import deep_merge, load_yaml
from maira.shared.utils.paths import default_config_path, user_config_path

_MISSING = object()
# YAML 1.1 turns unquoted 07:30 into 450 and "on"/"no" into booleans: quote such strings.
_AMBIGUOUS = re.compile(r"^[\d:.\-+_ ]*$|^(?:y|n|yes|no|on|off|true|false|null|~)$", re.IGNORECASE)


class _Dumper(yaml.SafeDumper):
  pass


def _represent_str(dumper: yaml.SafeDumper, value: str):
  style = '"' if _AMBIGUOUS.match(value) else None
  return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def _dig(data: dict, path: str, default: Any = None) -> Any:
  node: Any = data
  for part in path.split("."):
    if not isinstance(node, dict) or part not in node:
      return default
    node = node[part]
  return node


class UserConfig:
  def __init__(self, user_path: Path | None = None, default_path: Path | None = None) -> None:
    self._user_path = user_path or user_config_path()
    self._default_path = default_path or default_config_path()
    self.reload()

  def reload(self) -> None:
    self._defaults = load_yaml(self._default_path)
    self._user = load_yaml(self._user_path)

  @property
  def path(self) -> Path:
    return self._user_path

  def get(self, path: str, fallback: Any = None) -> Any:
    """Effective value: the user's override, else the default."""
    value = _dig(self._user, path, _MISSING)
    if value is not _MISSING:
      return value
    return _dig(self._defaults, path, fallback)

  def is_overridden(self, path: str) -> bool:
    return _dig(self._user, path, _MISSING) is not _MISSING

  def set(self, path: str, value: Any) -> None:
    """Store an override and save. Setting the default value removes the override."""
    parts = path.split(".")
    if value == _dig(self._defaults, path, _MISSING):
      self._remove(parts)
    else:
      node = self._user
      for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
          child = {}
          node[part] = child
        node = child
      node[parts[-1]] = value
    self.save()

  def reset(self, path: str) -> None:
    self._remove(path.split("."))
    self.save()

  def merged(self) -> dict:
    return deep_merge(self._defaults, self._user)

  def save(self) -> None:
    self._user_path.parent.mkdir(parents=True, exist_ok=True)
    text = "# Your Ultron settings (changed from Settings in the app).\n"
    text += "# Anything not listed here uses config/default.yaml.\n"
    text += yaml.dump(self._user, Dumper=_Dumper, sort_keys=False, allow_unicode=True) if self._user else ""
    # Atomic replace: a crash mid-write never leaves a half-written config.
    fd, tmp = tempfile.mkstemp(dir=str(self._user_path.parent), suffix=".tmp")
    try:
      with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
      os.replace(tmp, self._user_path)
    except BaseException:
      Path(tmp).unlink(missing_ok=True)
      raise

  def _remove(self, parts: list[str]) -> None:
    trail = [self._user]
    for part in parts[:-1]:
      child = trail[-1].get(part)
      if not isinstance(child, dict):
        return
      trail.append(child)
    trail[-1].pop(parts[-1], None)
    # Drop empty parent sections.
    for depth in range(len(parts) - 1, 0, -1):
      if not trail[depth]:
        trail[depth - 1].pop(parts[depth - 1], None)
