"""Calendar events and the one-line context strip."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from maira.api.deps import get_calendar
from maira.api.mapping import event_to_api
from maira.api.schemas import EventCreate

router = APIRouter(tags=["calendar"])


def _moment(value: str | None, *, field: str) -> datetime | None:
  if not value:
    return None
  try:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=f"Invalid {field} '{value}'") from exc
  return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.get("/events")
def list_events(
  from_: str | None = Query(default=None, alias="from"),
  to: str | None = Query(default=None),
) -> list[dict]:
  events = get_calendar().list_events(
    start=_moment(from_, field="from"),
    end=_moment(to, field="to"),
  )
  return [event_to_api(event) for event in events]


@router.post("/events", status_code=201)
def create_event(body: EventCreate) -> dict:
  start = _moment(body.start, field="start")
  if start is None:
    raise HTTPException(status_code=422, detail="An event needs a start time")
  event = get_calendar().create(
    body.title,
    start,
    _moment(body.end, field="end") or start,
    type=body.type or "meeting",
    project_id=body.projectId,
  )
  return event_to_api(event)


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: str) -> Response:
  if not get_calendar().delete(event_id):
    raise HTTPException(status_code=404, detail="Event not found")
  return Response(status_code=204)


@router.get("/calendar/context")
def calendar_context() -> dict:
  """What tomorrow looks like, in one sentence."""
  tomorrow = (datetime.now(timezone.utc).astimezone() + timedelta(days=1)).date()
  meetings = [
    event
    for event in get_calendar().list_events()
    if event.start_at.astimezone().date() == tomorrow and event.type == "meeting"
  ]
  busy = sum(
    max(0.0, (event.end_at - event.start_at).total_seconds() / 3600.0) for event in meetings
  )
  free = max(0, round(8 - busy))
  plural = "" if len(meetings) == 1 else "s"
  return {
    "text": f"You have {len(meetings)} meeting{plural} tomorrow and about {free} free hours.",
    "meetings": len(meetings),
    "freeHours": free,
  }
