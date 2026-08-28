"""GET/PATCH /me — local single-user profile overlay."""

from __future__ import annotations

from fastapi import APIRouter

from maira.api.deps import get_overlay
from maira.api.schemas import UserPatch

router = APIRouter(tags=["user"])


@router.get("/me")
def get_me() -> dict:
  return get_overlay().user()


@router.patch("/me")
def patch_me(body: UserPatch) -> dict:
  return get_overlay().patch_user(body.model_dump(exclude_unset=True))
