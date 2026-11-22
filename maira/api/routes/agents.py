"""Agents - the live registry, execution history, and multi-agent orchestration."""

from __future__ import annotations

import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from maira.api.deps import get_executions, get_orchestrator, get_registry
from maira.api.mapping import iso
from maira.api.sse import STREAM_HEADERS, sse

router = APIRouter(tags=["agents"])

MAX_REQUEST_CHARS = 2000


class OrchestrateIn(BaseModel):
  request: str


def execution_to_api(execution) -> dict:
  return {
    "id": execution.id,
    "agentId": execution.agent_id,
    "task": execution.task,
    "status": execution.status,
    "startedAt": iso(execution.started_at),
    "endedAt": iso(execution.ended_at),
    "ms": execution.duration_ms,
    "error": execution.error,
  }


@router.get("/agents")
def list_agents() -> list[dict]:
  return get_registry().list_agents()


@router.get("/agents/{agent_id}")
def read_agent(agent_id: str) -> dict:
  agent = get_registry().describe(agent_id)
  if agent is None:
    raise HTTPException(status_code=404, detail="Agent not found")
  return agent


@router.get("/agents/{agent_id}/executions")
def agent_executions(agent_id: str) -> list[dict]:
  if get_registry().describe(agent_id) is None:
    raise HTTPException(status_code=404, detail="Agent not found")
  return [execution_to_api(item) for item in get_executions().list_executions(agent_id)]


@router.get("/executions")
def list_executions() -> list[dict]:
  return [execution_to_api(item) for item in get_executions().list_executions()]


@router.post("/agents/orchestrate")
def orchestrate(body: OrchestrateIn) -> StreamingResponse:
  request = (body.request or "").strip()
  if not request:
    raise HTTPException(status_code=400, detail="Describe what you want done")
  if len(request) > MAX_REQUEST_CHARS:
    raise HTTPException(status_code=422, detail="That request is too long")

  orchestrator = get_orchestrator()
  events: queue.Queue[tuple[str, object]] = queue.Queue()

  def on_step(index: int, agent: str, label: str, status: str) -> None:
    events.put(("step", {"type": "step", "index": index, "agent": agent, "label": label, "status": status}))

  def run() -> None:
    try:
      events.put(("done", orchestrator.run(request, on_step=on_step)))
    except Exception as exc:  # noqa: BLE001 - reported to the client as a stream error
      logger.warning("Orchestration failed: {}", exc)
      events.put(("error", str(exc) or "Orchestration failed"))

  def generate():
    threading.Thread(target=run, name="ultron-orchestrate", daemon=True).start()
    while True:
      kind, payload = events.get()
      if kind == "step":
        yield sse(payload)
      elif kind == "done":
        yield sse({"type": "done", "payload": payload})
        return
      else:
        yield sse({"type": "error", "status": 503, "message": str(payload), "detail": str(payload)})
        return

  return StreamingResponse(generate(), media_type="text/event-stream", headers=STREAM_HEADERS)
