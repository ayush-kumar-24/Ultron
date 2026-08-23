"""Bridge: prototype Memory screen ↔ MemoryService."""

from __future__ import annotations

from PySide6.QtCore import QObject

from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.memory import Memory
from maira.ui.prototype.screens.memory import MemoryScreen

_UI_TO_CATEGORY = {
  "Projects": MemoryCategory.PROJECT,
  "Preferences": MemoryCategory.PREFERENCE,
  "Important": MemoryCategory.IDEA,
  "Project": MemoryCategory.PROJECT,
  "Preference": MemoryCategory.PREFERENCE,
}

_CATEGORY_TO_UI = {
  MemoryCategory.PROJECT: "Projects",
  MemoryCategory.PREFERENCE: "Preferences",
  MemoryCategory.IDEA: "Important",
  MemoryCategory.NOTE: "Important",
  MemoryCategory.TASK: "Important",
  MemoryCategory.CONVERSATION: "Important",
}


def _entry_to_row(entry) -> dict:
  cat = _CATEGORY_TO_UI.get(entry.category, "Important")
  return {
    "id": entry.id,
    "title": entry.title,
    "body": entry.body,
    "category": cat,
    "importance": "High" if entry.category in (MemoryCategory.PREFERENCE, MemoryCategory.PROJECT) else "Medium",
    "created": entry.created_at.strftime("%b %d"),
    "tags": [cat],
  }


class ProtoMemoryBridge(QObject):
  def __init__(self, memory: Memory, view: MemoryScreen) -> None:
    super().__init__()
    self._memory = memory
    self._view = view
    view.set_live_mode(True)
    view.add_requested.connect(self.add_memory)
    view.forget_requested.connect(self.forget_memory)
    view.select_requested.connect(self.select_memory)
    view.search_changed.connect(self.apply_search)
    self._search = ""
    self.refresh()

  def refresh(self) -> None:
    if self._search.strip():
      entries = self._memory.search(self._search)
    else:
      entries = self._memory.list_memories()
    rows = [_entry_to_row(e) for e in entries]
    selected = rows[0]["id"] if rows else None
    self._view.set_memories(rows, selected)

  def add_memory(self) -> None:
    entry = self._memory.store(
      category=MemoryCategory.IDEA,
      title="New memory",
      body="Something worth remembering.",
    )
    self.refresh()
    self._view.select_memory(entry.id)

  def forget_memory(self, memory_id: str) -> None:
    self._memory.delete(memory_id)
    self.refresh()

  def select_memory(self, memory_id: str) -> None:
    entry = self._memory.get(memory_id)
    if entry:
      self._view.show_memory(_entry_to_row(entry))

  def apply_search(self, query: str) -> None:
    self._search = query
    self.refresh()
