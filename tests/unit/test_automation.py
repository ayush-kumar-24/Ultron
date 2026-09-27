"""Unit tests for automation scheduling and parsing."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
)
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import AutomationRepository
from maira.modules.automation.executor import AutomationExecutor
from maira.modules.automation.parser import infer_action, parse_schedule_request
from maira.modules.automation.service import AutomationService


@pytest.fixture
def automation_service(tmp_path):
  db = tmp_path / "test.db"
  storage = SqliteStorage(db)
  apply_migrations(storage)
  return AutomationService(AutomationRepository(storage))


def test_parse_in_minutes() -> None:
  now = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("remind me to stretch in 10 minutes", now=now)
  assert parsed is not None
  assert "stretch" in parsed.instruction.lower()
  assert parsed.run_at <= (now + timedelta(minutes=10)).astimezone(parsed.run_at.tzinfo) + timedelta(seconds=1)


def test_parse_tomorrow_at() -> None:
  now = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("schedule open youtube tomorrow at 9am", now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.OPEN_URL
  local = parsed.run_at.astimezone(ZoneInfo("Asia/Kolkata"))
  assert local.day == 15
  assert local.hour == 9


def test_parse_every_day() -> None:
  now = datetime(2026, 8, 14, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("every day at 8am remind me to drink water", now=now)
  assert parsed is not None
  assert parsed.recurrence == AutomationRecurrence.DAILY


def test_infer_open_app() -> None:
  action, payload = infer_action("open notepad")
  assert action == AutomationActionType.OPEN_APP
  assert payload["app"] == "notepad.exe"


def test_create_and_due(automation_service) -> None:
  now = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  job = automation_service.create(
    "Test",
    "say hello",
    now - timedelta(minutes=1),
  )
  due = automation_service.due_jobs(now)
  assert any(item.id == job.id for item in due)


def test_executor_notify(automation_service) -> None:
  notes: list[str] = []
  now = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  job = automation_service.create(
    "Ping",
    "drink water",
    now - timedelta(seconds=5),
    action_type=AutomationActionType.NOTIFY,
    action_payload='{"message": "drink water"}',
  )
  executor = AutomationExecutor(automation_service, on_notify=notes.append)
  result = executor.run(job)
  assert result.ok
  assert notes
  refreshed = automation_service.get(job.id)
  assert refreshed is not None
  assert refreshed.status == AutomationStatus.DONE


def test_parse_one_minute_remind() -> None:
  now = datetime(2026, 8, 14, 19, 37, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("1 minute remind", now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.NOTIFY
  delta = parsed.run_at - now.astimezone(parsed.run_at.tzinfo)
  assert timedelta(seconds=50) <= delta <= timedelta(seconds=70)


def test_parse_remind_me_in_one_minute() -> None:
  now = datetime(2026, 8, 14, 19, 37, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("remind me in 1 minute", now=now)
  assert parsed is not None
  delta = parsed.run_at - now.astimezone(parsed.run_at.tzinfo)
  assert timedelta(seconds=50) <= delta <= timedelta(seconds=70)


def test_parse_open_youtube_evening_bare_time() -> None:
  now = datetime(2026, 8, 14, 19, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("open youtube at 7:38", now=now)
  assert parsed is not None
  local = parsed.run_at.astimezone(ZoneInfo("Asia/Kolkata"))
  assert local.hour == 19
  assert local.minute == 38
  assert local.day == 14


def test_parse_open_youtube_at() -> None:
  now = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("open youtube at 9pm", now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.OPEN_URL
  assert "youtube" in parsed.action_payload


def test_non_schedule_returns_none() -> None:
  assert parse_schedule_request("what is recursion?") is None


@pytest.mark.parametrize(
  ("text", "title", "message"),
  [
    ("remind me in 1 minute to drink water", "Drink water", "drink water"),
    ("remind me to drink water in 1 minute", "Drink water", "drink water"),
    ("remind me to call mom at 6pm", "Call mom", "call mom"),
    ("yaad dila dena 5 min baad paani peena", "Paani peena", "paani peena"),
    ("every day at 8am remind me to take vitamins", "Take vitamins", "take vitamins"),
    ("remind me in 10 minutes to go to gym", "Go to gym", "go to gym"),
    ("remind me to open youtube at 9pm", "Open youtube", "open youtube"),
    ("drink water in 10 minutes", "Drink water", "drink water"),
  ],
)
def test_reminders_become_notifications_not_ai_tasks(text: str, title: str, message: str) -> None:
  import json

  now = datetime(2026, 9, 23, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request(text, now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.NOTIFY
  assert parsed.title == title
  assert json.loads(parsed.action_payload) == {"message": message}
  assert "reminder" in parsed.confirmation


def test_dangling_to_falls_back_to_plain_reminder() -> None:
  now = datetime(2026, 9, 23, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("remind me at 9pm to", now=now)
  assert parsed is not None
  assert parsed.title == "Reminder"


def test_explicit_schedule_still_runs_ai_task() -> None:
  now = datetime(2026, 9, 23, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("schedule summarize my notes tomorrow at 9am", now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.AGENT


def test_open_at_time_still_opens() -> None:
  now = datetime(2026, 9, 23, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("open youtube at 9pm", now=now)
  assert parsed is not None
  assert parsed.action_type == AutomationActionType.OPEN_URL


def test_dotted_pm_in_reminders() -> None:
  now = datetime(2026, 9, 24, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
  parsed = parse_schedule_request("remind me at 6 p.m. to drink water", now=now)
  assert parsed is not None
  assert parsed.title == "Drink water"
  assert parsed.run_at.astimezone(ZoneInfo("Asia/Kolkata")).hour == 18
