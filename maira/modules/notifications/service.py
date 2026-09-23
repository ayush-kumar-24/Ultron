"""Notification facade — show reminders through OS backends and handle actions."""

from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from loguru import logger

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import AutomationJob
from maira.core.domain.value_objects import AutomationActionType
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.notifier import Notification, NotificationAction, Notifier

# A reminder fired this late (e.g. the PC was off) says when it was due.
LATE_AFTER = timedelta(minutes=2)
SNOOZE_SUFFIX = " (snoozed)"
_MAX_TRACKED = 50

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
  return datetime.now(timezone.utc)


class NotificationService:
  def __init__(
    self,
    automation: Automation,
    *,
    event_bus: EventBus | None = None,
    snooze_minutes: int = 10,
    local_tz=None,
    clock: Clock = _utc_now,
  ) -> None:
    self._automation = automation
    self._event_bus = event_bus
    self._snooze = timedelta(minutes=max(1, snooze_minutes))
    self._local_tz = local_tz
    self._clock = clock
    self._notifiers: list[Notifier] = []
    self._tracked: OrderedDict[str, Notification] = OrderedDict()
    self._on_open: Callable[[], None] | None = None

  @property
  def snooze_minutes(self) -> int:
    return int(self._snooze.total_seconds() // 60)

  def add_notifier(self, notifier: Notifier) -> None:
    """Register a backend. Earlier backends are preferred."""
    if notifier.is_available():
      self._notifiers.append(notifier)
      logger.info("Notification backend ready: {}", notifier.name())
    else:
      logger.info("Notification backend unavailable: {}", notifier.name())

  def has_backend(self) -> bool:
    return bool(self._notifiers)

  def set_open_handler(self, handler: Callable[[], None]) -> None:
    self._on_open = handler

  def remind(self, job: AutomationJob, message: str) -> Notification:
    """Show a reminder for a due job. Returns the notification (shown or not)."""
    body = message.strip() or job.title
    late_by = self._clock() - job.run_at
    if late_by > LATE_AFTER:
      body = f"{body}\nMissed at {self._format_time(job.run_at)}"

    notification = Notification(
      id=uuid.uuid4().hex,
      title=job.title or "Reminder",
      body=body,
      job_id=job.id,
      actions=(NotificationAction.DONE, NotificationAction.SNOOZE),
    )
    self._track(notification)
    self._show(notification)
    return notification

  def send_test(self) -> str | None:
    """Show a sample notification. Returns the backend that showed it."""
    notification = Notification(
      id=uuid.uuid4().hex,
      title="Ultron notifications work",
      body="Your reminders will pop up like this.",
      actions=(NotificationAction.DONE,),
    )
    self._track(notification)
    return self._show(notification)

  def retry_without(self, notification_id: str, failed_backend: str) -> str | None:
    """A backend failed asynchronously: show the same notification with the next one."""
    notification = self._tracked.get(notification_id)
    if notification is None:
      return None
    return self._show(notification, skip={failed_backend})

  def handle_action(self, notification_id: str, action: str) -> str | None:
    """Apply a button click. Returns a short status message, or None if ignored."""
    try:
      kind = NotificationAction(action)
    except ValueError:
      logger.warning("Unknown notification action: {}", action)
      return None

    if kind == NotificationAction.OPEN:
      if self._on_open:
        self._on_open()
      return None

    notification = self._tracked.pop(notification_id, None)
    if notification is None:
      logger.info("Notification {} already handled or expired", notification_id)
      return None

    if kind == NotificationAction.SNOOZE:
      return self._snooze_reminder(notification)

    self._publish("notification.done", {"job_id": notification.job_id, "title": notification.title})
    return f"Done: {notification.title}"

  def _snooze_reminder(self, notification: Notification) -> str:
    # Snooze creates a separate one-shot job so a daily reminder keeps its schedule.
    title = notification.title
    if not title.endswith(SNOOZE_SUFFIX):
      title += SNOOZE_SUFFIX
    message = notification.body.split("\nMissed at ")[0]
    run_at = self._clock() + self._snooze
    self._automation.create(
      title,
      message,
      run_at,
      action_type=AutomationActionType.NOTIFY,
      action_payload=json.dumps({"message": message}),
    )
    self._publish("automation.changed", None)
    return f"Snoozed for {self.snooze_minutes} min: {notification.title}"

  def _show(self, notification: Notification, *, skip: set[str] | None = None) -> str | None:
    """Try backends in order. Returns the name of the one that showed it."""
    for notifier in self._notifiers:
      if skip and notifier.name() in skip:
        continue
      try:
        if notifier.show(notification):
          logger.info("Notification '{}' sent via {}", notification.title, notifier.name())
          return notifier.name()
      except Exception:  # noqa: BLE001
        logger.exception("Notification backend {} failed", notifier.name())
    logger.warning("No notification backend showed: {}", notification.title)
    return None

  def _track(self, notification: Notification) -> None:
    self._tracked[notification.id] = notification
    while len(self._tracked) > _MAX_TRACKED:
      self._tracked.popitem(last=False)

  def _format_time(self, moment: datetime) -> str:
    local = moment.astimezone(self._local_tz) if self._local_tz else moment.astimezone()
    return local.strftime("%I:%M %p").lstrip("0")

  def _publish(self, topic: str, payload) -> None:
    if self._event_bus is not None:
      self._event_bus.publish(topic, payload)
