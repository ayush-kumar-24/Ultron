"""Research - sessions, the live run, and turning a report into tasks or knowledge."""

from __future__ import annotations

import queue
import threading

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from maira.api.deps import get_container, get_knowledge, get_registry, get_research, get_tasks
from maira.api.mapping import iso, knowledge_to_api, task_to_api
from maira.api.sse import STREAM_HEADERS, sse
from maira.modules.research import RESEARCH_STEPS

router = APIRouter(tags=["research"])

MAX_QUERY_CHARS = 1000


class ResearchIn(BaseModel):
  query: str
  projectId: str | None = None


def session_to_api(session) -> dict:
  return {
    "id": session.id,
    "query": session.query,
    "status": session.status,
    "step": session.step,
    "sources": session.sources,
    "projectId": session.project_id,
    "report": session.report,
    "error": session.error,
    "createdAt": iso(session.created_at),
    "updatedAt": iso(session.updated_at),
  }


def _session_or_404(session_id: str):
  session = get_research().repository.get(session_id)
  if session is None:
    raise HTTPException(status_code=404, detail="Research not found")
  return session


@router.get("/research")
def list_research() -> list[dict]:
  return [session_to_api(item) for item in get_research().repository.list_sessions()]


@router.get("/research/{session_id}")
def read_research(session_id: str) -> dict:
  return session_to_api(_session_or_404(session_id))


@router.delete("/research/{session_id}", status_code=204)
def delete_research(session_id: str) -> Response:
  if not get_research().repository.delete(session_id):
    raise HTTPException(status_code=404, detail="Research not found")
  return Response(status_code=204)


@router.post("/research/stream")
def research_stream(body: ResearchIn) -> StreamingResponse:
  query = (body.query or "").strip()
  if not query:
    raise HTTPException(status_code=400, detail="Say what you want researched")
  if len(query) > MAX_QUERY_CHARS:
    raise HTTPException(status_code=422, detail="That question is too long")

  research = get_research()
  registry = get_registry()
  session = research.start(query, project_id=body.projectId)
  events: queue.Queue[tuple[str, object]] = queue.Queue()

  def on_step(index: int, label: str, sources: int) -> None:
    events.put(("step", {"type": "step", "step": index, "label": label, "sources": sources}))

  def run() -> None:
    # The run outlives the request: closing the tab must not lose the research.
    try:
      with registry.track("research", query):
        finished = research.run(session.id, on_step=on_step)
        if finished.status != "done":
          raise RuntimeError(finished.error or "Research failed")
      events.put(("done", finished))
    except Exception as exc:  # noqa: BLE001
      events.put(("error", str(exc) or "Research failed"))
    _notify(finished_query=query, session_id=session.id)

  def generate():
    yield sse({"type": "session", "session": session_to_api(session)})
    threading.Thread(target=run, name="ultron-research", daemon=True).start()
    while True:
      kind, payload = events.get()
      if kind == "step":
        yield sse(payload)
      elif kind == "done":
        api = session_to_api(payload)
        yield sse({"type": "step", "step": len(RESEARCH_STEPS), "label": "Done", "sources": api["sources"]})
        yield sse({"type": "report", "report": api["report"]})
        yield sse({"type": "done", "payload": api})
        return
      else:
        yield sse({"type": "error", "status": 503, "message": str(payload), "detail": str(payload)})
        return

  return StreamingResponse(generate(), media_type="text/event-stream", headers=STREAM_HEADERS)


def _notify(*, finished_query: str, session_id: str) -> None:
  """Leave a notification so research that finished in the background is not missed."""
  container = get_container()
  notifications = container.try_resolve("notification_repository")
  session = get_research().repository.get(session_id)
  if notifications is None or session is None:
    return
  if session.status == "done":
    created = notifications.create(
      type="agent", title="Research complete", body=f"{finished_query} - {session.sources} local source(s)"
    )
  else:
    created = notifications.create(
      type="agent", title="Research failed", body=f"{finished_query} - {session.error or 'did not finish'}"
    )
  bus = container.try_resolve("event_bus")
  if bus is not None:
    bus.publish("notification", {"id": created.id, "type": created.type, "title": created.title, "body": created.body})


@router.post("/research/{session_id}/tasks", status_code=201)
def research_to_tasks(session_id: str) -> list[dict]:
  session = _session_or_404(session_id)
  actions = (session.report or {}).get("nextActions") or []
  if not actions:
    raise HTTPException(status_code=422, detail="This report has no next actions to turn into tasks")
  tasks = get_tasks()
  created = [
    tasks.create(str(action)[:500], project_id=session.project_id, tags=["research"]) for action in actions
  ]
  bus = get_container().try_resolve("event_bus")
  if bus is not None:
    bus.publish("planner.changed", {"reason": "research"})
  return [task_to_api(task) for task in created]


@router.post("/research/{session_id}/knowledge", status_code=201)
def research_to_knowledge(session_id: str) -> dict:
  session = _session_or_404(session_id)
  report = session.report
  if not report:
    raise HTTPException(status_code=422, detail="This research has no report to save")
  lines = [report.get("summary", ""), "", "Key findings:"]
  lines += [f"- {item}" for item in report.get("findings", [])]
  if report.get("recommendations"):
    lines += ["", "Recommendations:"] + [f"- {item}" for item in report["recommendations"]]
  item = get_knowledge().create(
    f"Research: {session.query}"[:200],
    type="note",
    source="Research",
    body="\n".join(lines),
    tags=["research"],
    project_id=session.project_id,
  )
  return knowledge_to_api(item)
