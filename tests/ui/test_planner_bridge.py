"""Tasks screen refreshes safely when chat changes tasks on a worker thread."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from maira.core.bus.event_bus import EventBus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import NoteRepository, TaskRepository
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.planner.service import PlannerService
from maira.ui.prototype.integration.planner_bridge import ProtoPlannerBridge
from maira.ui.prototype.screens.notes import NotesScreen
from maira.ui.prototype.screens.tasks import TasksScreen


def test_chat_change_refreshes_tasks_on_ui_thread(qtbot, tmp_path) -> None:
  storage = SqliteStorage(tmp_path / "ui.db")
  apply_migrations(storage)
  planner = PlannerService(TaskRepository(storage), NoteRepository(storage))
  bus = EventBus()
  tasks, notes = TasksScreen(), NotesScreen()
  qtbot.addWidget(tasks)
  qtbot.addWidget(notes)
  ProtoPlannerBridge(planner, tasks, notes, bus)
  assert tasks._tasks == []  # noqa: SLF001

  tomorrow = datetime.now(LOCAL_TZ) + timedelta(days=1)
  planner.add_task("Pay bill", due_at=tomorrow.replace(hour=23, minute=59))
  worker = threading.Thread(target=bus.publish, args=("planner.changed", {"reason": "chat"}))
  worker.start()
  worker.join()

  qtbot.waitUntil(lambda: len(tasks._tasks) == 1, timeout=3000)  # noqa: SLF001
  row = tasks._tasks[0]  # noqa: SLF001
  assert row["section"] == "Upcoming"
  assert row["time"] == "Kal"
