"""Mutable mock store for the UI prototype (no backend)."""

from __future__ import annotations

import itertools
from typing import Any

from PySide6.QtCore import QObject, Signal

from maira.ui.prototype.mock.data import (
  MOCK_COMMANDS,
  MOCK_ERRORS,
  MOCK_QUICK_ACTIONS,
  MOCK_SEARCH_RESULTS,
  MOCK_STREAM_REPLIES,
  clone_defaults,
)


class MockStore(QObject):
  changed = Signal(str)
  toast = Signal(str)

  def __init__(self) -> None:
    super().__init__()
    self._ids = itertools.count(1000)
    self.reset()

  def reset(self) -> None:
    data = clone_defaults()
    self.profile = data["profile"]
    self.conversation = data["conversation"]
    self.memories = data["memories"]
    self.tasks = data["tasks"]
    self.notes = data["notes"]
    self.activity = data["activity"]
    self.automations = data["automations"]
    self.settings = data["settings"]
    self.status = data["status"]
    self.selected_memory_id = self.memories[0]["id"] if self.memories else None
    self.selected_note_id = self.notes[0]["id"] if self.notes else None
    self.force_empty: set[str] = set()
    self.force_error: str | None = None
    self.stream_index = 0

  def next_id(self, prefix: str) -> str:
    return f"{prefix}{next(self._ids)}"

  def greeting_name(self) -> str:
    return str(self.profile.get("name") or "there")

  def set_profile_name(self, name: str) -> None:
    self.profile["name"] = name.strip() or "Friend"
    self.settings["general"]["name"] = self.profile["name"]
    self.changed.emit("profile")

  def set_voice_choice(self, voice: str) -> None:
    self.profile["voice"] = voice
    self.settings["voice"]["voice"] = voice
    self.changed.emit("profile")

  def complete_onboarding(self) -> None:
    self.profile["onboarded"] = True
    self.changed.emit("profile")

  def append_user_message(self, text: str) -> dict[str, Any]:
    msg = {"id": self.next_id("m"), "role": "user", "content": text}
    self.conversation.append(msg)
    self.changed.emit("conversation")
    return msg

  def next_stream_reply(self) -> str:
    reply = MOCK_STREAM_REPLIES[self.stream_index % len(MOCK_STREAM_REPLIES)]
    self.stream_index += 1
    return reply

  def append_assistant_message(self, text: str) -> dict[str, Any]:
    msg = {"id": self.next_id("m"), "role": "assistant", "content": text}
    self.conversation.append(msg)
    self.changed.emit("conversation")
    return msg

  def memories_by_section(self) -> dict[str, list[dict[str, Any]]]:
    if "memory" in self.force_empty:
      return {"Recent": [], "Projects": [], "Preferences": [], "Important": []}
    sections: dict[str, list[dict[str, Any]]] = {
      "Recent": list(self.memories[:4]),
      "Projects": [],
      "Preferences": [],
      "Important": [],
    }
    for mem in self.memories:
      cat = mem.get("category", "Important")
      if cat in sections and cat != "Recent":
        sections[cat].append(mem)
    return sections

  def get_memory(self, memory_id: str | None) -> dict[str, Any] | None:
    if not memory_id:
      return None
    for mem in self.memories:
      if mem["id"] == memory_id:
        return mem
    return None

  def add_memory(self, title: str, body: str = "") -> None:
    mem = {
      "id": self.next_id("mem"),
      "title": title,
      "body": body or title,
      "category": "Important",
      "importance": "Medium",
      "created": "Just now",
      "tags": ["New"],
    }
    self.memories.insert(0, mem)
    self.selected_memory_id = mem["id"]
    self.toast.emit("Memory saved")
    self.changed.emit("memories")

  def forget_memory(self, memory_id: str) -> None:
    self.memories = [m for m in self.memories if m["id"] != memory_id]
    self.selected_memory_id = self.memories[0]["id"] if self.memories else None
    self.toast.emit("Memory forgotten")
    self.changed.emit("memories")

  def tasks_by_section(self) -> dict[str, list[dict[str, Any]]]:
    if "tasks" in self.force_empty:
      return {"Today": [], "Upcoming": [], "Completed": []}
    result = {"Today": [], "Upcoming": [], "Completed": []}
    for task in self.tasks:
      section = "Completed" if task["done"] else task.get("section", "Today")
      if section not in result:
        section = "Today"
      if task["done"]:
        result["Completed"].append(task)
      else:
        result[section].append(task)
    return result

  def toggle_task(self, task_id: str) -> None:
    for task in self.tasks:
      if task["id"] == task_id:
        task["done"] = not task["done"]
        task["section"] = "Completed" if task["done"] else "Today"
        break
    self.changed.emit("tasks")

  def add_task(self, title: str) -> None:
    self.tasks.insert(
      0,
      {
        "id": self.next_id("t"),
        "title": title,
        "section": "Today",
        "time": "Now",
        "done": False,
        "priority": "Medium",
      },
    )
    self.toast.emit("Task created")
    self.changed.emit("tasks")

  def get_note(self, note_id: str | None) -> dict[str, Any] | None:
    if not note_id:
      return None
    for note in self.notes:
      if note["id"] == note_id:
        return note
    return None

  def add_note(self, title: str = "Untitled") -> None:
    note = {
      "id": self.next_id("n"),
      "title": title,
      "updated": "Just now",
      "body": "",
    }
    self.notes.insert(0, note)
    self.selected_note_id = note["id"]
    self.toast.emit("Note created")
    self.changed.emit("notes")

  def update_note(self, note_id: str, title: str, body: str) -> None:
    for note in self.notes:
      if note["id"] == note_id:
        note["title"] = title or "Untitled"
        note["body"] = body
        note["updated"] = "Just now"
        break
    self.changed.emit("notes")

  def toggle_automation(self, auto_id: str) -> None:
    for item in self.automations:
      if item["id"] == auto_id:
        item["enabled"] = not item["enabled"]
        break
    self.changed.emit("automations")

  def add_automation(self) -> None:
    self.automations.append(
      {
        "id": self.next_id("au"),
        "title": "New Automation",
        "schedule": "Manual",
        "enabled": False,
      }
    )
    self.toast.emit("Automation draft created")
    self.changed.emit("automations")

  def set_status_offline(self, offline: bool) -> None:
    for item in self.status:
      if item["id"] == "brain":
        item["state"] = "Offline" if offline else "Ready"
      if item["id"] == "ollama":
        item["state"] = "Offline" if offline else "Ready"
    self.changed.emit("status")

  def search(self, query: str, category: str = "Everything") -> list[dict[str, Any]]:
    q = query.strip().lower()
    results = MOCK_SEARCH_RESULTS
    if category not in ("Everything", "All", ""):
      results = [r for r in results if r["category"] == category]
    if q:
      results = [
        r
        for r in results
        if q in r["title"].lower() or q in r["subtitle"].lower() or q in r["category"].lower()
      ]
    return results

  def commands(self) -> list[dict[str, Any]]:
    return list(MOCK_COMMANDS)

  def quick_actions(self) -> list[dict[str, Any]]:
    return list(MOCK_QUICK_ACTIONS)

  def error_copy(self, key: str) -> dict[str, str]:
    return dict(MOCK_ERRORS.get(key, MOCK_ERRORS["general"]))
