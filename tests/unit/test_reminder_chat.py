"""Managing reminders from chat, without the AI (it may be offline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import AutomationActionType
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import AutomationRepository, ConversationRepository
from maira.modules.automation.chat import ReminderChat
from maira.modules.automation.service import AutomationService
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE
from tests.unit.test_brain_service import FakeLLM

SOON = datetime.now(timezone.utc) + timedelta(hours=2)


@pytest.fixture
def storage(tmp_path):
  storage = SqliteStorage(tmp_path / "r.db")
  apply_migrations(storage)
  return storage


@pytest.fixture
def automation(storage):
  service = AutomationService(AutomationRepository(storage))
  service.create("Extract the text from this pdf Attached: Ally_Delivery_Plan_", "x", SOON,
                 action_type=AutomationActionType.NOTIFY)
  service.create("Drink water", "drink water", SOON + timedelta(hours=1), action_type=AutomationActionType.NOTIFY)
  service.create("Call mom", "call mom", SOON + timedelta(hours=2), action_type=AutomationActionType.NOTIFY)
  return service


def _titles(automation) -> list[str]:
  return [j.title for j in automation.list_jobs(include_done=False)]


@pytest.mark.parametrize(
  "text",
  ["remove reminder Extract the text", "delete the reminder extract the text from this pdf",
   "cancel reminder ally delivery plan", "extract the text wala reminder hatao"],
)
def test_remove_by_name(automation, text) -> None:
  reply = ReminderChat(automation).handle(text)
  assert reply.startswith('Reminder hata diya: "Extract the text')
  assert _titles(automation) == ["Drink water", "Call mom"]


def test_list_then_remove_by_number(automation) -> None:
  chat = ReminderChat(automation)
  listing = chat.handle("my reminders")
  assert listing.startswith("Pending reminders (3):") and "2. Drink water" in listing
  assert chat.handle("remove reminder 2") == 'Reminder hata diya: "Drink water".'
  assert "Drink water" not in _titles(automation)


def test_ambiguous_and_missing(automation) -> None:
  chat = ReminderChat(automation)
  automation.create("Call dad", "call dad", SOON, action_type=AutomationActionType.NOTIFY)
  reply = chat.handle("remove reminder call")
  assert reply.startswith("Kaunsa reminder?") and len(_titles(automation)) == 4
  assert "naam ka koi pending reminder nahi" in chat.handle("remove reminder dentist")
  assert "Pehle" in ReminderChat(automation).handle("remove reminder 7")


def test_remove_all(automation) -> None:
  assert ReminderChat(automation).handle("cancel all reminders") == "Sab 3 reminder hata diye."
  assert _titles(automation) == []
  assert ReminderChat(automation).handle("reminders") == "Koi reminder pending nahi hai."


@pytest.mark.parametrize("text", ["remind me in 10 minutes to stretch", "how are you", "remove skill pdf", "add task buy milk"])
def test_other_messages_pass_through(automation, text) -> None:
  assert ReminderChat(automation).handle(text) is None


def test_works_in_chat_even_when_the_ai_is_offline(storage, automation) -> None:
  bus = EventBus()
  done: list[str] = []
  bus.subscribe(TOPIC_COMPLETE, lambda p: done.append(p["content"]))
  llm = FakeLLM(available=False)
  brain = BrainService(llm, bus, ConversationRepository(storage), automation=automation)
  brain.send_message("remove reminder Extract the text")
  assert done == ['Reminder hata diya: "Extract the text from this pdf Attached: Ally_Delivery_Plan_".']
  assert llm.calls == []
  # "cancel … at 6pm" must not create a new 6pm reminder.
  brain.send_message("cancel reminder call mom at 6pm")
  assert len(automation.list_jobs(include_done=False)) == 1
