"""Phase 3 HTTP API — projects, goals, knowledge, activity, insights, search."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maira.api.overlay import OverlayStore
from maira.api.routes.stream import ActivityStream
from maira.api.server import create_app
from maira.app.container import Container
from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRepository,
  AutomationRunRepository,
  CalendarEventRepository,
  ConversationRepository,
  GoalRepository,
  KnowledgeRepository,
  MemoryRepository,
  NotificationRepository,
  ProjectRepository,
  TaskRepository,
)
from maira.modules.automation.service import AutomationService
from maira.modules.memory.service import MemoryService


class FakeLlm:
  model = "test-model"

  def __init__(self, reply: str = "A short summary.") -> None:
    self.reply = reply

  def is_available(self, *, force: bool = False) -> bool:
    return True

  def chat_stream(self, messages, options=None):
    yield self.reply


@pytest.fixture
def api(tmp_path: Path):
  storage = SqliteStorage(tmp_path / "api.db")
  apply_migrations(storage)

  container = Container()
  container.register_instance("settings", load_settings())
  container.register_instance("event_bus", EventBus())
  container.register_instance("llm", FakeLlm())
  container.register_instance("overlay", OverlayStore(tmp_path / "profile.json"))
  container.register_instance("conversation_repository", ConversationRepository(storage))
  container.register_instance("memory", MemoryService(MemoryRepository(storage)))
  container.register_instance("task_repository", TaskRepository(storage))
  container.register_instance("calendar_repository", CalendarEventRepository(storage))
  container.register_instance("notification_repository", NotificationRepository(storage))
  container.register_instance("automation_run_repository", AutomationRunRepository(storage))
  container.register_instance("automation", AutomationService(AutomationRepository(storage)))
  container.register_instance("project_repository", ProjectRepository(storage))
  container.register_instance("goal_repository", GoalRepository(storage))
  container.register_instance("knowledge_repository", KnowledgeRepository(storage))

  client = TestClient(create_app(container))
  yield client
  storage.close()


def test_projects_crud_and_open_task_count(api: TestClient) -> None:
  created = api.post("/api/projects", json={"name": "Ultron", "description": "the AI OS"})
  assert created.status_code == 201
  project = created.json()
  assert project["openTasks"] == 0
  assert set(project) >= {"id", "name", "description", "status", "progress", "openTasks"}

  api.post("/api/tasks", json={"title": "Wire the API", "projectId": project["id"]})
  done = api.post("/api/tasks", json={"title": "Old thing", "projectId": project["id"]}).json()
  api.patch(f"/api/tasks/{done['id']}", json={"status": "done"})

  listed = api.get("/api/projects").json()
  assert listed[0]["openTasks"] == 1  # the finished one is not counted

  detail = api.get(f"/api/projects/{project['id']}").json()
  assert {"tasks", "conversations", "goals", "files", "memories"} <= set(detail)
  assert len(detail["tasks"]) == 2

  renamed = api.patch(f"/api/projects/{project['id']}", json={"name": "Ultron OS"}).json()
  assert renamed["name"] == "Ultron OS"

  assert api.delete(f"/api/projects/{project['id']}").status_code == 204
  assert api.get(f"/api/projects/{project['id']}").status_code == 404


def test_goals_carry_project_name_and_milestones(api: TestClient) -> None:
  project = api.post("/api/projects", json={"name": "Ultron"}).json()
  goal = api.post(
    "/api/goals",
    json={"title": "Ship v1", "projectId": project["id"], "milestones": ["API", "UI"]},
  ).json()
  assert goal["milestones"][0] == {"t": "API", "done": False, "current": True}

  listed = api.get("/api/goals").json()
  assert listed[0]["project"] == "Ultron"

  updated = api.patch(f"/api/goals/{goal['id']}", json={"progress": 40}).json()
  assert updated["progress"] == 40
  # Progress is clamped rather than trusted.
  assert api.patch(f"/api/goals/{goal['id']}", json={"progress": 300}).json()["progress"] == 100
  assert api.patch("/api/goals/nope", json={"progress": 10}).status_code == 404


def test_knowledge_crud_summarize_and_save_to_memory(api: TestClient) -> None:
  item = api.post(
    "/api/knowledge",
    json={"title": "Design notes", "body": "Ultron is local-first.", "tags": ["design"]},
  ).json()
  assert item["size"] == len("Ultron is local-first.")
  assert item["summary"] is None

  assert [k["id"] for k in api.get("/api/knowledge", params={"q": "design"}).json()] == [item["id"]]
  assert api.get("/api/knowledge", params={"q": "nothing here"}).json() == []

  summarized = api.post(f"/api/knowledge/{item['id']}/summarize").json()
  assert summarized["summary"] == "A short summary."

  memory = api.post(f"/api/knowledge/{item['id']}/memory").json()
  assert memory["text"] == "A short summary."
  assert memory["category"] == "learned"

  assert api.delete(f"/api/knowledge/{item['id']}").status_code == 204
  assert api.post("/api/knowledge/gone/summarize").status_code == 404


def test_summarize_needs_text(api: TestClient) -> None:
  item = api.post("/api/knowledge", json={"title": "Empty"}).json()
  response = api.post(f"/api/knowledge/{item['id']}/summarize")
  assert response.status_code == 422
  assert "no text" in response.json()["detail"]


def test_activity_is_derived_and_filterable(api: TestClient) -> None:
  assert api.get("/api/activity").json() == []

  task = api.post("/api/tasks", json={"title": "Write the docs"}).json()
  api.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
  api.post("/api/memories", json={"text": "Prefers chai", "category": "preferences"})

  everything = api.get("/api/activity").json()
  kinds = {item["kind"] for item in everything}
  assert {"tasks", "memory"} <= kinds
  assert any(item["title"] == "Task completed" for item in everything)

  only_tasks = api.get("/api/activity", params={"kind": "tasks"}).json()
  assert {item["kind"] for item in only_tasks} == {"tasks"}


def test_insights_count_real_work_only(api: TestClient) -> None:
  empty = api.get("/api/insights").json()
  assert empty["tasks"] == {"done": 0, "total": 0}
  assert empty["streak"] == 0
  assert empty["sessions"] == []

  task = api.post("/api/tasks", json={"title": "Ship it"}).json()
  api.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
  body = api.get("/api/insights").json()
  assert body["tasks"] == {"done": 1, "total": 1}
  assert body["usage"]["tasks"] == 1
  assert body["streak"] >= 1


def test_search_spans_tasks_memories_projects_and_knowledge(api: TestClient) -> None:
  assert api.get("/api/search", params={"q": ""}).json() == []

  api.post("/api/tasks", json={"title": "Buy oat milk"})
  api.post("/api/memories", json={"text": "Likes oat milk in chai", "category": "preferences"})
  api.post("/api/projects", json={"name": "Milk run"})
  api.post("/api/knowledge", json={"title": "Milk suppliers", "tags": ["milk"]})

  kinds = {item["kind"] for item in api.get("/api/search", params={"q": "milk"}).json()}
  assert kinds == {"task", "memory", "project", "knowledge"}
  assert api.get("/api/search", params={"q": "zzzz"}).json() == []


def test_unbuilt_surfaces_answer_empty_rather_than_erroring(api: TestClient) -> None:
  # No agent runtime, session tracking, or integrations exist yet. The pages
  # should render their empty states, not an error.
  for path in ("/api/agents", "/api/executions", "/api/sessions", "/api/integrations", "/api/research"):
    response = api.get(path)
    assert response.status_code == 200, path
    assert response.json() == [], path


def test_activity_stream_forwards_bus_events() -> None:
  """The frontend's EventSource needs a real event stream on its own path.

  /api/events is the calendar REST route, so the stream lives at /api/stream.
  """
  import json as _json

  bus = EventBus()
  stream = ActivityStream(bus, heartbeat=0.05)
  frames = stream.frames()

  assert _json.loads(next(frames).split("data: ", 1)[1])["type"] == "ready"

  bus.publish("automation.notify", {"message": "tea time"})
  payload = _json.loads(next(frames).split("data: ", 1)[1])
  assert payload == {"type": "automation", "payload": {"message": "tea time"}}

  # An idle connection is held open with a comment heartbeat.
  assert next(frames).startswith(": keep-alive")
  frames.close()
  assert bus._handlers["automation.notify"] == []  # noqa: SLF001 - unsubscribed


def test_stream_route_is_registered_separately_from_calendar(api: TestClient) -> None:
  paths = set(api.app.openapi()["paths"])
  assert "/api/stream" in paths
  assert "/api/events" in paths
