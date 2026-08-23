"""QTimer-backed poller that runs due automations while the app is open."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from loguru import logger

from maira.core.interfaces.automation import Automation
from maira.modules.automation.executor import AutomationExecutor


class AutomationRunner(QObject):
  job_ran = Signal(str, bool, str)  # title, ok, message
  jobs_changed = Signal()

  def __init__(
    self,
    automation: Automation,
    executor: AutomationExecutor,
    *,
    interval_ms: int = 15_000,
    parent: QObject | None = None,
  ) -> None:
    super().__init__(parent)
    self._automation = automation
    self._executor = executor
    self._busy = False
    self._timer = QTimer(self)
    self._timer.setInterval(max(5_000, interval_ms))
    self._timer.timeout.connect(self.tick)

  def start(self) -> None:
    if not self._timer.isActive():
      self._timer.start()
      logger.info("Automation runner started (every {}s)", self._timer.interval() // 1000)
      # Catch anything already due on launch.
      QTimer.singleShot(1500, self.tick)

  def stop(self) -> None:
    self._timer.stop()

  def tick(self) -> None:
    if self._busy:
      return
    self._busy = True
    try:
      due = self._automation.due_jobs()
      for job in due:
        logger.info("Running automation '{}' ({})", job.title, job.id)
        result = self._executor.run(job)
        self.job_ran.emit(job.title, result.ok, result.message)
        self.jobs_changed.emit()
    except Exception:  # noqa: BLE001
      logger.exception("Automation runner tick failed")
    finally:
      self._busy = False
