"""Tasks and reminders kept in sync (LinkedPlanner) and roll-over."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import AutomationActionType, TaskStatus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRepository,
  NoteRepository,
  TaskRepository,
)
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.automation.service import AutomationService
from maira.modules.notifications.service import NotificationService
from maira.modules.planner.chat import PlannerChat
from maira.modules.planner.intent import DATE_ONLY_TIME, is_date_only
from maira.modules.planner.reminders import LinkedPlanner, task_id_of
from maira.modules.planner.service import PlannerService

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=LOCAL_TZ)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
  return datetime(2026, 9, day, hour, minute, tzinfo=LOCAL_TZ)


@pytest.fixture
def storage(tmp_path):
  storage = SqliteStorage(tmp_path / "links.db")
  apply_migrations(storage)
  return storage


@pytest.fixture
def automation(storage):
  return AutomationService(AutomationRepository(storage))


def _linked(storage, automation, **kwargs) -> LinkedPlanner:
  return LinkedPlanner(
    PlannerService(TaskRepository(storage), NoteRepository(storage)),
    automation,
    clock=lambda: NOW,
    **kwargs,
  )


@pytest.fixture
def planner(storage, automation) -> LinkedPlanner:
  return _linked(storage, automation)


def _task_jobs(automation) -> list:
  return [j for j in automation.list_jobs(include_done=False) if task_id_of(j)]


def test_timed_task_gets_a_reminder(planner, automation) -> None:
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  jobs = _task_jobs(automation)
  assert len(jobs) == 1
  job = jobs[0]
  assert job.title == "Call mom"
  assert job.action_type == AutomationActionType.NOTIFY
  assert job.run_at == _at(24, 18)
  assert json.loads(job.action_payload) == {"message": "Call mom", "task_id": task.id}
  assert planner.has_reminder(task)


@pytest.mark.parametrize(
  "due",
  [None, datetime.combine(NOW.date(), DATE_ONLY_TIME, LOCAL_TZ), _at(24, 9)],  # none, date only, past
)
def test_no_reminder_without_future_clock_time(planner, automation, due) -> None:
  planner.add_task("Something", due_at=due)
  assert _task_jobs(automation) == []


def test_reminders_can_be_turned_off(storage, automation) -> None:
  planner = _linked(storage, automation, remind_at_due=False)
  planner.add_task("Call mom", due_at=_at(24, 18))
  assert _task_jobs(automation) == []


def test_done_and_delete_cancel_reminder_reopen_restores(planner, automation) -> None:
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  planner.set_task_status(task.id, TaskStatus.DONE)
  assert _task_jobs(automation) == []
  planner.set_task_status(task.id, TaskStatus.OPEN)
  assert len(_task_jobs(automation)) == 1
  planner.delete_task(task.id)
  assert _task_jobs(automation) == []


def test_changing_due_moves_reminder(planner, automation) -> None:
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  planner.set_task_due(task.id, _at(24, 20))
  jobs = _task_jobs(automation)
  assert [j.run_at for j in jobs] == [_at(24, 20)]


def test_other_reminders_are_untouched(planner, automation) -> None:
  automation.create("Drink water", "drink water", _at(24, 11), action_type=AutomationActionType.NOTIFY,
                    action_payload='{"message": "drink water"}')
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  planner.delete_task(task.id)
  assert [j.title for j in automation.list_jobs(include_done=False)] == ["Drink water"]


def test_reminder_done_completes_task(planner, automation) -> None:
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  job = _task_jobs(automation)[0]
  done = planner.complete_from_job(job.id)
  assert done is not None and done.status == TaskStatus.DONE
  assert planner.get_task(task.id).status == TaskStatus.DONE
  assert planner.complete_from_job(job.id) is None  # already done
  assert planner.complete_from_job(None) is None
  assert planner.complete_from_job("missing") is None


def test_plain_reminder_done_does_not_touch_tasks(planner, automation) -> None:
  job = automation.create("Drink water", "x", _at(24, 11), action_type=AutomationActionType.NOTIFY,
                          action_payload='{"message": "drink water"}')
  assert planner.complete_from_job(job.id) is None


def test_done_on_snoozed_task_reminder_completes_task(planner, automation) -> None:
  bus = EventBus()
  done_events: list = []
  bus.subscribe("notification.done", lambda p: done_events.append(p))
  notifications = NotificationService(automation, event_bus=bus, clock=lambda: _at(24, 18, 1))
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  job = _task_jobs(automation)[0]

  first = notifications.remind(job, "Call mom")
  notifications.handle_action(first.id, "snooze")
  snoozed = [j for j in automation.list_jobs(include_done=False) if j.title.endswith("(snoozed)")][0]
  assert task_id_of(snoozed) == task.id

  second = notifications.remind(snoozed, "Call mom")
  notifications.handle_action(second.id, "done")
  assert planner.complete_from_job(done_events[-1]["job_id"]).id == task.id


def test_roll_over_moves_unfinished_tasks_to_today(planner) -> None:
  old_date = planner.add_task("Pay bill", due_at=datetime.combine(_at(20, 0).date(), DATE_ONLY_TIME, LOCAL_TZ))
  old_timed = planner.add_task("Call bank", due_at=_at(23, 15))
  today_timed = planner.add_task("Standup", due_at=_at(24, 9))  # earlier today: stays
  future = planner.add_task("Gym", due_at=_at(25, 7))
  undated = planner.add_task("Read book")
  finished = planner.add_task("Old done", due_at=_at(21, 9))
  planner.set_task_status(finished.id, TaskStatus.DONE)

  moved = planner.roll_over(NOW)

  assert {t.title for t in moved} == {"Pay bill", "Call bank"}
  for task_id in (old_date.id, old_timed.id):
    due = planner.get_task(task_id).due_at
    assert due.astimezone(LOCAL_TZ).date() == NOW.date() and is_date_only(due)
  assert planner.get_task(today_timed.id).due_at == _at(24, 9)
  assert planner.get_task(future.id).due_at == _at(25, 7)
  assert planner.get_task(undated.id).due_at is None
  assert planner.get_task(finished.id).due_at == _at(21, 9)
  assert planner.roll_over(NOW) == []  # idempotent


def test_roll_over_can_be_turned_off(storage, automation) -> None:
  planner = _linked(storage, automation, roll_over_enabled=False)
  planner.add_task("Pay bill", due_at=_at(20, 9))
  assert planner.roll_over(NOW) == []


def test_chat_confirms_reminder_for_timed_tasks(planner) -> None:
  chat = PlannerChat(planner)
  reply = chat.handle("add task call mom today at 6pm", now=NOW)
  assert reply.text == 'Task add ho gaya: "Call mom" (aaj 6:00 PM). Time pe reminder aayega.'
  reply = chat.handle("add task pay bill tomorrow", now=NOW)
  assert reply.text == 'Task add ho gaya: "Pay bill" (kal).'


def test_chat_done_cancels_reminder(planner, automation) -> None:
  chat = PlannerChat(planner)
  chat.handle("add task call mom today at 6pm", now=NOW)
  chat.handle("call mom ho gaya", now=NOW)
  assert _task_jobs(automation) == []


def test_app_wiring_completes_task_from_reminder_done(qtbot, storage, automation) -> None:
  from PySide6.QtWidgets import QApplication

  from maira.app.bootstrap import _setup_task_links
  from maira.app.container import Container
  from maira.app.lifecycle import Lifecycle

  planner = _linked(storage, automation)
  bus = EventBus()
  container = Container()
  container.register_instance("planner", planner)
  container.register_instance("event_bus", bus)
  changed: list = []
  bus.subscribe("planner.changed", changed.append)
  old = planner.add_task("Pay bill", due_at=_at(20, 9))
  task = planner.add_task("Call mom", due_at=_at(24, 18))
  lifecycle = Lifecycle()

  _setup_task_links(QApplication.instance(), container, lifecycle)
  # Startup roll-over moved the old task to today.
  assert planner.get_task(old.id).due_at.astimezone(LOCAL_TZ).date() == NOW.date()

  job = _task_jobs(automation)[0]
  bus.publish("notification.done", {"job_id": job.id, "title": job.title})
  assert planner.get_task(task.id).status == TaskStatus.DONE
  assert {"reason": "reminder"} in changed
  lifecycle.run_shutdown()
