"""Memory controller — browse, filter, and edit memories."""

from PySide6.QtCore import QObject, Slot

from maira.core.domain.value_objects import MemoryCategory
from maira.core.interfaces.memory import Memory
from maira.ui.views.memory import MemoryView


class MemoryController(QObject):
  def __init__(self, memory: Memory, view: MemoryView) -> None:
    super().__init__()
    self._memory = memory
    self._view = view
    self._selected_id: str | None = None
    self._category_filter: str = ""
    self._search: str = ""

    view.add_requested.connect(self.add_memory)
    view.save_requested.connect(self.save_memory)
    view.delete_requested.connect(self.delete_memory)
    view.memory_selected.connect(self.select_memory)
    view.filter_changed.connect(self.apply_filter)

    self.refresh()

  def refresh(self) -> None:
    category = MemoryCategory(self._category_filter) if self._category_filter else None
    if self._search.strip():
      memories = self._memory.search(self._search, category=category)
    else:
      memories = self._memory.list_memories(category)

    ids = {item.id for item in memories}
    if self._selected_id not in ids:
      self._selected_id = memories[0].id if memories else None

    selected = self._selected_id
    self._view.set_memories(memories, selected)
    self._view.show_memory(self._memory.get(selected) if selected else None)

  @Slot()
  def add_memory(self) -> None:
    entry = self._memory.store(
      category=MemoryCategory.IDEA,
      title="New memory",
      body="",
    )
    self._selected_id = entry.id
    self.refresh()

  @Slot(str, str, str, str)
  def save_memory(self, memory_id: str, category: str, title: str, body: str) -> None:
    self._memory.update(
      memory_id,
      category=MemoryCategory(category),
      title=title,
      body=body,
    )
    self._selected_id = memory_id
    self.refresh()

  @Slot(str)
  def delete_memory(self, memory_id: str) -> None:
    self._memory.delete(memory_id)
    self._selected_id = None
    self.refresh()

  @Slot(str)
  def select_memory(self, memory_id: str) -> None:
    self._selected_id = memory_id
    self._view.show_memory(self._memory.get(memory_id))

  @Slot(str, str)
  def apply_filter(self, category: str, search: str) -> None:
    self._category_filter = category
    self._search = search
    self.refresh()
