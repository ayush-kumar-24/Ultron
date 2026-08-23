"""Application lifecycle hooks."""

from collections.abc import Callable

ShutdownHook = Callable[[], None]


class Lifecycle:
  def __init__(self) -> None:
    self._hooks: list[ShutdownHook] = []

  def on_shutdown(self, callback: ShutdownHook) -> None:
    self._hooks.append(callback)

  def run_shutdown(self) -> None:
    for callback in reversed(self._hooks):
      callback()
