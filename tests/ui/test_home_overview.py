"""Home screen shows real data in live mode and refreshes safely."""

from __future__ import annotations

import threading

from maira.core.bus.event_bus import EventBus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import AutomationRepository, NoteRepository, TaskRepository
from maira.modules.automation.service import AutomationService
from maira.modules.planner.service import PlannerService
from maira.ui.prototype.integration.overview_bridge import LIVE_COMMANDS, LIVE_QUICK_ACTIONS, OverviewBridge
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.screens.home import HomeScreen


def _setup(qtbot, tmp_path):
  storage = SqliteStorage(tmp_path / "h.db")
  apply_migrations(storage)
  planner = PlannerService(TaskRepository(storage), NoteRepository(storage))
  automation = AutomationService(AutomationRepository(storage))
  bus = EventBus()
  store = MockStore()
  home = HomeScreen(store)
  qtbot.addWidget(home)
  bridge = OverviewBridge(planner, automation, None, bus, home, store)
  return planner, bus, store, home, bridge


def _labels(column) -> list[str]:
  from PySide6.QtWidgets import QLabel

  return [w.text() for w in column.findChildren(QLabel)]


def test_demo_data_is_replaced(qtbot, tmp_path) -> None:
  _planner, _bus, store, home, _bridge = _setup(qtbot, tmp_path)
  assert store.quick_actions() == LIVE_QUICK_ACTIONS
  assert store.commands() == LIVE_COMMANDS
  assert all(c["id"] not in ("workspace", "error_demo") for c in store.commands())
  assert store.search("Maira") == []  # demo search results are gone
  assert store.activity == []  # demo timeline is gone
  assert not home.overview.isHidden()
  assert any("Koi task nahi" in text for text in _labels(home.tasks_column))


def test_panel_refreshes_when_chat_changes_tasks(qtbot, tmp_path) -> None:
  planner, bus, store, home, _bridge = _setup(qtbot, tmp_path)
  planner.add_task("Call mom")
  worker = threading.Thread(target=bus.publish, args=("planner.changed", {"reason": "chat"}))
  worker.start()
  worker.join()
  qtbot.waitUntil(lambda: "Call mom" in _labels(home.tasks_column), timeout=3000)
  assert home.tasks_column.header.text() == "Aaj ke tasks (1)"
  assert store.activity[0]["text"] == 'Task added: "Call mom"'


def test_quick_action_buttons_and_prefill(qtbot, tmp_path) -> None:
  from PySide6.QtWidgets import QPushButton

  _planner, _bus, _store, home, _bridge = _setup(qtbot, tmp_path)
  labels = [b.text() for b in home.findChildren(QPushButton) if b.objectName() == "QuickAction" and not b.isHidden()]
  assert {"Plan my day", "What's pending?", "Add a task", "Set a reminder"} <= set(labels)
  home.prefill("add task ")
  editor = home.command_input.editor
  assert editor.toPlainText() == "add task "  # trailing space kept
  assert editor.textCursor().position() == len("add task ")  # typing continues after it


def test_column_header_opens_screen(qtbot, tmp_path) -> None:
  _planner, _bus, _store, home, _bridge = _setup(qtbot, tmp_path)
  opened: list = []
  home.open_screen.connect(opened.append)
  home.tasks_column.header.click()
  home.reminders_column.header.click()
  home.notes_column.header.click()
  assert opened == ["tasks", "automations", "notes"]


def test_mock_mode_keeps_demo_data(qtbot) -> None:
  store = MockStore()
  home = HomeScreen(store)
  qtbot.addWidget(home)
  assert home.overview.isHidden()
  assert any(c["id"] == "workspace" for c in store.quick_actions())
