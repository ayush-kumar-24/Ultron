"""GET/PATCH /me - the local user. The name is the real setting (briefing.name)."""

from __future__ import annotations

from fastapi import APIRouter
from loguru import logger

from maira.api.deps import get_overlay
from maira.api.schemas import UserPatch

router = APIRouter(tags=["user"])


def _configured_name() -> str:
  try:
    from maira.app.user_config import UserConfig  # noqa: PLC0415

    return str(UserConfig().get("briefing.name") or "").strip()
  except Exception:  # noqa: BLE001
    return ""


def _initials(name: str) -> str:
  return "".join(part[0] for part in name.split() if part)[:2].upper()


@router.get("/me")
def get_me() -> dict:
  user = get_overlay().user()
  name = _configured_name()
  if name:
    # The greeting and the daily briefing use this name - keep the web UI on the same one.
    user = {**user, "name": name, "initials": _initials(name) or user.get("initials", "")}
  return user


@router.patch("/me")
def patch_me(body: UserPatch) -> dict:
  patch = body.model_dump(exclude_unset=True)
  name = (patch.get("name") or "").strip()
  if name:
    try:
      from maira.app.user_config import UserConfig  # noqa: PLC0415

      UserConfig().set("briefing.name", name)
    except Exception as exc:  # noqa: BLE001
      logger.warning("Could not save the name to settings: {}", exc)
  get_overlay().patch_user(patch)
  return get_me()
