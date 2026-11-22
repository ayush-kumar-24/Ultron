"""Agents, research, integrations, sessions, screen and data controls over HTTP.

Fake model and fake vision only - no Ollama, no real screen, no microphone.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maira.api.overlay import OverlayStore
from maira.api.server import create_app
from maira.app.container import Container
from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.screen import Screen, ScreenReading
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
from maira.infrastructure.persistence.sqlite.repositories.intelligence import (
  AgentExecutionRepository,
  ResearchRepository,
  WorkSessionRepository,
)
from maira.modules.automation.service import AutomationService
from maira.modules.desktop_controller.service import DesktopControllerService
from maira.modules.memory.service import MemoryService
from maira.modules.orchestration.orchestrator import Orchestrator
from maira.modules.orchestration.registry import AgentRegistry
from maira.modules.orchestration.wiring import register_agents, subscribe_activity
from maira.modules.research.service import ResearchService

REPORT = {
  "summary": "Use openWakeWord. It runs locally on the CPU [1].",
  "findings": ["openWakeWord is fully local", "It needs about an hour of training data"],
  "contradictions": [],
  "recommendations": ["Start with openWakeWord"],
  "nextActions": ["Train a wake word model", "Measure the false accept rate"],
}
PLAN = {"summary": "A short plan for the wake word work.", "plan": ["Install openWakeWord", "Train the wake word", "Test it for a day"]}


class FakeLlm:
  model = "fake-model"

  def __init__(self) -> None:
    self.available = True
    self.reply = json.dumps(REPORT)
    self.prompts: list[str] = []

  def is_available(self, *, force: bool = False) -> bool:
    return self.available

  def chat_stream(self, messages, *, options=None) -> Iterator[str]:
    self.prompts.append(messages[-1]["content"])
    yield self.reply


class FakeVision(Screen):
  def __init__(self, bus=None) -> None:
    self.enabled = True
    self.bus = bus

  def set_enabled(self, enabled: bool) -> None:
    self.enabled = enabled

  def is_available(self) -> tuple[bool, str]:
    return (True, "ready") if self.enabled else (False, "Screen vision disabled in settings")

  def read_screen(self, *, display=None, region=None) -> ScreenReading:
    if self.bus is not None:
      self.bus.publish("screen.read", {"ok": True})
    return ScreenReading(ok=True, summary="Read 1 line(s).", text="KeyError: id", lines=("KeyError: id",), width=800, height=600)


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
  # Integration toggles persist to the user config; keep that out of the real data folder.
  monkeypatch.setattr("maira.api.routes.integrations._persist", lambda path, value: None)
  storage = SqliteStorage(tmp_path / "intel.db")
  apply_migrations(storage)
  settings = load_settings()
  bus = EventBus()
  llm = FakeLlm()
  vision = FakeVision(bus)

  container = Container()
  container.register_instance("settings", settings)
  container.register_instance("event_bus", bus)
  container.register_instance("storage", storage)
  container.register_instance("llm", llm)
  container.register_instance("overlay", OverlayStore(tmp_path / "profile.json"))
  conversations = ConversationRepository(storage)
  memory = MemoryService(MemoryRepository(storage))
  knowledge = KnowledgeRepository(storage)
  container.register_instance("conversation_repository", conversations)
  container.register_instance("memory", memory)
  container.register_instance("task_repository", TaskRepository(storage))
  container.register_instance("calendar_repository", CalendarEventRepository(storage))
  container.register_instance("notification_repository", NotificationRepository(storage))
  container.register_instance("automation_run_repository", AutomationRunRepository(storage))
  container.register_instance("automation", AutomationService(AutomationRepository(storage)))
  container.register_instance("project_repository", ProjectRepository(storage))
  container.register_instance("goal_repository", GoalRepository(storage))
  container.register_instance("knowledge_repository", knowledge)
  container.register_instance("vision", vision)
  container.register_instance("desktop", DesktopControllerService(enabled=True, allow_input=False))

  research_repo = ResearchRepository(storage)
  executions = AgentExecutionRepository(storage)
  container.register_instance("research_repository", research_repo)
  container.register_instance("agent_execution_repository", executions)
  container.register_instance("work_session_repository", WorkSessionRepository(storage))
  registry = AgentRegistry(executions, bus=bus)
  register_agents(registry, container, settings)
  container.register_instance("agent_registry", registry)
  subscribe_activity(registry, bus, memory)
  container.register_instance(
    "research",
    ResearchService(research_repo, llm, knowledge=knowledge, memory=memory, conversations=conversations, bus=bus),
  )
  container.register_instance(
    "orchestrator", Orchestrator(registry, llm, knowledge=knowledge, memory=memory, conversations=conversations)
  )

  client = TestClient(create_app(container))
  yield client, container, llm
  storage.close()


def _events(response) -> list[dict]:
  return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


# ---------------------------------------------------------------- agents
def test_agents_are_the_real_services(env) -> None:
  client, *_ = env
  agents = client.get("/api/agents").json()
  ids = {agent["id"] for agent in agents}
  assert {"core", "action", "memory", "planning", "automation", "research", "knowledge", "vision", "system"} <= ids
  core = next(agent for agent in agents if agent["id"] == "core")
  assert core["status"] == "ready"
  assert core["model"].endswith("fake-model")
  assert core["executions"] == 0


def test_an_unavailable_model_is_reported_not_hidden(env) -> None:
  client, _container, llm = env
  llm.available = False
  core = client.get("/api/agents/core").json()
  assert core["available"] is False
  assert core["status"] == "idle"
  assert "Ollama is not running" in core["description"]


def test_unknown_agent_is_404(env) -> None:
  client, *_ = env
  assert client.get("/api/agents/nope").status_code == 404
  assert client.get("/api/agents/nope/executions").status_code == 404


def test_orchestration_streams_five_stages_and_records_history(env) -> None:
  client, _container, llm = env
  llm.reply = json.dumps(PLAN)
  response = client.post("/api/agents/orchestrate", json={"request": "Plan the wake word work"})
  events = _events(response)
  steps = [e for e in events if e["type"] == "step"]
  assert [s["index"] for s in steps if s["status"] == "done"] == [0, 1, 2, 3, 4]
  assert [s["agent"] for s in steps if s["status"] == "running"] == ["core", "research", "knowledge", "planning", "core"]
  result = events[-1]
  assert result["type"] == "done"
  assert result["payload"]["verified"] is True
  assert len(result["payload"]["plan"]) == 3

  history = client.get("/api/executions").json()
  assert len(history) == 5
  assert all(item["status"] == "done" for item in history)
  assert client.get("/api/agents/planning").json()["executions"] == 1


def test_orchestration_is_unverified_when_the_plan_is_thin(env) -> None:
  client, _container, llm = env
  llm.reply = json.dumps({"summary": "Do it.", "plan": ["Just one step"]})
  result = _events(client.post("/api/agents/orchestrate", json={"request": "Plan the wake word work"}))[-1]
  assert result["payload"]["verified"] is False
  assert result["payload"]["checks"]


def test_orchestration_fails_cleanly_without_a_model(env) -> None:
  client, _container, llm = env
  llm.available = False
  events = _events(client.post("/api/agents/orchestrate", json={"request": "Plan something"}))
  assert events[-1]["type"] == "error"
  failed = [item for item in client.get("/api/executions").json() if item["status"] == "failed"]
  assert len(failed) == 1 and failed[0]["agentId"] == "planning"


def test_orchestrate_rejects_an_empty_request(env) -> None:
  client, *_ = env
  assert client.post("/api/agents/orchestrate", json={"request": "  "}).status_code == 400


# ---------------------------------------------------------------- research
def test_research_uses_local_sources_and_cites_them(env) -> None:
  client, _container, llm = env
  client.post("/api/knowledge", json={"title": "Wake word notes", "body": "openWakeWord runs locally on the CPU.", "type": "note"})
  client.post("/api/memories", json={"text": "Prefers a local wake word engine", "category": "preferences"})

  events = _events(client.post("/api/research/stream", json={"query": "Which wake word engine should I use?"}))
  kinds = [e["type"] for e in events]
  assert kinds[0] == "session"
  assert kinds[-1] == "done"
  assert [e["step"] for e in events if e["type"] == "step"][:6] == [0, 1, 2, 3, 4, 5]

  session = events[-1]["payload"]
  assert session["status"] == "done"
  assert session["sources"] == 2
  report = session["report"]
  assert report["grounded"] is True
  assert len(report["evidence"]) == 2
  assert {e["title"].split(":")[0] for e in report["evidence"]} == {"Knowledge", "Memory"}
  assert "[1]" in llm.prompts[-1]  # the model was shown the numbered sources

  listed = client.get("/api/research").json()
  assert [item["id"] for item in listed] == [session["id"]]
  assert client.get(f"/api/research/{session['id']}").json()["report"]["summary"]


def test_research_says_so_when_nothing_on_the_device_matches(env) -> None:
  client, *_ = env
  session = _events(client.post("/api/research/stream", json={"query": "History of sourdough bread"}))[-1]["payload"]
  assert session["sources"] == 0
  assert session["report"]["grounded"] is False
  assert session["report"]["evidence"] == []
  assert "not sourced" in session["report"]["summary"]


def test_research_failure_is_stored_and_explained(env) -> None:
  client, _container, llm = env
  llm.available = False
  events = _events(client.post("/api/research/stream", json={"query": "Anything at all"}))
  assert events[-1]["type"] == "error"
  stored = client.get("/api/research").json()[0]
  assert stored["status"] == "failed"
  assert "Ollama" in stored["error"]
  notes = client.get("/api/notifications").json()
  assert notes[0]["title"] == "Research failed"


def test_research_survives_a_model_that_ignores_the_format(env) -> None:
  client, _container, llm = env
  llm.reply = "openWakeWord is the best choice because it is local."
  session = _events(client.post("/api/research/stream", json={"query": "wake word engine"}))[-1]["payload"]
  assert session["status"] == "done"
  assert "openWakeWord" in session["report"]["summary"]


def test_research_becomes_tasks_and_knowledge(env) -> None:
  client, *_ = env
  session = _events(client.post("/api/research/stream", json={"query": "wake word engine"}))[-1]["payload"]
  tasks = client.post(f"/api/research/{session['id']}/tasks").json()
  assert [task["title"] for task in tasks] == REPORT["nextActions"]
  item = client.post(f"/api/research/{session['id']}/knowledge").json()
  assert item["title"].startswith("Research:")

  assert client.delete(f"/api/research/{session['id']}").status_code == 204
  assert client.get(f"/api/research/{session['id']}").status_code == 404


def test_research_rejects_bad_input(env) -> None:
  client, *_ = env
  assert client.post("/api/research/stream", json={"query": ""}).status_code == 400
  assert client.post("/api/research/stream", json={"query": "x" * 2000}).status_code == 422
  assert client.post("/api/research/missing/tasks").status_code == 404


# ---------------------------------------------------------------- integrations
def test_integrations_report_real_state(env) -> None:
  client, _container, llm = env
  rows = {row["id"]: row for row in client.get("/api/integrations").json()}
  assert rows["ollama"]["status"] == "connected"
  assert rows["screen"]["status"] == "connected"
  assert rows["voice"]["status"] == "available"  # never started in this process
  llm.available = False
  assert client.get("/api/integrations").json()[0]["status"] == "disconnected"


def test_screen_reading_can_be_switched_off_and_on(env) -> None:
  client, container, _llm = env
  off = client.post("/api/integrations/screen/disconnect").json()
  assert off["status"] == "available"
  assert container.resolve("vision").enabled is False
  assert client.post("/api/screen/read").status_code == 503
  assert client.post("/api/integrations/screen/connect").json()["status"] == "connected"


def test_secrets_are_never_set_from_the_web(env) -> None:
  client, *_ = env
  response = client.post("/api/integrations/gmail/connect")
  assert response.status_code == 409
  assert "desktop app" in response.json()["detail"]
  assert client.post("/api/integrations/unknown/connect").status_code == 404


# ---------------------------------------------------------------- screen, sessions, message -> task
def test_screen_read_returns_text_and_logs_the_vision_agent(env) -> None:
  client, *_ = env
  reading = client.post("/api/screen/read").json()
  assert reading["text"] == "KeyError: id"
  assert client.get("/api/agents/vision").json()["executions"] == 1


def test_sessions_feed_insights(env) -> None:
  client, *_ = env
  assert client.get("/api/sessions").json() == []
  created = client.post("/api/sessions", json={"type": "work", "project": "Ultron", "minutes": 120, "summary": "API layer"})
  assert created.status_code == 201
  assert client.post("/api/sessions", json={"minutes": 0}).status_code == 422

  insights = client.get("/api/insights").json()
  assert len(insights["weekly"]) == 7 and len(insights["focus"]) == 7
  assert insights["weekly"][-1]["work"] == 2.0
  assert insights["focus"][-1] == 50  # 120 of a 240-minute target
  assert insights["projects"] == [{"name": "Ultron", "minutes": 120}]


def test_task_from_a_message(env) -> None:
  client, container, _llm = env
  from maira.core.domain.entities import Message
  from maira.core.domain.value_objects import MessageRole
  from datetime import datetime, timezone

  repo = container.resolve("conversation_repository")
  conversation = repo.create_conversation("Chat")
  message = Message(id="m-1", role=MessageRole.ASSISTANT, content="Stamp the migration then rebuild.", timestamp=datetime.now(timezone.utc))
  repo.add_message(conversation.id, message)

  task = client.post("/api/messages/m-1/task", json={"title": "Stamp the migration"}).json()
  assert task["title"] == "Stamp the migration"
  assert client.post("/api/messages/none/task", json={}).status_code == 404


# ---------------------------------------------------------------- data controls
def test_wipe_really_deletes_everything(env) -> None:
  client, container, _llm = env
  client.post("/api/tasks", json={"title": "A task"})
  client.post("/api/memories", json={"text": "A memory", "category": "personal"})
  client.post("/api/knowledge", json={"title": "A doc", "body": "text"})
  client.post("/api/sessions", json={"minutes": 30})
  _events(client.post("/api/research/stream", json={"query": "A doc"}))

  assert client.post("/api/system/wipe").status_code == 204

  for path in ("/api/tasks", "/api/memories", "/api/knowledge", "/api/sessions", "/api/research", "/api/executions", "/api/notifications"):
    assert client.get(path).json() == [], path
  storage = container.resolve("storage")
  assert storage.fetchone("SELECT COUNT(*) FROM memories")[0] == 0


def test_reset_is_refused_on_real_data(env) -> None:
  client, *_ = env
  response = client.post("/api/system/reset")
  assert response.status_code == 409
  assert "real data" in response.json()["detail"]


def test_work_done_through_chat_reaches_the_right_agents(env) -> None:
  """The Agents page must reflect chat and voice use, not only its own buttons."""
  client, container, _llm = env
  bus = container.resolve("event_bus")
  bus.publish("agent.ran", {"goal": "send my resume to Rahul", "ok": True, "message": "Sent"})
  bus.publish("agent.ran", {"goal": "rename report.pdf", "ok": False, "message": "File not found"})
  bus.publish("desktop.ran", {"ok": True, "message": "Opened Chrome"})
  bus.publish("skill.used", {"name": "pdf-split", "explicit": True})
  bus.publish("planner.changed", {"reason": "chat"})
  bus.publish("planner.changed", {"reason": "web"})  # the user's own edit, not the agent's
  bus.publish("automation.changed", {"reason": "created"})
  client.post("/api/memories", json={"text": "Likes short answers", "category": "preferences"})

  counts = {agent["id"]: agent["executions"] for agent in client.get("/api/agents").json()}
  assert counts["action"] == 2
  assert counts["system"] == 1
  assert counts["skills"] == 1
  assert counts["planning"] == 1
  assert counts["automation"] == 1
  assert counts["memory"] == 1
  failed = [e for e in client.get("/api/agents/action/executions").json() if e["status"] == "failed"]
  assert failed[0]["error"] == "File not found"


# ---------------------------------------------------------------- real settings
@pytest.fixture
def cfg(env, tmp_path: Path, monkeypatch):
  # The settings file is the user's; tests write a throwaway copy instead.
  monkeypatch.setattr("maira.app.user_config.user_config_path", lambda: tmp_path / "config.yaml")
  monkeypatch.setattr("maira.api.routes.config._installed_models", lambda: ["llama3.2:latest", "qwen2.5:0.5b"])
  return env


def _field(client, path: str) -> dict:
  return next(f for f in client.get("/api/config").json()["fields"] if f["path"] == path)


def test_config_lists_the_desktop_settings(cfg) -> None:
  client, _container, _llm = cfg
  data = client.get("/api/config").json()
  ids = {c["id"] for c in data["categories"]}
  assert {"general", "ai", "tasks", "agent"} <= ids and "status" not in ids
  model = next(f for f in data["fields"] if f["path"] == "ollama.model")
  assert {"llama3.2:latest", "qwen2.5:0.5b"} <= {o["value"] for o in model["options"]}
  assert data["restartPending"] == []


def test_config_saves_and_coerces(cfg, tmp_path: Path) -> None:
  client, _container, _llm = cfg
  res = client.patch("/api/config", json={"path": "notifications.enabled", "value": "false"})
  assert res.status_code == 200 and res.json()["value"] is False
  assert _field(client, "notifications.enabled")["value"] is False
  assert client.patch("/api/config", json={"path": "briefing.time", "value": "7:5"}).json()["value"] == "07:05"
  assert "notifications" in (tmp_path / "config.yaml").read_text(encoding="utf-8")


def test_config_rejects_bad_values(cfg) -> None:
  client, _container, _llm = cfg
  assert client.patch("/api/config", json={"path": "no.such", "value": 1}).status_code == 404
  assert client.patch("/api/config", json={"path": "briefing.time", "value": "25:00"}).status_code == 422
  assert client.patch("/api/config", json={"path": "agent.max_steps", "value": "lots"}).status_code == 422
  assert client.patch("/api/config", json={"path": "agent.max_steps", "value": 100000}).status_code == 422
  assert client.patch("/api/config", json={"path": "memory.recall_mode", "value": "nonsense"}).status_code == 422


def test_restart_settings_are_flagged(cfg) -> None:
  client, _container, _llm = cfg
  field = next(f for f in client.get("/api/config").json()["fields"] if f["restart"] and f["kind"] == "bool" and not f["readOnly"])
  res = client.patch("/api/config", json={"path": field["path"], "value": not field["value"]}).json()
  assert res["restart"] is True and field["path"] in res["restartPending"]
  assert field["path"] in client.get("/api/config").json()["restartPending"]


def test_agent_settings_apply_to_the_running_agent(cfg) -> None:
  client, container, _llm = cfg

  class Agent:
    enabled, auto_detect, model, max_steps = True, True, "x", 5

  agent = Agent()
  container.register_instance("agent", agent)
  container.resolve("agent")
  client.patch("/api/config", json={"path": "agent.enabled", "value": False})
  client.patch("/api/config", json={"path": "agent.model", "value": "llama3.2:latest"})
  assert agent.enabled is False and agent.model == "llama3.2:latest"


def test_profile_name_is_the_real_setting(cfg) -> None:
  client, _container, _llm = cfg
  me = client.patch("/api/me", json={"name": "Ayush Kumar"}).json()
  assert me["name"] == "Ayush Kumar" and me["initials"] == "AK"
  assert _field(client, "briefing.name")["value"] == "Ayush Kumar"
  client.patch("/api/config", json={"path": "briefing.name", "value": "Tony"})
  assert client.get("/api/me").json()["name"] == "Tony"
