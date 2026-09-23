"""QTimer that shows the daily briefing once a day."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from loguru import logger
from PySide6.QtCore import QObject, QTimer

from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.briefing import Briefing, BriefingService
from maira.modules.planner.briefing.schedule import BriefingSchedule

Deliver = Callable[[Briefing], None]


class BriefingRunner(QObject):
  def __init__(
    self,
    briefing: BriefingService,
    schedule: BriefingSchedule,
    deliver: Deliver,
    *,
    interval_ms: int = 60_000,
    first_check_ms: int = 15_000,
    clock: Callable[[], datetime] | None = None,
    parent: QObject | None = None,
  ) -> None:
    super().__init__(parent)
    self._briefing = briefing
    self._schedule = schedule
    self._deliver = deliver
    self._first_check_ms = first_check_ms
    self._clock = clock or (lambda: datetime.now(LOCAL_TZ))
    self._timer = QTimer(self)
    self._timer.setInterval(interval_ms)
    self._timer.timeout.connect(self.tick)

  def start(self) -> None:
    if not self._timer.isActive():
      self._timer.start()
      # Let the app settle (voice warm-up, window) before a startup briefing.
      QTimer.singleShot(self._first_check_ms, self.tick)

  def stop(self) -> None:
    self._timer.stop()

  def tick(self) -> bool:
    now = self._clock()
    if not self._schedule.is_due(now):
      return False
    # Mark first: a failing delivery must not repeat every minute.
    self._schedule.mark_shown(now.date())
    try:
      self._deliver(self._briefing.build(now))
      logger.info("Daily briefing shown")
    except Exception:  # noqa: BLE001
      logger.exception("Daily briefing failed")
    return True
