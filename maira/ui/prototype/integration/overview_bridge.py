"""Bridge: Home Today panel, Activity timeline and search ↔ real data."""

from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.planner import Planner
from maira.modules.planner.overview import activity_feed, home_overview, search_everything
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.screens.home import HomeScreen

LIVE_QUICK_ACTIONS = [
  {"id": "plan", "label": "Plan my day"},
  {"id": "pending", "label": "What's pending?"},
  {"id": "add_task", "label": "Add a task"},
  {"id": "reminder", "label": "Set a reminder"},
]

LIVE_COMMANDS = [
  {"id": "plan", "label": "Plan my day", "hint": "Briefing"},
  {"id": "task", "label": "Create task", "hint": "Tasks"},
  {"id": "note", "label": "Create note", "hint": "Notes"},
  {"id": "memory", "label": "Search memory", "hint": "Memory"},
  {"id": "voice", "label": "Dictate (mic)", "hint": "Chat"},
  {"id": "search", "label": "Search tasks, notes, memory", "hint": "Search"},
  {"id": "settings", "label": "Open settings", "hint": "Settings"},
  {"id": "status", "label": "System status", "hint": "Status"},
]

SEARCH_CATEGORIES = ["Everything", "Tasks", "Notes", "Memory"]

_REFRESH_TOPICS = ("planner.changed", "automation.changed", "notification.done", "automation.notify")


class OverviewBridge(QObject):
  # Events arrive from worker threads; refresh on the UI thread.
  _changed = Signal()

  def __init__(
    self,
    planner: Planner,
    automation: Automation | None,
    memory,
    event_bus: EventBus,
    home: HomeScreen,
    store: MockStore,
  ) -> None:
    super().__init__()
    self._planner = planner
    self._automation = automation
    self._memory = memory
    self._home = home
    self._store = store

    store.set_live(
      search=lambda query, category: search_everything(planner, memory, query, category),
      commands=LIVE_COMMANDS,
      quick_actions=LIVE_QUICK_ACTIONS,
    )
    home.set_quick_actions(LIVE_QUICK_ACTIONS)

    self._changed.connect(self.refresh)
    for topic in _REFRESH_TOPICS:
      event_bus.subscribe(topic, lambda _p: self._changed.emit())
    # Times like "in 5 minutes" / overdue change on their own.
    self._timer = QTimer(self)
    self._timer.setInterval(60_000)
    self._timer.timeout.connect(self.refresh)
    self._timer.start()
    self.refresh()

  def refresh(self) -> None:
    try:
      self._home.set_overview(home_overview(self._planner, self._automation))
      self._store.activity = activity_feed(self._planner, self._automation)
      self._store.changed.emit("activity")
    except Exception:  # noqa: BLE001
      logger.exception("Home overview refresh failed")
