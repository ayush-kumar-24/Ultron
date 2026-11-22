"""Hands and senses: voice capture, screen reading, focus sessions, and data controls."""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from maira.api.deps import (
  get_container,
  get_conversations,
  get_storage,
  get_tasks,
  get_work_sessions,
)
from maira.api.mapping import iso, task_to_api, title_from_text
from maira.api.sse import STREAM_HEADERS, sse

router = APIRouter(tags=["tools"])


# ---------------------------------------------------------------- task from a message
class MessageTaskIn(BaseModel):
  title: str | None = None
  projectId: str | None = None


@router.post("/messages/{message_id}/task", status_code=201)
def task_from_message(message_id: str, body: MessageTaskIn) -> dict:
  message = get_conversations().get_message(message_id)
  if message is None:
    raise HTTPException(status_code=404, detail="Message not found")
  title = (body.title or "").strip() or title_from_text(message.content)
  if not title:
    raise HTTPException(status_code=400, detail="There is nothing in that message to make a task from")
  task = get_tasks().create(title[:500], description=message.content[:5000], project_id=body.projectId)
  bus = get_container().try_resolve("event_bus")
  if bus is not None:
    bus.publish("planner.changed", {"reason": "web"})
  return task_to_api(task)


# ---------------------------------------------------------------- screen
@router.post("/screen/read")
def read_screen() -> dict:
  """Look at the screen once and return what is on it. Never called on a timer."""
  vision = get_container().try_resolve("vision")
  if vision is None:
    raise HTTPException(status_code=503, detail="Screen reading is not installed")
  ok, why = vision.is_available()
  if not ok:
    raise HTTPException(status_code=503, detail=why)
  reading = vision.read_screen()  # announces screen.read, which the registry counts
  if not reading.ok:
    raise HTTPException(status_code=503, detail=reading.summary)
  return {
    "ok": True,
    "summary": reading.summary,
    "text": reading.text,
    "lines": list(reading.lines),
    "width": reading.width,
    "height": reading.height,
    "display": reading.display,
    "engine": reading.engine,
    "details": list(reading.details),
  }


# ---------------------------------------------------------------- voice
class TranscribeIn(BaseModel):
  prompt: str | None = None


@router.post("/voice/transcribe")
def transcribe(body: TranscribeIn) -> StreamingResponse:  # noqa: ARG001 - prompt is a demo-only field
  """Record one utterance on this machine's microphone and stream back the transcript."""
  container = get_container()
  try:
    voice = container.resolve("voice")
  except Exception as exc:  # noqa: BLE001 - voice extras missing
    raise HTTPException(status_code=503, detail=f"Voice is not available: {exc}") from exc
  check = getattr(voice, "can_listen", None)
  ok, why = check() if callable(check) else (False, "Voice capture is not supported by this build")
  if not ok:
    raise HTTPException(status_code=503, detail=why)

  events: queue.Queue[tuple[str, str]] = queue.Queue()
  stop = threading.Event()

  def run() -> None:
    try:
      events.put(("done", voice.listen_once(should_stop=stop.is_set)))
    except Exception as exc:  # noqa: BLE001
      logger.warning("Voice capture failed: {}", exc)
      events.put(("error", str(exc) or "Could not hear anything"))

  def generate():
    threading.Thread(target=run, name="ultron-web-voice", daemon=True).start()
    yield sse({"type": "state", "state": "listening"})
    try:
      kind, payload = events.get()
      if kind == "done":
        if payload:
          yield sse({"type": "partial", "text": payload})
        yield sse({"type": "done", "payload": {"transcript": payload}})
      else:
        yield sse({"type": "error", "status": 503, "message": payload, "detail": payload})
    finally:
      stop.set()  # the browser cancelled: release the microphone

  return StreamingResponse(generate(), media_type="text/event-stream", headers=STREAM_HEADERS)


# ---------------------------------------------------------------- focus / work sessions
class SessionIn(BaseModel):
  type: str = "work"
  project: str | None = None
  minutes: int
  summary: str | None = None
  startedAt: str | None = None


def session_to_api(session) -> dict:
  return {
    "id": session.id,
    "type": session.type,
    "project": session.project,
    "start": iso(session.started_at),
    "minutes": session.minutes,
    "recorded": session.recorded,
    "summary": session.summary,
  }


@router.get("/sessions")
def list_sessions() -> list[dict]:
  return [session_to_api(item) for item in get_work_sessions().list_sessions()]


@router.post("/sessions", status_code=201)
def record_session(body: SessionIn) -> dict:
  if body.minutes <= 0 or body.minutes > 24 * 60:
    raise HTTPException(status_code=422, detail="A session needs between 1 minute and 24 hours")
  started = None
  if body.startedAt:
    try:
      started = datetime.fromisoformat(body.startedAt.replace("Z", "+00:00"))
    except ValueError as exc:
      raise HTTPException(status_code=422, detail="startedAt is not a valid time") from exc
    if started.tzinfo is None:
      started = started.replace(tzinfo=timezone.utc)
  session = get_work_sessions().record(
    type=body.type,
    project=(body.project or "").strip(),
    minutes=body.minutes,
    summary=(body.summary or "").strip(),
    started_at=started,
  )
  return session_to_api(session)


# ---------------------------------------------------------------- data controls
_USER_TABLES = (
  "messages",
  "conversations",
  "tasks",
  "notes",
  "automation_runs",
  "automations",
  "calendar_events",
  "notifications",
  "goals",
  "projects",
  "knowledge_items",
  "research_sessions",
  "agent_executions",
  "work_sessions",
)


@router.post("/system/reset")
def reset_demo() -> Response:
  # Live data has no "demo" to go back to; refusing is safer than guessing what to erase.
  raise HTTPException(status_code=409, detail="There is no demo data here - this is your real data.")


@router.post("/system/wipe", status_code=204)
def wipe() -> Response:
  """Delete the user's data from this device. Not an archive: the rows are gone."""
  container = get_container()
  storage = get_storage()

  # Memories go through the service so their vector embeddings are removed too.
  memory = container.try_resolve("memory")
  if memory is not None:
    for entry in memory.list_memories():
      try:
        memory.delete(entry.id)
      except Exception as exc:  # noqa: BLE001
        logger.warning("Could not delete memory {}: {}", entry.id, exc)

  with storage.transaction():
    for table in _USER_TABLES:
      storage.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
    storage.execute("DELETE FROM memories")

  leftover = {
    table: int(storage.fetchone(f"SELECT COUNT(*) FROM {table}")[0])  # noqa: S608
    for table in (*_USER_TABLES, "memories")
  }
  remaining = {table: count for table, count in leftover.items() if count}
  if remaining:
    # Verify before claiming success.
    logger.error("Wipe left rows behind: {}", remaining)
    raise HTTPException(status_code=500, detail="Some data could not be deleted. Nothing was hidden - try again.")

  brain = container.try_resolve("brain") if container.is_resolved("brain") else None
  fresh = getattr(brain, "new_conversation", None)
  if callable(fresh):
    fresh()  # the brain was pointing at a conversation that no longer exists
  bus = container.try_resolve("event_bus")
  if bus is not None:
    bus.publish("planner.changed", {"reason": "wipe"})
    bus.publish("automation.changed", {"reason": "wipe"})
  logger.info("All user data deleted on request")
  return Response(status_code=204)
