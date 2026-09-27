"""Home Today panel, Activity timeline and global search built from real data."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from maira.core.domain.value_objects import AutomationActionType, MemoryCategory, Priority, TaskStatus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRepository,
  MemoryRepository,
  NoteRepository,
  TaskRepository,
)
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.automation.service import AutomationService
from maira.modules.memory.service import MemoryService
from maira.modules.planner.overview import activity_feed, home_overview, search_everything
from maira.modules.planner.service import PlannerService

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=LOCAL_TZ)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
  return datetime(2026, 9, day, hour, minute, tzinfo=LOCAL_TZ)


@pytest.fixture
def storage(tmp_path):
  storage = SqliteStorage(tmp_path / "o.db")
  apply_migrations(storage)
  return storage


@pytest.fixture
def planner(storage):
  return PlannerService(TaskRepository(storage), NoteRepository(storage))


@pytest.fixture
def automation(storage):
  return AutomationService(AutomationRepository(storage))


def test_empty_home(planner, automation) -> None:
  overview = home_overview(planner, automation, NOW)
  assert overview.tasks == [] and overview.reminders == [] and overview.notes == []
  assert overview.tasks_total == 0


def test_home_orders_overdue_then_timed_then_rest(planner, automation) -> None:
  planner.add_task("Buy milk")
  planner.add_task("Submit report", due_at=_at(24, 23, 59))
  planner.add_task("Call mom", due_at=_at(24, 18), priority=Priority.HIGH)
  planner.add_task("Pay bill", due_at=_at(23, 23, 59))
  planner.add_task("Gym tomorrow", due_at=_at(25, 7))  # not today
  finished = planner.add_task("Old")
  planner.set_task_status(finished.id, TaskStatus.DONE)
  planner.add_task("Fifth")

  overview = home_overview(planner, automation, NOW)

  titles = [t.title for t in overview.tasks]
  assert titles[:3] == ["Pay bill", "Call mom", "Submit report"]
  assert titles[3] in {"Buy milk", "Fifth"}  # undated: either, same timestamp
  assert overview.tasks_total == 5  # four shown + "Fifth"
  assert overview.tasks[0].warn and overview.tasks[0].meta == "kal (beet gaya) · overdue"
  assert overview.tasks[1].meta == "aaj 6:00 PM · high"


def test_home_reminders_are_upcoming_only_and_sorted(planner, automation) -> None:
  automation.create("Later", "x", _at(24, 20), action_type=AutomationActionType.NOTIFY)
  automation.create("Soon", "x", _at(24, 11), action_type=AutomationActionType.NOTIFY)
  automation.create("Tomorrow", "x", _at(25, 9), action_type=AutomationActionType.NOTIFY)
  automation.create("Past", "x", _at(24, 8), action_type=AutomationActionType.NOTIFY)
  paused = automation.create("Paused", "x", _at(24, 12), action_type=AutomationActionType.NOTIFY)
  automation.set_enabled(paused.id, False)

  reminders = home_overview(planner, automation, NOW).reminders

  assert [(r.title, r.meta) for r in reminders] == [
    ("Soon", "11:00 AM"),
    ("Later", "8:00 PM"),
    ("Tomorrow", "Tomorrow 9:00 AM"),
  ]


def test_home_recent_notes(planner, automation) -> None:
  planner.add_note("First", "a")
  planner.add_note("Second", "b")
  planner.add_note("Third", "c")
  assert len(home_overview(planner, automation, NOW).notes) == 2


def test_activity_feed_lists_real_events_newest_first(planner, automation) -> None:
  task = planner.add_task("Pay bill")
  planner.set_task_status(task.id, TaskStatus.DONE)
  planner.add_task("Call mom")
  planner.add_note("Ideas", "x")
  job = automation.create("Drink water", "x", datetime.now(LOCAL_TZ) - timedelta(minutes=1),
                          action_type=AutomationActionType.NOTIFY)
  automation.mark_ran(job.id, ok=True)
  failed = automation.create("Open app", "x", datetime.now(LOCAL_TZ), action_type=AutomationActionType.OPEN_APP)
  automation.mark_ran(failed.id, ok=False, error="nope")
  automation.create("Future", "x", datetime.now(LOCAL_TZ) + timedelta(hours=1))  # not run: not listed

  texts = [e["text"] for e in activity_feed(planner, automation)]

  assert set(texts) == {
    'Task done: "Pay bill"',
    'Task added: "Call mom"',
    'Note saved: "Ideas"',
    'Reminder shown: "Drink water"',
    'Automation failed: "Open app"',
  }


def test_activity_feed_limit(planner, automation) -> None:
  for i in range(10):
    planner.add_task(f"t{i}")
  assert len(activity_feed(planner, automation, limit=3)) == 3


def test_search_everything(planner, storage) -> None:
  memory = MemoryService(MemoryRepository(storage))
  planner.add_task("Pay electricity bill")
  planner.add_note("Bills", "electricity due on 5th")
  planner.add_note("Groceries", "milk, eggs")
  memory.store(category=MemoryCategory.PREFERENCE, title="Electricity provider", body="Tata Power")

  everything = search_everything(planner, memory, "ELECTRICITY")
  assert {(r["category"], r["title"]) for r in everything} == {
    ("Tasks", "Pay electricity bill"),
    ("Notes", "Bills"),
    ("Memory", "Electricity provider"),
  }
  assert [r["title"] for r in search_everything(planner, memory, "electricity", "Notes")] == ["Bills"]
  assert len(search_everything(planner, memory, "")) == 4
  assert search_everything(planner, None, "zzz") == []
