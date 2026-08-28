"""Notification centre — what Ultron did while you were away."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from maira.api.deps import get_notifications
from maira.api.mapping import notification_to_api
from maira.api.schemas import NotificationPatch

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications() -> list[dict]:
  return [notification_to_api(item) for item in get_notifications().list_notifications()]


@router.patch("/notifications/{notification_id}")
def update_notification(notification_id: str, body: NotificationPatch) -> dict:
  notifications = get_notifications()
  if body.read is None:
    existing = notifications.get(notification_id)
    if existing is None:
      raise HTTPException(status_code=404, detail="Notification not found")
    return notification_to_api(existing)

  updated = notifications.set_read(notification_id, body.read)
  if updated is None:
    raise HTTPException(status_code=404, detail="Notification not found")
  return notification_to_api(updated)


@router.post("/notifications/read-all", status_code=204)
def read_all() -> Response:
  get_notifications().mark_all_read()
  return Response(status_code=204)


@router.delete("/notifications/{notification_id}", status_code=204)
def delete_notification(notification_id: str) -> Response:
  if not get_notifications().delete(notification_id):
    raise HTTPException(status_code=404, detail="Notification not found")
  return Response(status_code=204)
