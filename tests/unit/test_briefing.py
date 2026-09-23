"""Daily briefing: content, schedule, runner, chat command, and delivery."""

from __future__ import annotations

import threading
import time as time_mod
from datetime import date, datetime, time, timedelta

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import AutomationActionType, Priority
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRepository,
  ConversationRepository,
  NoteRepository,
  TaskRepository,
)
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.automation.service import AutomationService
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE
from maira.modules.planner.briefing import BriefingService
from maira.modules.planner.briefing.schedule import BriefingSchedule, parse_clock
from maira.modules.planner.chat import PlannerChat
from maira.modules.planner.intent import PlannerAction, parse_planner_request
from maira.modules.planner.service import PlannerService
from tests.unit.test_brain_service import FakeLLM

NOW = datetime(2026, 9, 23, 8, 0, tzinfo=LOCAL_TZ)  # Wednesday morning


def _at(day: int, hour: int, minute: int = 0) -> datetime:
  return datetime(2026, 9, day, hour, minute, tzinfo=LOCAL_TZ)


@pytest.fixture
def storage(tmp_path):
  storage = SqliteStorage(tmp_path / "b.db")
  apply_migrations(storage)
  return storage


@pytest.fixture
def planner(storage):
  return PlannerService(TaskRepository(storage), NoteRepository(storage))


@pytest.fixture
def automation(storage):
  return AutomationService(AutomationRepository(storage))


def test_empty_day(planner, automation) -> None:
  b = BriefingService(planner, automation, name="Ayush").build(NOW)
  assert b.empty
  assert b.text.startswith("Good morning, Ayush! Aaj Wednesday, 23 Sep hai.")
  assert "Aaj ka din free hai" in b.text
  assert b.summary == "Aaj koi task ya reminder nahi."
  assert b.speech == "Good morning, Ayush! Aaj ka din free hai."


def test_full_day(planner, automation) -> None:
  planner.add_task("Pay bill", due_at=_at(22, 23, 59))  # overdue (date only, yesterday)
  planner.add_task("Call mom", due_at=_at(23, 18), priority=Priority.HIGH)
  planner.add_task("Submit report", due_at=_at(23, 23, 59))
  planner.add_task("Buy milk")
  planner.add_task("Gym", due_at=_at(24, 23, 59))
  automation.create("Drink water", "drink water", _at(23, 11), action_type=AutomationActionType.NOTIFY)
  automation.create("Already past", "x", _at(23, 7), action_type=AutomationActionType.NOTIFY)
  automation.create("Tomorrow thing", "x", _at(24, 9), action_type=AutomationActionType.NOTIFY)

  b = BriefingService(planner, automation).build(NOW)

  assert b.text.splitlines() == [
    "Good morning! Aaj Wednesday, 23 Sep hai.",
    "",
    "Overdue (1):",
    "• Pay bill",
    "",
    "Aaj ke tasks (2):",
    "• 6:00 PM — Call mom (high)",
    "• Submit report",
    "",
    "Reminders aaj (1):",
    "• 11:00 AM — Drink water",
    "",
    "Bina date ke (1): Buy milk",
    "",
    "Kal ke liye: 1 task.",
    "",
    'Pehle yeh karo: "Pay bill".',
  ]
  assert b.summary == "2 tasks aaj, 1 overdue, 1 reminder, 1 bina date"
  assert b.speech == "Good morning! Aaj 2 tasks, 1 overdue, 1 reminder hain. Pehle Pay bill karo."
  assert not b.empty


def test_timed_task_later_today_is_not_overdue(planner) -> None:
  planner.add_task("Standup", due_at=_at(23, 10))
  b = BriefingService(planner).build(NOW)
  assert "Overdue" not in b.text
  assert "• 10:00 AM — Standup" in b.text


def test_only_undated_tasks(planner) -> None:
  planner.add_task("Read book", priority=Priority.HIGH)
  b = BriefingService(planner).build(_at(23, 18))
  assert b.text.startswith("Good evening!")
  assert b.speech == "Good evening! Aaj ke liye kuch fixed nahi, par 1 task pending hain. Pehle Read book karo."


@pytest.mark.parametrize(
  "text",
  ["plan my day", "aaj ka plan", "briefing", "morning briefing", "how's my day looking",
   "what's my day", "what's on my schedule today", "mera din kaisa hai", "aaj kya karna hai", "brief me"],
)
def test_briefing_phrases(text) -> None:
  intent = parse_planner_request(text, now=NOW)
  assert intent is not None and intent.action == PlannerAction.BRIEFING


@pytest.mark.parametrize("text", ["how are you", "plan a trip to goa", "what's the weather"])
def test_non_briefing_phrases(text) -> None:
  intent = parse_planner_request(text, now=NOW)
  assert intent is None or intent.action != PlannerAction.BRIEFING


def test_plan_my_day_in_chat(planner, automation) -> None:
  planner.add_task("Call mom", due_at=_at(23, 18))
  chat = PlannerChat(planner, BriefingService(planner, automation))
  reply = chat.handle("plan my day", now=NOW)
  assert reply is not None and not reply.changed
  assert "• 6:00 PM — Call mom" in reply.text


