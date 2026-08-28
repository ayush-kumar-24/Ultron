"""Phase 2 HTTP API — tasks, calendar, automations, notifications, overview."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maira.api.overlay import OverlayStore
from maira.api.parsing import parse_task
from maira.api.server import create_app
from maira.app.container import Container
from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import AutomationActionType
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRepository,
  AutomationRunRepository,
  CalendarEventRepository,
  ConversationRepository,
  MemoryRepository,
  NotificationRepository,
  TaskRepository,
)
from maira.modules.automation.executor import AutomationExecutor
from maira.modules.automation.scheduler import AutomationScheduler
from maira.modules.automation.service import AutomationService
from maira.modules.memory.service import MemoryService


class FakeLlm:
  model = "test-model"

  def is_available(self, *, force: bool = False) -> bool:
    return True


@pytest.fixture
def api(tmp_path: Path):
  storage = SqliteStorage(tmp_path / "api.db")
  apply_migrations(storage)

  container = Container()
  container.register_instance("settings", load_settings())
  container.register_instance("event_bus", EventBus())
  container.register_instance("llm", FakeLlm())
  container.register_instance("overlay", OverlayStore(tmp_path / "user_profile.json"))
  container.register_instance("conversation_repository", ConversationRepository(storage))
  container.register_instance("memory", MemoryService(MemoryRepository(storage)))
  container.register_instance("task_repository", TaskRepository(storage))
  container.register_instance("calendar_repository", CalendarEventRepository(storage))
  notifications = NotificationRepository(storage)
  container.register_instance("notification_repository", notifications)
  runs = AutomationRunRepository(storage)
  container.register_instance("automation_run_repository", runs)

  automation = AutomationService(AutomationRepository(storage))
  container.register_instance("automation", automation)
  notified: list[str] = []
  scheduler = AutomationScheduler(
    automation, AutomationExecutor(automation, on_notify=notified.append)
  )
  container.register_instance("automation_scheduler", scheduler)

  client = TestClient(create_app(container))
  yield client, notified, scheduler, automation
  storage.close()


# -- task parsing ------------------------------------------------------------


def test_parse_task_reads_time_priority_and_recurrence() -> None:
  now = datetime(2026, 8, 28, 9, 0).astimezone()

  tomorrow = parse_task("remind me to call the bank tomorrow at 4pm", now=now)
  assert tomorrow.title == "Call the bank"
  assert tomorrow.due is not None
  assert (tomorrow.due.hour, tomorrow.due.minute) == (16, 0)
  assert tomorrow.due.date() == (now + timedelta(days=1)).date()

  daily = parse_task("every day at 8am morning review", now=now)
  assert daily.recurrence == "Every Day"
  assert daily.title == "Morning review"

  urgent = parse_task("urgent: fix the migration", now=now)
  assert urgent.priority == "high"

  someday = parse_task("someday tidy the garage", now=now)
  assert someday.priority == "low"

  plain = parse_task("buy milk", now=now)
  assert plain.title == "Buy milk"
  assert plain.due is None


def test_parse_endpoint_matches_contract(api) -> None:
  client, *_ = api
  body = client.post("/api/tasks/parse", json={"text": "call mom tomorrow at 7pm"}).json()
  assert set(body) == {"title", "priority", "due", "recurrence", "projectId", "tags"}
  assert body["title"] == "Call mom"
  assert body["due"] is not None


# -- tasks -------------------------------------------------------------------


def test_task_crud_and_api_shape(api) -> None:
  client, *_ = api
  due = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()

  created = client.post(
    "/api/tasks",
    json={
      "title": "Ship the API",
      "priority": "high",
      "due": due,
      "tags": ["backend"],
      "estimate": 90,
      "description": "wire the routes",
    },
  )
  assert created.status_code == 201
  task = created.json()
  assert task["status"] == "todo"
  assert task["tags"] == ["backend"]
  assert task["estimate"] == 90
  assert set(task) >= {"id", "title", "priority", "status", "due", "projectId", "createdAt"}

  in_progress = client.patch(f"/api/tasks/{task['id']}", json={"status": "in_progress"})
  assert in_progress.json()["status"] == "in_progress"
  assert in_progress.json()["completedAt"] is None

  done = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()
  assert done["status"] == "done"
  assert done["completedAt"] is not None

  reopened = client.patch(f"/api/tasks/{task['id']}", json={"status": "todo"}).json()
  assert reopened["completedAt"] is None

  assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
  assert client.delete(f"/api/tasks/{task['id']}").status_code == 404


def test_task_created_from_a_typed_line(api) -> None:
  client, *_ = api
  task = client.post("/api/tasks", json={"text": "urgent: email the investor tomorrow at 9am"}).json()
  # The priority word stays in the title, matching the frontend's own parser.
  assert task["title"] == "Urgent: email the investor"
  assert task["priority"] == "high"
  assert task["due"] is not None


def test_task_views_filter(api) -> None:
  client, *_ = api
  soon = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
  later = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
  client.post("/api/tasks", json={"title": "Today thing", "due": soon})
  client.post("/api/tasks", json={"title": "Later thing", "due": later})
  client.post("/api/tasks", json={"title": "Someday thing"})

  assert [t["title"] for t in client.get("/api/tasks", params={"view": "today"}).json()] == [
    "Today thing"
  ]
  assert [t["title"] for t in client.get("/api/tasks", params={"view": "upcoming"}).json()] == [
    "Later thing"
  ]
  assert [t["title"] for t in client.get("/api/tasks", params={"view": "inbox"}).json()] == [
    "Someday thing"
  ]
  assert client.get("/api/tasks", params={"view": "completed"}).json() == []


def test_task_rejects_bad_values(api) -> None:
  client, *_ = api
  assert client.post("/api/tasks", json={"title": "x", "priority": "urgent"}).status_code == 400
  assert client.post("/api/tasks", json={"title": "x", "due": "someday"}).status_code == 400
  assert client.post("/api/tasks", json={}).status_code == 422
  task = client.post("/api/tasks", json={"title": "ok"}).json()
  assert client.patch(f"/api/tasks/{task['id']}", json={"status": "blocked"}).status_code == 400


# -- calendar ----------------------------------------------------------------


def test_events_crud_and_range_filter(api) -> None:
  client, *_ = api
  now = datetime.now(timezone.utc)
  soon = client.post(
    "/api/events",
    json={
      "title": "Standup",
      "start": now.isoformat(),
      "end": (now + timedelta(minutes=30)).isoformat(),
    },
  )
  assert soon.status_code == 201
  event = soon.json()
  assert event["type"] == "meeting"
  assert set(event) >= {"id", "title", "start", "end", "type", "projectId"}

  client.post(
    "/api/events",
    json={"title": "Next week", "start": (now + timedelta(days=7)).isoformat()},
  )

  window = client.get(
    "/api/events",
    params={"from": (now - timedelta(hours=1)).isoformat(), "to": (now + timedelta(hours=1)).isoformat()},
  ).json()
  assert [item["title"] for item in window] == ["Standup"]

  assert client.delete(f"/api/events/{event['id']}").status_code == 204
  assert client.delete(f"/api/events/{event['id']}").status_code == 404


def test_calendar_context_counts_tomorrows_meetings(api) -> None:
  client, *_ = api
  tomorrow = datetime.now(timezone.utc).astimezone() + timedelta(days=1)
  start = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
  client.post(
    "/api/events",
    json={
      "title": "Investor call",
      "start": start.isoformat(),
      "end": (start + timedelta(hours=1)).isoformat(),
      "type": "meeting",
    },
  )
  context = client.get("/api/calendar/context").json()
  assert context["meetings"] == 1
  assert "1 meeting tomorrow" in context["text"]
  assert context["freeHours"] == 7


# -- automations -------------------------------------------------------------


def test_automation_from_text_and_controls(api) -> None:
  client, *_ = api
  created = client.post("/api/automations", json={"text": "every day at 8am morning summary"})
  assert created.status_code == 201
  job = created.json()
  assert job["name"] == "Morning summary"
  assert job["status"] == "active"
  assert job["trigger"].startswith("Every day")
  assert job["runs"] == 0
  assert set(job) >= {"id", "name", "trigger", "action", "status", "lastRun", "nextRun", "runs", "failures"}

  paused = client.patch(f"/api/automations/{job['id']}", json={"status": "paused"}).json()
  assert paused["status"] == "paused"
  assert paused["nextRun"] is None

  active = client.patch(f"/api/automations/{job['id']}", json={"status": "active"}).json()
  assert active["status"] == "active"

  assert client.delete(f"/api/automations/{job['id']}").status_code == 204
  assert client.get(f"/api/automations/{job['id']}/runs").status_code == 404


def test_automation_without_a_time_is_rejected(api) -> None:
  client, *_ = api
  response = client.post("/api/automations", json={"text": "do something nice"})
  assert response.status_code == 422
  assert "No time found" in response.json()["detail"]


def test_run_now_records_history_and_notifies(api) -> None:
  client, notified, _, _ = api
  job = client.post("/api/automations", json={"text": "remind me tomorrow at 9am drink water"}).json()

  run = client.post(f"/api/automations/{job['id']}/run").json()
  assert run["status"] == "done"
  assert run["automationId"] == job["id"]
  assert notified == ["Automation: Remind: Drink water"]  # "tomorrow" must not become "morrow"

  runs = client.get(f"/api/automations/{job['id']}/runs").json()
  assert len(runs) == 1
  assert runs[0]["output"]

  listed = client.get("/api/automations").json()[0]
  assert listed["runs"] == 1
  assert listed["failures"] == 0

  inbox = client.get("/api/notifications").json()
  assert inbox[0]["type"] == "automation"
  assert "Drink water" in inbox[0]["body"]


def test_scheduler_runs_due_jobs(api) -> None:
  client, notified, scheduler, automation = api
  automation.create(
    "Late reminder",
    "Late reminder",
    datetime.now(timezone.utc) - timedelta(minutes=5),
    action_type=AutomationActionType.NOTIFY,
    action_payload=json.dumps({"message": "you are late"}),
  )
  assert scheduler.tick() == 1
  assert notified == ["Automation: you are late"]
  # The job is spent, so a second tick finds nothing.
  assert scheduler.tick() == 0


# -- notifications -----------------------------------------------------------


def test_notification_read_flow(api) -> None:
  client, *_ = api
  job = client.post("/api/automations", json={"text": "remind me tomorrow at 9am stretch"}).json()
  client.post(f"/api/automations/{job['id']}/run")

  inbox = client.get("/api/notifications").json()
  assert inbox and inbox[0]["read"] is False
  assert set(inbox[0]) == {"id", "type", "title", "body", "at", "read"}

  marked = client.patch(f"/api/notifications/{inbox[0]['id']}", json={"read": True}).json()
  assert marked["read"] is True

  assert client.post("/api/notifications/read-all").status_code == 204
  assert all(item["read"] for item in client.get("/api/notifications").json())

  assert client.patch("/api/notifications/nope", json={"read": True}).status_code == 404


# -- overview ----------------------------------------------------------------


def test_overview_aggregates_the_dashboard(api) -> None:
  client, *_ = api
  overdue = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
  client.post("/api/tasks", json={"title": "Overdue thing", "due": overdue})
  client.post("/api/tasks", json={"title": "Someday thing"})
  finished = client.post("/api/tasks", json={"title": "Finished thing"}).json()
  client.patch(f"/api/tasks/{finished['id']}", json={"status": "done"})
  client.post("/api/memories", json={"text": "Prefers chai", "category": "preferences"})
  client.post("/api/automations", json={"text": "every day at 7am plan the day"})

  body = client.get("/api/overview").json()
  assert body["productivity"] == {"done": 1, "pending": 2, "rate": 33, "sessions": 0}
  assert body["dueSoon"] == 1
  assert body["memory"]["total"] == 1
  assert body["memory"]["byCategory"]["preferences"] == 1
  assert len(body["automations"]) == 1
  assert {metric["l"] for metric in body["metrics"]} == {
    "Task completion",
    "Open tasks",
    "Automations",
    "Cognitive load",
  }
  assert isinstance(body["activity"], list)


def test_plan_day_groups_work(api) -> None:
  client, *_ = api
  client.post("/api/tasks", json={"title": "Top thing", "priority": "high"})
  client.post("/api/tasks", json={"title": "Second thing", "priority": "medium"})
  today = datetime.now(timezone.utc).astimezone().replace(hour=10, minute=0, second=0, microsecond=0)
  client.post(
    "/api/events",
    json={"title": "Standup", "start": today.isoformat(), "end": (today + timedelta(minutes=30)).isoformat()},
  )

  plan = client.get("/api/plan/day").json()
  assert plan["morning"][0]["title"] == "Top thing"
  assert any(item["title"] == "Standup" for item in plan["morning"])
  assert plan["afternoon"][-1]["title"] == "Second thing"
  assert float(plan["freeHours"]) <= 8
  assert plan["conflicts"] == []


def test_manual_run_is_recorded_once_when_the_scheduler_announces(tmp_path: Path) -> None:
  """A wired scheduler records the run itself — the route must not duplicate it."""
  storage = SqliteStorage(tmp_path / "dup.db")
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
  notifications = NotificationRepository(storage)
  container.register_instance("notification_repository", notifications)
  runs = AutomationRunRepository(storage)
  container.register_instance("automation_run_repository", runs)

  automation = AutomationService(AutomationRepository(storage))
  container.register_instance("automation", automation)

  def announce(job, result) -> None:
    notifications.create(type="automation", title="Automation ran", body=job.title)
    runs.record(job.id, status="done" if result.ok else "failed", output=result.message)

  container.register_instance(
    "automation_scheduler",
    AutomationScheduler(automation, AutomationExecutor(automation), on_job_ran=announce),
  )

  client = TestClient(create_app(container))
  job = client.post("/api/automations", json={"text": "remind me tomorrow at 9am tea"}).json()

  client.post(f"/api/automations/{job['id']}/run")
  assert len(client.get(f"/api/automations/{job['id']}/runs").json()) == 1
  assert len(client.get("/api/notifications").json()) == 1

  client.post(f"/api/automations/{job['id']}/run")
  assert len(client.get(f"/api/automations/{job['id']}/runs").json()) == 2
  assert client.get("/api/automations").json()[0]["runs"] == 2
  storage.close()
