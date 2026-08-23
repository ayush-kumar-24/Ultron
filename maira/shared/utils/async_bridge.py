"""Qt/threading helpers — run blocking work off the UI thread safely."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class Worker(QObject):
  """Runs ``fn`` then emits ``finished`` with "" on success or an error string."""

  finished = Signal(str)

  def __init__(self, fn: Callable[[], Any]) -> None:
    super().__init__()
    self._fn = fn

  @Slot()
  def run(self) -> None:
    error = ""
    try:
      self._fn()
    except Exception as exc:  # noqa: BLE001 — surface to UI layer
      error = str(exc)
    self.finished.emit(error)


def run_in_thread(parent: QObject, fn: Callable[[], Any]) -> QThread:
  """Run ``fn`` on a background QThread owned by ``parent``.

  Returns the thread. Connect to ``thread._maira_worker.finished`` (Signal[str])
  from a slot on ``parent`` so completion is handled on the UI thread.
  Keeps a Python reference to the worker until the thread finishes.
  """
  thread = QThread(parent)
  worker = Worker(fn)
  thread._maira_worker = worker  # type: ignore[attr-defined]

  worker.moveToThread(thread)
  thread.started.connect(worker.run)
  worker.finished.connect(thread.quit)
  worker.finished.connect(worker.deleteLater)
  thread.finished.connect(thread.deleteLater)

  def _clear_ref() -> None:
    thread._maira_worker = None  # type: ignore[attr-defined]

  thread.finished.connect(_clear_ref)
  thread.start()
  return thread