# --- schedule ------------------------------------------------------------------


def test_schedule_once_per_day_within_window(tmp_path) -> None:
  schedule = BriefingSchedule(tmp_path / "state.json", at=time(8, 0), until=time(12, 0))
  assert not schedule.is_due(_at(23, 7, 59))
  assert schedule.is_due(_at(23, 8, 0))
  assert schedule.is_due(_at(23, 11, 30))  # PC started late: still shown
  assert not schedule.is_due(_at(23, 12, 1))  # too late for a morning briefing
  schedule.mark_shown(date(2026, 9, 23))
  assert not schedule.is_due(_at(23, 9))
  assert schedule.is_due(_at(24, 8, 5))
  # State survives restarts.
  again = BriefingSchedule(tmp_path / "state.json", at=time(8, 0), until=time(12, 0))
  assert again.last_shown() == date(2026, 9, 23)


def test_schedule_ignores_corrupt_state(tmp_path) -> None:
  path = tmp_path / "state.json"
  path.write_text("{not json", encoding="utf-8")
  schedule = BriefingSchedule(path, at=time(8, 0), until=time(12, 0))
  assert schedule.last_shown() is None
  assert schedule.is_due(_at(23, 9))


def test_parse_clock() -> None:
  assert parse_clock("07:30", time(8, 0)) == time(7, 30)
  assert parse_clock("7:05", time(8, 0)) == time(7, 5)
  assert parse_clock("late", time(8, 0)) == time(8, 0)
  assert parse_clock("25:00", time(8, 0)) == time(8, 0)


# --- runner --------------------------------------------------------------------


def test_runner_delivers_once(qtbot, tmp_path, planner) -> None:
  from maira.modules.planner.briefing.runner import BriefingRunner

  delivered: list = []
  clock = {"now": _at(23, 7, 0)}
  runner = BriefingRunner(
    BriefingService(planner),
    BriefingSchedule(tmp_path / "s.json", at=time(8, 0), until=time(12, 0)),
    delivered.append,
    clock=lambda: clock["now"],
  )
  assert runner.tick() is False
  clock["now"] = _at(23, 8, 1)
  assert runner.tick() is True
  assert runner.tick() is False  # already shown today
  assert len(delivered) == 1 and delivered[0].text.startswith("Good morning")


def test_runner_failure_does_not_repeat(qtbot, tmp_path, planner) -> None:
  from maira.modules.planner.briefing.runner import BriefingRunner

  calls: list = []

  def broken(item):
    calls.append(item)
    raise RuntimeError("boom")

  runner = BriefingRunner(
    BriefingService(planner),
    BriefingSchedule(tmp_path / "s.json", at=time(8, 0), until=time(12, 0)),
    broken,
    clock=lambda: _at(23, 9),
  )
  assert runner.tick() is True
  assert runner.tick() is False
  assert len(calls) == 1


# --- delivery --------------------------------------------------------------------


def test_brain_announce_posts_to_chat_and_history(storage) -> None:
  bus = EventBus()
  completed: list = []
  bus.subscribe(TOPIC_COMPLETE, lambda p: completed.append(p["content"]))
  brain = BrainService(FakeLLM(), bus, ConversationRepository(storage))
  brain.announce("Good morning!")
  assert completed == ["Good morning!"]
  assert brain.get_history()[-1].content == "Good morning!"
  stored = ConversationRepository(storage).get_messages(brain.get_active_conversation().id)
  assert stored[-1].content == "Good morning!"


def test_announce_waits_for_a_reply_in_progress(storage) -> None:
  class SlowLLM(FakeLLM):
    def chat_stream(self, messages, *, options=None):
      yield "part1"
      time_mod.sleep(0.3)
      yield " part2"

  bus = EventBus()
  order: list = []
  bus.subscribe(TOPIC_COMPLETE, lambda p: order.append(p["content"]))
  brain = BrainService(SlowLLM(), bus, ConversationRepository(storage))
  chat = threading.Thread(target=brain.send_message, args=("hello",))
  chat.start()
  time_mod.sleep(0.1)
  brain.announce("Briefing")
  chat.join()
  assert order == ["part1 part2", "Briefing"]


def test_voice_announce(voice_stack) -> None:
  voice, _brain, _audio, _stt, tts, _events = voice_stack
  assert voice.announce("Good morning") is True
  deadline = time_mod.time() + 2
  while not tts.spoken and time_mod.time() < deadline:
    time_mod.sleep(0.02)
  assert tts.spoken == ["Good morning"]
  assert voice.announce("   ") is False


def test_notification_announce(automation) -> None:
  from maira.modules.notifications.service import NotificationService
  from tests.unit.test_notifications import FakeNotifier

  service = NotificationService(automation)
  backend = FakeNotifier()
  service.add_notifier(backend)
  assert service.announce("Aaj ka plan", "2 tasks aaj") == "fake"
  shown = backend.shown[0]
  assert (shown.title, shown.body, shown.actions) == ("Aaj ka plan", "2 tasks aaj", ())


from tests.unit.test_voice_service import voice_stack  # noqa: E402, F401  (fixture)
