"""Unit tests for reminder notifications, snooze, and recurring catch-up."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
)
from maira.core.interfaces.notifier import Notification, NotificationAction, Notifier
from maira.infrastructure.notifications.windows_toast import (
  WindowsToastNotifier,
  decode_arguments,
  encode_arguments,
)
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import AutomationRepository
from maira.modules.automation.executor import AutomationExecutor
from maira.modules.automation.service import AutomationService
from maira.modules.notifications.service import NotificationService

NOW = datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc)


class FakeNotifier(Notifier):
  def __init__(self, *, available: bool = True, accepts: bool = True) -> None:
    self.available = available
    self.accepts = accepts
    self.shown: list[Notification] = []

  def name(self) -> str:
    return "fake"

  def is_available(self) -> bool:
    return self.available

  def show(self, notification: Notification) -> bool:
    self.shown.append(notification)
    return self.accepts


@pytest.fixture
def automation(tmp_path) -> AutomationService:
  storage = SqliteStorage(tmp_path / "test.db")
  apply_migrations(storage)
  return AutomationService(AutomationRepository(storage))


def _service(automation, *, bus=None, now=NOW) -> NotificationService:
  return NotificationService(automation, event_bus=bus, snooze_minutes=10, local_tz=timezone.utc, clock=lambda: now)


def _reminder(automation, run_at=NOW, recurrence=AutomationRecurrence.NONE):
  return automation.create(
    "Drink water",
    "drink water",
    run_at,
    action_type=AutomationActionType.NOTIFY,
    action_payload='{"message": "drink water"}',
    recurrence=recurrence,
  )


def test_remind_shows_with_done_and_snooze(automation) -> None:
  service = _service(automation)
  notifier = FakeNotifier()
  service.add_notifier(notifier)
  job = _reminder(automation)

  notification = service.remind(job, "drink water")

  assert notifier.shown == [notification]
  assert notification.title == "Drink water"
  assert notification.body == "drink water"
  assert notification.job_id == job.id
  assert notification.actions == (NotificationAction.DONE, NotificationAction.SNOOZE)


def test_unavailable_backend_is_skipped(automation) -> None:
  service = _service(automation)
  service.add_notifier(FakeNotifier(available=False))
  assert not service.has_backend()


def test_falls_back_to_next_backend(automation) -> None:
  service = _service(automation)
  first = FakeNotifier(accepts=False)
  second = FakeNotifier()
  service.add_notifier(first)
  service.add_notifier(second)

  service.remind(_reminder(automation), "drink water")

  assert len(first.shown) == 1
  assert len(second.shown) == 1


def test_crashing_backend_does_not_break_reminder(automation) -> None:
  class Broken(FakeNotifier):
    def show(self, notification):
      raise RuntimeError("boom")

  service = _service(automation)
  backup = FakeNotifier()
  service.add_notifier(Broken())
  service.add_notifier(backup)

  service.remind(_reminder(automation), "drink water")
  assert len(backup.shown) == 1


def test_late_reminder_says_when_it_was_due(automation) -> None:
  service = _service(automation, now=NOW + timedelta(hours=3))
  notification = service.remind(_reminder(automation), "drink water")
  assert notification.body == "drink water\nMissed at 9:00 AM"


def test_on_time_reminder_has_no_missed_note(automation) -> None:
  service = _service(automation, now=NOW + timedelta(seconds=30))
  notification = service.remind(_reminder(automation), "drink water")
  assert "Missed" not in notification.body


def test_snooze_creates_one_shot_reminder(automation) -> None:
  bus = EventBus()
  changed: list = []
  bus.subscribe("automation.changed", changed.append)
  service = _service(automation, bus=bus, now=NOW + timedelta(hours=1))
  job = _reminder(automation, recurrence=AutomationRecurrence.DAILY)
  notification = service.remind(job, "drink water")

  message = service.handle_action(notification.id, "snooze")

  assert message == "Snoozed for 10 min: Drink water"
  assert changed == [None]
  snoozed = [j for j in automation.list_jobs() if j.id != job.id]
  assert len(snoozed) == 1
  new = snoozed[0]
  assert new.title == "Drink water (snoozed)"
  assert new.recurrence == AutomationRecurrence.NONE
  assert new.action_type == AutomationActionType.NOTIFY
  assert json.loads(new.action_payload) == {"message": "drink water"}
  assert new.run_at == NOW + timedelta(hours=1, minutes=10)
  # The daily original is untouched.
  assert automation.get(job.id).recurrence == AutomationRecurrence.DAILY


def test_snoozing_twice_does_not_stack_suffix_or_missed_note(automation) -> None:
  service = _service(automation, now=NOW + timedelta(hours=2))
  first = service.remind(_reminder(automation), "drink water")
  service.handle_action(first.id, "snooze")
  snoozed = next(j for j in automation.list_jobs() if j.title.endswith("(snoozed)"))

  second = service.remind(snoozed, "drink water")
  service.handle_action(second.id, "snooze")

  titles = sorted(j.title for j in automation.list_jobs())
  assert titles == ["Drink water", "Drink water (snoozed)", "Drink water (snoozed)"]
  assert all("Missed" not in j.instruction for j in automation.list_jobs())


def test_done_publishes_event_and_is_idempotent(automation) -> None:
  bus = EventBus()
  done: list = []
  bus.subscribe("notification.done", done.append)
  service = _service(automation, bus=bus)
  job = _reminder(automation)
  notification = service.remind(job, "drink water")

  assert service.handle_action(notification.id, "done") == "Done: Drink water"
  assert service.handle_action(notification.id, "done") is None
  assert service.handle_action(notification.id, "snooze") is None
  assert done == [{"job_id": job.id, "title": "Drink water"}]
  assert len(automation.list_jobs()) == 1


def test_open_action_calls_handler(automation) -> None:
  service = _service(automation)
  opened: list = []
  service.set_open_handler(lambda: opened.append(True))
  notification = service.remind(_reminder(automation), "drink water")

  assert service.handle_action(notification.id, "open") is None
  assert opened == [True]
  # Opening does not consume the notification; its buttons still work.
  assert service.handle_action(notification.id, "done") == "Done: Drink water"


def test_unknown_action_is_ignored(automation) -> None:
  service = _service(automation)
  notification = service.remind(_reminder(automation), "drink water")
  assert service.handle_action(notification.id, "explode") is None


def test_tracked_notifications_are_bounded(automation) -> None:
  service = _service(automation)
  job = _reminder(automation)
  first = service.remind(job, "one")
  for _ in range(60):
    service.remind(job, "more")
  assert service.handle_action(first.id, "done") is None


def test_executor_routes_notify_jobs_to_reminder_callback(automation) -> None:
  reminders: list = []
  notes: list = []
  job = _reminder(automation, run_at=datetime.now(timezone.utc) - timedelta(seconds=5))
  executor = AutomationExecutor(
    automation,
    on_notify=notes.append,
    on_reminder=lambda j, m: reminders.append((j.id, m)),
  )

  result = executor.run(job)

  assert result.ok
  assert reminders == [(job.id, "drink water")]
  assert notes == []
  assert automation.get(job.id).status == AutomationStatus.DONE


def test_daily_job_skips_missed_days_after_long_downtime(automation) -> None:
  job = _reminder(automation, run_at=NOW, recurrence=AutomationRecurrence.DAILY)
  later = NOW + timedelta(days=5, hours=2)
  nxt = automation.next_run_after(job, now=later)
  assert nxt == NOW + timedelta(days=6)


def test_daily_job_on_time_moves_one_day(automation) -> None:
  job = _reminder(automation, run_at=NOW, recurrence=AutomationRecurrence.DAILY)
  assert automation.next_run_after(job, now=NOW + timedelta(seconds=3)) == NOW + timedelta(days=1)


def test_weekly_job_skips_missed_weeks(automation) -> None:
  job = _reminder(automation, run_at=NOW, recurrence=AutomationRecurrence.WEEKLY)
  nxt = automation.next_run_after(job, now=NOW + timedelta(weeks=3))
  assert nxt == NOW + timedelta(weeks=4)


def test_one_shot_job_has_no_next_run(automation) -> None:
  job = _reminder(automation)
  assert automation.next_run_after(job, now=NOW) is None


def test_toast_arguments_round_trip() -> None:
  encoded = encode_arguments(NotificationAction.SNOOZE, "abc123")
  assert decode_arguments(encoded) == ("abc123", "snooze")
  assert decode_arguments(None) is None
  assert decode_arguments("") is None
  assert decode_arguments("snooze") is None
  assert decode_arguments("snooze|") is None


def test_windows_toast_unavailable_off_windows(monkeypatch) -> None:
  monkeypatch.setattr("maira.infrastructure.notifications.windows_toast.os.name", "posix")
  notifier = WindowsToastNotifier(lambda *_: None)
  assert not notifier.is_available()
  assert not notifier.show(Notification("id", "t", "b"))


def test_windows_toast_activation_forwards_action() -> None:
  calls: list = []
  notifier = WindowsToastNotifier(lambda nid, action: calls.append((nid, action)))

  class Args:
    arguments = "done|n1"

  notifier._activated(Args())  # noqa: SLF001
  notifier._activated(type("Empty", (), {"arguments": None})())  # noqa: SLF001
  assert calls == [("n1", "done")]


class NamedNotifier(FakeNotifier):
  def __init__(self, label: str, **kwargs) -> None:
    super().__init__(**kwargs)
    self.label = label

  def name(self) -> str:
    return self.label


def test_remind_logs_backend_and_retry_skips_failed_backend(automation) -> None:
  service = _service(automation)
  toast = NamedNotifier("windows-toast")
  balloon = NamedNotifier("tray-balloon")
  service.add_notifier(toast)
  service.add_notifier(balloon)
  notification = service.remind(_reminder(automation), "drink water")
  assert len(toast.shown) == 1 and balloon.shown == []

  # Windows later reports the toast as failed: re-show with the next backend.
  assert service.retry_without(notification.id, "windows-toast") == "tray-balloon"
  assert balloon.shown == [notification]
  assert len(toast.shown) == 1


def test_retry_for_unknown_notification_is_noop(automation) -> None:
  service = _service(automation)
  service.add_notifier(NamedNotifier("tray-balloon"))
  assert service.retry_without("missing", "windows-toast") is None


def test_send_test_notification(automation) -> None:
  service = _service(automation)
  assert service.send_test() is None  # no backend yet
  backend = NamedNotifier("windows-toast")
  service.add_notifier(backend)
  assert service.send_test() == "windows-toast"
  shown = backend.shown[-1]
  assert shown.job_id is None
  assert service.handle_action(shown.id, "done") == f"Done: {shown.title}"


def test_windows_toast_failure_calls_back_with_notification_id() -> None:
  failed: list = []
  notifier = WindowsToastNotifier(lambda *_: None, on_failed=failed.append)

  class Args:
    error_code = -2143420143

  notifier._failed("n42", Args())  # noqa: SLF001
  assert failed == ["n42"]
