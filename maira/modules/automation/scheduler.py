"""Thread-backed poller that runs due automations without Qt.

The desktop app drives automations from a QTimer. The headless API server has
no Qt event loop, so it uses this scheduler instead — same executor, same jobs,
so a reminder fires whether you run the desktop app or just the server.
"""

from __future__ import annotations

import threading

from loguru import logger

from maira.core.interfaces.automation import Automation
from maira.modules.automation.executor import AutomationExecutor


class AutomationScheduler:
  def __init__(
    self,
    automation: Automation,
    executor: AutomationExecutor,
    *,
    interval_seconds: float = 15.0,
    on_job_ran=None,
  ) -> None:
    self._automation = automation
    self._executor = executor
    self._interval = max(5.0, interval_seconds)
    self._on_job_ran = on_job_ran
    self._stop = threading.Event()
    self._thread: threading.Thread | None = None

  @property
  def running(self) -> bool:
    return self._thread is not None and self._thread.is_alive()

  def start(self) -> None:
    if self.running:
      return
    self._stop.clear()
    self._thread = threading.Thread(target=self._loop, name="ultron-automations", daemon=True)
    self._thread.start()
    logger.info("Automation scheduler started (every {}s)", int(self._interval))

  def stop(self) -> None:
    self._stop.set()
    thread = self._thread
    if thread is not None and thread.is_alive():
      thread.join(timeout=5.0)
    self._thread = None

  def _loop(self) -> None:
    # Catch anything already due at startup, then poll.
    self._stop.wait(1.5)
    while not self._stop.is_set():
      self.tick()
      self._stop.wait(self._interval)

  def run_now(self, job):
    """Fire one job immediately, outside the poll loop."""
    result = self._executor.run(job)
    if self._on_job_ran is not None:
      self._on_job_ran(job, result)
    return result

  def tick(self) -> int:
    """Run every due job. Returns how many ran."""
    ran = 0
    try:
      for job in self._automation.due_jobs():
        logger.info("Running automation '{}' ({})", job.title, job.id)
        result = self._executor.run(job)
        ran += 1
        if self._on_job_ran is not None:
          self._on_job_ran(job, result)
    except Exception:  # noqa: BLE001 - a bad job must not kill the loop
      logger.exception("Automation scheduler tick failed")
    return ran
