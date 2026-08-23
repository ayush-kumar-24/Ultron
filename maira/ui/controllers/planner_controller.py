"""Planner controller — todos and notes."""

from PySide6.QtCore import QObject, Slot

from maira.core.domain.value_objects import MemoryCategory, Priority, TaskStatus
from maira.core.interfaces.memory import Memory
from maira.core.interfaces.planner import Planner
from maira.ui.views.planner import PlannerView


class PlannerController(QObject):
  def __init__(
    self,
    planner: Planner,
    view: PlannerView,
    memory: Memory | None = None,
  ) -> None:
    super().__init__()
    self._planner = planner
    self._memory = memory
    self._view = view
    self._selected_note_id: str | None = None

    view.add_task_requested.connect(self.add_task)
    view.toggle_task_requested.connect(self.toggle_task)
    view.delete_task_requested.connect(self.delete_task)
    view.change_priority_requested.connect(self.change_priority)
    view.add_note_requested.connect(self.add_note)
    view.save_note_requested.connect(self.save_note)
    view.delete_note_requested.connect(self.delete_note)
    view.note_selected.connect(self.select_note)
    view.save_note_to_memory_requested.connect(self.save_note_to_memory)

    self.refresh()

  def refresh(self) -> None:
    self._view.set_tasks(self._planner.list_tasks())
    notes = self._planner.list_notes()
    selected = self._selected_note_id
    if selected and self._planner.get_note(selected) is None:
      selected = None
      self._selected_note_id = None
    self._view.set_notes(notes, selected)
    if selected:
      self._view.show_note(self._planner.get_note(selected))
    elif notes:
      self._selected_note_id = notes[0].id
      self._view.show_note(notes[0])
    else:
      self._view.show_note(None)

  @Slot(str, str)
  def add_task(self, title: str, priority: str) -> None:
    self._planner.add_task(title, priority=Priority(priority))
    self.refresh()

  @Slot(str, bool)
  def toggle_task(self, task_id: str, done: bool) -> None:
    status = TaskStatus.DONE if done else TaskStatus.OPEN
    self._planner.set_task_status(task_id, status)
    self.refresh()

  @Slot(str)
  def delete_task(self, task_id: str) -> None:
    self._planner.delete_task(task_id)
    self.refresh()

  @Slot(str, str)
  def change_priority(self, task_id: str, priority: str) -> None:
    self._planner.set_task_priority(task_id, Priority(priority))
    self.refresh()

  @Slot()
  def add_note(self) -> None:
    note = self._planner.add_note("Untitled", "")
    self._selected_note_id = note.id
    self.refresh()

  @Slot(str, str, str)
  def save_note(self, note_id: str, title: str, body: str) -> None:
    self._planner.update_note(note_id, title=title, body=body)
    self._selected_note_id = note_id
    self.refresh()

  @Slot(str)
  def delete_note(self, note_id: str) -> None:
    self._planner.delete_note(note_id)
    self._selected_note_id = None
    self.refresh()

  @Slot(str)
  def select_note(self, note_id: str) -> None:
    self._selected_note_id = note_id
    self._view.show_note(self._planner.get_note(note_id))

  @Slot(str, str)
  def save_note_to_memory(self, title: str, body: str) -> None:
    if self._memory is None:
      return
    self._memory.store(
      category=MemoryCategory.NOTE,
      title=title or "Untitled note",
      body=body,
    )
