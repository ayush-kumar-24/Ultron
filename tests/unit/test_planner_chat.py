"""Tasks and notes from chat: parsing, actions, replies, and brain routing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import Priority, TaskStatus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  ConversationRepository,
  NoteRepository,
  TaskRepository,
)
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE
from maira.modules.planner.chat import PlannerChat, format_due, is_overdue
from maira.modules.planner.intent import PlannerAction, parse_planner_request
from maira.modules.planner.service import PlannerService
from tests.unit.test_brain_service import FakeLLM

NOW = datetime(2026, 9, 23, 10, 0, tzinfo=LOCAL_TZ)  # Wednesday


@pytest.fixture
def storage(tmp_path: Path) -> SqliteStorage:
  storage = SqliteStorage(tmp_path / "planner.db")
  apply_migrations(storage)
  return storage


@pytest.fixture
def planner(storage) -> PlannerService:
  return PlannerService(TaskRepository(storage), NoteRepository(storage))


@pytest.fixture
def chat(planner) -> PlannerChat:
  return PlannerChat(planner)


def _say(chat: PlannerChat, text: str) -> str | None:
  reply = chat.handle(text, now=NOW)
  return reply.text if reply else None


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
  ("text", "title", "due", "priority"),
  [
    ("add task pay bill tomorrow", "Pay bill", "Thu 23:59", Priority.MEDIUM),
    ("add task pay electricity bill tomorrow at 5pm urgent", "Pay electricity bill", "Thu 17:00", Priority.HIGH),
    ("task: call mom", "Call mom", None, Priority.MEDIUM),
    ("todo: buy milk today", "Buy milk", "Wed 23:59", Priority.MEDIUM),
    ("add buy groceries to my list", "Buy groceries", None, Priority.MEDIUM),
    ("pay bill ka task add karo", "Pay bill", None, Priority.MEDIUM),
    ("task add karo gym jana kal", "Gym jana", "Thu 23:59", Priority.MEDIUM),
    ("new task submit report on friday", "Submit report", "Fri 23:59", Priority.MEDIUM),
    ("parso tak report submit karna task add karo", "Report submit karna", "Fri 23:59", Priority.MEDIUM),
    ("add task send invoice in 2 hours", "Send invoice", "Wed 12:00", Priority.MEDIUM),
  ],
)
def test_parse_add_task(text, title, due, priority) -> None:
  intent = parse_planner_request(text, now=NOW)
  assert intent is not None and intent.action == PlannerAction.ADD_TASK
  assert intent.text == title
  assert intent.priority == priority
  if due is None:
    assert intent.due_at is None
  else:
    assert intent.due_at.astimezone(LOCAL_TZ).strftime("%a %H:%M") == due


@pytest.mark.parametrize(
  ("text", "today_only"),
  [
    ("what's pending", False),
    ("show my tasks", False),
    ("pending kya hai", False),
    ("my tasks", False),
    ("aaj ke tasks", True),
    ("what's pending today", True),
  ],
)
def test_parse_list(text, today_only) -> None:
  intent = parse_planner_request(text, now=NOW)
  assert intent is not None and intent.action == PlannerAction.LIST_TASKS
  assert intent.today_only is today_only


@pytest.mark.parametrize(
  ("text", "action", "ref", "strict"),
  [
    ("mark pay bill done", PlannerAction.COMPLETE_TASK, "pay bill", True),
    ("done 2", PlannerAction.COMPLETE_TASK, "2", True),
    ("complete task pay bill", PlannerAction.COMPLETE_TASK, "pay bill", True),
    ("pay bill ho gaya", PlannerAction.COMPLETE_TASK, "pay bill", False),
    ("delete task buy milk", PlannerAction.DELETE_TASK, "buy milk", True),
    ("remove buy milk from my list", PlannerAction.DELETE_TASK, "buy milk", True),
    ("buy milk wala task delete karo", PlannerAction.DELETE_TASK, "buy milk", True),
    ("note: call Rahul about project", PlannerAction.ADD_NOTE, "call Rahul about project", True),
    ("take a note that wifi password is abc", PlannerAction.ADD_NOTE, "wifi password is abc", True),
  ],
)
def test_parse_other_actions(text, action, ref, strict) -> None:
  intent = parse_planner_request(text, now=NOW)
  assert intent is not None
  assert (intent.action, intent.text, intent.strict) == (action, ref, strict)


@pytest.mark.parametrize(
  "text",
  ["what is a task manager", "remind me in 1 minute to drink water", "open youtube", "kaise ho", "", "tell me a joke"],
)
def test_non_planner_messages_are_ignored(text) -> None:
  assert parse_planner_request(text, now=NOW) is None


# --- actions -----------------------------------------------------------------


def test_add_list_complete_delete_flow(chat, planner) -> None:
  assert _say(chat, "add task pay bill tomorrow") == 'Task add ho gaya: "Pay bill" (kal).'
  assert _say(chat, "add task call mom today at 6pm urgent") == 'Task add ho gaya: "Call mom" (aaj 6:00 PM, high priority).'
  _say(chat, "todo: buy milk")

  listing = _say(chat, "what's pending")
  assert listing.splitlines()[:4] == [
    "Pending tasks (3):",
    "1. Call mom — aaj 6:00 PM, high",
    "2. Pay bill — kal",
    "3. Buy milk",
  ]

  assert _say(chat, "done 2") == 'Badhiya! "Pay bill" done mark kar diya.'
  assert _say(chat, "delete task milk") == 'Task delete kar diya: "Buy milk".'
  statuses = {t.title: t.status for t in planner.list_tasks()}
  assert statuses == {"Call mom": TaskStatus.OPEN, "Pay bill": TaskStatus.DONE}


def test_empty_list(chat) -> None:
  assert _say(chat, "what's pending") == "Koi pending task nahi hai. Sab clear!"


def test_today_list_includes_overdue_and_undated_only(chat) -> None:
  _say(chat, "add task pay bill tomorrow")
  _say(chat, "task: call mom")
  listing = _say(chat, "aaj ke tasks")
  assert "Call mom" in listing and "Pay bill" not in listing


def test_loose_done_only_acts_on_real_task(chat) -> None:
  _say(chat, "task: go to gym")
  assert _say(chat, "I'm done") is None  # goes to the LLM
  assert _say(chat, "all done") is None
  assert _say(chat, "gym ho gaya") == 'Badhiya! "Go to gym" done mark kar diya.'


def test_ambiguous_reference_asks_which(chat) -> None:
  _say(chat, "task: pay electricity bill")
  _say(chat, "task: pay phone bill")
  reply = _say(chat, "mark pay bill done")
  assert reply.startswith("Kaunsa task?")
  assert "1. " in reply and "2. " in reply
  # Numbers now refer to the options just shown.
  assert _say(chat, "done 1").startswith('Badhiya! "Pay')


def test_unknown_reference_and_bad_number(chat) -> None:
  assert "nahi mila" in _say(chat, "complete task xyz")
  assert _say(chat, "done 3").startswith("Pehle")
  _say(chat, "task: one")
  _say(chat, "what's pending")
  assert _say(chat, "done 9") == "List mein number 9 nahi hai."


def test_note_is_saved(chat, planner) -> None:
  reply = _say(chat, "note: call Rahul about the project deadline next week")
  assert reply == 'Note save ho gaya: "Call Rahul about the project deadline…".'
  note = planner.list_notes()[0]
  assert note.body == "call Rahul about the project deadline next week"


def test_format_due_and_overdue(planner) -> None:
  from maira.modules.planner.intent import parse_due

  assert format_due(parse_due("tomorrow", NOW), NOW) == "kal"
  assert format_due(parse_due("today at 6pm", NOW), NOW) == "aaj 6:00 PM"
  assert format_due(parse_due("friday", NOW), NOW) == "Friday"
  task = planner.add_task("Old", due_at=datetime(2026, 9, 21, 23, 59, tzinfo=LOCAL_TZ))
  assert is_overdue(task, NOW)
  today = planner.add_task("Today", due_at=parse_due("today", NOW))
  assert not is_overdue(today, NOW)


# --- brain routing -------------------------------------------------------------


def test_brain_answers_task_commands_without_llm(storage, planner) -> None:
  bus = EventBus()
  llm = FakeLLM(["from", " llm"])
  changed: list = []
  completed: list = []
  bus.subscribe("planner.changed", changed.append)
  bus.subscribe(TOPIC_COMPLETE, lambda p: completed.append(p["content"]))
  brain = BrainService(llm, bus, ConversationRepository(storage), planner=planner)

  brain.send_message("add task pay bill tomorrow")
  brain.send_message("what's pending")
  brain.send_message("kaise ho")

  assert completed[0] == 'Task add ho gaya: "Pay bill" (kal).'
  assert completed[1].startswith("Pending tasks (1):")
  assert completed[2] == "from llm"
  assert len(llm.calls) == 1  # only "kaise ho" reached the model
  assert changed == [{"reason": "chat"}]  # listing does not count as a change
  history = [m.content for m in brain.get_history()]
  assert history[:2] == ["add task pay bill tomorrow", 'Task add ho gaya: "Pay bill" (kal).']


def test_brain_handles_task_commands_by_voice(storage, planner) -> None:
  bus = EventBus()
  llm = FakeLLM()
  brain = BrainService(llm, bus, ConversationRepository(storage), planner=planner)
  brain.send_message("task: call mom", voice=True)
  assert [t.title for t in planner.list_tasks()] == ["Call mom"]
  assert llm.calls == []


def test_task_command_wins_over_schedule(storage, planner) -> None:
  """'add task … tomorrow at 5pm' is a task with a due time, not a reminder job."""

  class Automation:
    created = False

    def create(self, *a, **k):
      Automation.created = True

  bus = EventBus()
  brain = BrainService(FakeLLM(), bus, ConversationRepository(storage), planner=planner, automation=Automation())
  brain.send_message("add task pay bill tomorrow at 5pm")
  assert not Automation.created
  assert planner.list_tasks()[0].title == "Pay bill"


@pytest.mark.parametrize("text", ["complete this code for me", "finish the story about a dragon", "done with lunch"])
def test_llm_requests_that_look_like_completion_reach_the_llm(chat, text) -> None:
  _say(chat, "task: pay bill")
  assert _say(chat, text) is None


def test_bare_complete_still_marks_matching_task(chat) -> None:
  _say(chat, "task: submit report")
  assert _say(chat, "complete submit report") == 'Badhiya! "Submit report" done mark kar diya.'
  _say(chat, "task: write essay")
  assert _say(chat, "finish essay") == 'Badhiya! "Write essay" done mark kar diya.'
