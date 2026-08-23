"""Loads YAML config from ``config/`` and the user data directory."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
  if not path.exists():
    return {}
  with path.open(encoding="utf-8") as handle:
    data = yaml.safe_load(handle)
  return data if isinstance(data, dict) else {}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
  merged = dict(base)
  for key, value in override.items():
    if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
      merged[key] = deep_merge(merged[key], value)
    else:
      merged[key] = value
  return merged
