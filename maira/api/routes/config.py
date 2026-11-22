"""The real settings - the same list, file and rules as the desktop Settings screen.

Reads and writes data/config.yaml through UserConfig using the desktop's own schema
(maira.app.settings_schema), so a change made in the browser is the same change the
desktop app would make. Settings marked `restart` apply after Ultron restarts; the
rest are applied to the running services immediately.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from maira.api.deps import get_container, get_settings
from maira.app.settings_schema import CATEGORIES, FIELDS, Field, field_by_path
from maira.app.user_config import UserConfig

router = APIRouter(tags=["config"])

# Desktop-only categories: "status" is a live panel, not settings.
_HIDDEN_CATEGORIES = {"status"}
_PENDING_KEY = "config_restart_pending"


class ConfigPatch(BaseModel):
  path: str
  value: Any = None


def _pending() -> set[str]:
  container = get_container()
  pending = container.try_resolve(_PENDING_KEY)
  if pending is None:
    pending = set()
    container.register_instance(_PENDING_KEY, pending)
  return pending


def _installed_models() -> list[str]:
  try:
    from maira.modules.voice.voice_tools import ollama_models  # noqa: PLC0415

    host = str(UserConfig().get("ollama.host") or get_settings().ollama.host)
    return ollama_models(host) or []
  except Exception:  # noqa: BLE001
    return []


def _options(f: Field, models: list[str]) -> list[dict[str, Any]]:
  options = [{"value": value, "label": label} for value, label in f.options]
  if f.path in {"ollama.model", "agent.model"}:
    known = {o["value"] for o in options}
    options += [{"value": name, "label": name} for name in models if name not in known]
  return options


def _field_to_api(f: Field, config: UserConfig, models: list[str]) -> dict[str, Any]:
  return {
    "path": f.path,
    "label": f.label,
    "kind": f.kind,
    "category": f.category,
    "help": f.help,
    "value": config.get(f.path),
    "options": _options(f, models),
    "editable": f.editable,
    "min": f.minimum,
    "max": f.maximum,
    "step": f.step,
    "restart": f.restart,
    "visibleWhen": {"path": f.visible_when[0], "values": list(f.visible_when[1])} if f.visible_when else None,
    # A file path can only be chosen with the desktop's file picker.
    "readOnly": f.kind == "file",
  }


@router.get("/config")
def read_config() -> dict:
  config = UserConfig()
  models = _installed_models()
  return {
    "categories": [
      {"id": key, "label": label}
      for key, label in CATEGORIES
      if key not in _HIDDEN_CATEGORIES and any(f.category == key for f in FIELDS)
    ],
    "fields": [_field_to_api(f, config, models) for f in FIELDS if f.category not in _HIDDEN_CATEGORIES],
    "restartPending": sorted(_pending()),
    "file": str(config.path),
  }


def _coerce(f: Field, value: Any) -> Any:
  try:
    if f.kind == "bool":
      if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
      return bool(value)
    if f.kind == "int":
      number = int(float(value))
    elif f.kind == "float":
      number = round(float(value), 4)
    else:
      number = None
  except (TypeError, ValueError) as exc:
    raise HTTPException(status_code=422, detail=f"{f.label} needs a number") from exc
  if number is not None:
    if number < f.minimum or number > f.maximum:
      raise HTTPException(status_code=422, detail=f"{f.label} must be between {f.minimum:g} and {f.maximum:g}")
    return number

  text = str(value if value is not None else "").strip()
  if f.kind == "time":
    parts = text.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60):
      raise HTTPException(status_code=422, detail=f"{f.label} must be a time like 08:00")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
  if f.kind == "choice" and not f.editable and f.path not in {"ollama.model", "agent.model"}:
    allowed = {str(option) for option, _label in f.options}
    if allowed and text not in allowed:
      raise HTTPException(status_code=422, detail=f"{text!r} is not an option for {f.label}")
  if len(text) > 500:
    raise HTTPException(status_code=422, detail=f"{f.label} is too long")
  return text


def _apply_live(path: str, value: Any) -> bool:
  """Change the running services for settings that do not need a restart."""
  container = get_container()
  if path.startswith("agent."):
    agent = container.try_resolve("agent") if container.is_resolved("agent") else None
    key = path.split(".", 1)[1]
    if agent is not None and key in {"enabled", "auto_detect", "model", "max_steps"}:
      setattr(agent, key, value)
    return True
  if path.startswith("skills."):
    skills = container.try_resolve("skills")
    key = path.split(".", 1)[1]
    if skills is not None and hasattr(skills, key):
      setattr(skills, key, value)
    return True
  if path == "briefing.name":
    overlay = container.try_resolve("overlay")
    if overlay is not None and value:
      overlay.patch_user({"name": str(value)})
    return True
  if path == "desktop.enabled":
    desktop = container.try_resolve("desktop")
    if desktop is not None and hasattr(desktop, "set_enabled"):
      desktop.set_enabled(bool(value))
    return False  # the desktop also reads it at start; still flag the restart
  return False


@router.patch("/config")
def write_config(body: ConfigPatch) -> dict:
  try:
    f = field_by_path(body.path)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail="Unknown setting") from exc
  if f.category in _HIDDEN_CATEGORIES or f.kind == "file":
    raise HTTPException(status_code=409, detail="Change this one in the desktop app's Settings")

  value = _coerce(f, body.value)
  config = UserConfig()
  config.set(f.path, value)
  for extra_path, extra_value in (f.also_sets(value) if f.also_sets else {}).items():
    config.set(extra_path, extra_value)

  applied = False
  try:
    applied = _apply_live(f.path, value)
  except Exception as exc:  # noqa: BLE001 - saved; it will apply on restart instead
    logger.warning("Saved {} but could not apply it now: {}", f.path, exc)

  pending = _pending()
  if f.restart:
    pending.add(f.path)
  logger.info("Setting changed from the web: {} = {!r}", f.path, value)
  return {
    "path": f.path,
    "value": UserConfig().get(f.path),
    "restart": f.restart,
    "appliedNow": applied and not f.restart,
    "restartPending": sorted(pending),
  }
