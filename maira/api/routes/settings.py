"""GET /settings and PATCH /settings/:section — UI overlay, live model from Ollama config."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from maira.api.deps import get_overlay, get_settings
from maira.api.overlay import SETTINGS_SECTIONS
from maira.api.schemas import SettingsPatch

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings_payload() -> dict:
  live = get_settings()
  return get_overlay().settings(model=live.ollama.model)


@router.patch("/settings/{section}")
def patch_settings(section: str, body: SettingsPatch) -> dict:
  if section not in SETTINGS_SECTIONS:
    raise HTTPException(status_code=404, detail="Settings section not found")
  patch = body.as_dict()
  if section == "ai" and "model" in patch:
    # Display-only until a later phase reloads the LLM client.
    patch = {k: v for k, v in patch.items() if k != "model"}
  return get_overlay().patch_section(section, patch)
