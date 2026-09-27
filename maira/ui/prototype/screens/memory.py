"""Memory screen — mock or live MemoryService."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QPushButton,
  QScrollArea,
  QVBoxLayout,
  QWidget,
)

from maira.ui.prototype.components.primitives import EmptyState, PageHeader, SectionHeader
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class MemoryCard(QFrame):
  selected = Signal(str)

  def __init__(self, memory: dict, active: bool = False, parent=None) -> None:
    super().__init__(parent)
    self.memory_id = memory["id"]
    self.setObjectName("ElevatedCard" if active else "Card")
    self.setCursor(Qt.CursorShape.PointingHandCursor)
    layout = QVBoxLayout(self)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)
    title = QLabel(memory["title"])
    title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 500;")
    title.setWordWrap(True)
    meta = QLabel(f"{memory.get('created', '')} · {memory.get('category', '')}")
    meta.setObjectName("Muted")
    layout.addWidget(title)
    layout.addWidget(meta)

  def mousePressEvent(self, event) -> None:  # noqa: N802
    if event.button() == Qt.MouseButton.LeftButton:
      self.selected.emit(self.memory_id)
    super().mousePressEvent(event)


class MemoryScreen(QWidget):
  add_requested = Signal()
  forget_requested = Signal(str)
  select_requested = Signal(str)
  search_changed = Signal(str)

  def __init__(self, store: MockStore | None = None, parent=None) -> None:
    super().__init__(parent)
    self.store = store or MockStore()
    self._live = False
    self._memories: list[dict] = []
    self._selected_id: str | None = None

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(16)

    top = QHBoxLayout()
    top.addWidget(PageHeader("Memory", "What Ultron remembers about you"))
    top.addStretch(1)
    self.add_btn = QPushButton("+ Add Memory")
    self.add_btn.setObjectName("GhostButton")
    self.add_btn.clicked.connect(self._add)
    top.addWidget(self.add_btn)
    root.addLayout(top)

    self.search = QLineEdit()
    self.search.setPlaceholderText("Search memories...")
    self.search.textChanged.connect(self._on_search)
    root.addWidget(self.search)

    body = QHBoxLayout()
    body.setSpacing(16)

    self.list_host = QWidget()
    self.list_layout = QVBoxLayout(self.list_host)
    self.list_layout.setContentsMargins(0, 0, 0, 0)
    self.list_layout.setSpacing(8)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(self.list_host)
    scroll.setMinimumWidth(280)
    scroll.setMaximumWidth(360)
    body.addWidget(scroll)

    self.detail = QFrame()
    self.detail.setObjectName("Card")
    self.detail_layout = QVBoxLayout(self.detail)
    self.detail_layout.setContentsMargins(24, 24, 24, 24)
    self.detail_layout.setSpacing(12)
    body.addWidget(self.detail, stretch=1)
    root.addLayout(body, stretch=1)

    self.empty = EmptyState(
      "Nothing here yet.",
      "As you use Ultron, important information will appear here.",
    )
    root.addWidget(self.empty)
    self.empty.hide()

    if not self._live:
      self.store.changed.connect(lambda k: k == "memories" and self.reload_from_store())
      self.reload_from_store()

  def set_live_mode(self, enabled: bool) -> None:
    self._live = enabled

  def set_memories(self, memories: list[dict], selected_id: str | None) -> None:
    self._memories = memories
    self._selected_id = selected_id
    self._render_list()
    mem = next((m for m in memories if m["id"] == selected_id), None)
    if mem:
      self.show_memory(mem)

  def select_memory(self, memory_id: str) -> None:
    self._selected_id = memory_id
    self._render_list()
    if self._live:
      self.select_requested.emit(memory_id)
    else:
      mem = next((m for m in self._memories if m["id"] == memory_id), None)
      if mem:
        self.show_memory(mem)

  def show_memory(self, mem: dict) -> None:
    while self.detail_layout.count():
      item = self.detail_layout.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    title = QLabel(mem["title"])
    title.setObjectName("PageTitle")
    title.setWordWrap(True)
    self.detail_layout.addWidget(title)
    meta = QLabel(
      f"Created: {mem.get('created', '—')}\n"
      f"Category: {mem.get('category', '—')}\n"
      f"Importance: {mem.get('importance', '—')}"
    )
    meta.setObjectName("Secondary")
    self.detail_layout.addWidget(meta)
    remember = QLabel("Ultron remembers:")
    remember.setObjectName("SectionLabel")
    self.detail_layout.addWidget(remember)
    body = QLabel(mem.get("body", ""))
    body.setWordWrap(True)
    body.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 14px;")
    self.detail_layout.addWidget(body)
    actions = QHBoxLayout()
    forget = QPushButton("Forget")
    forget.setObjectName("GhostButton")
    forget.clicked.connect(lambda: self._forget(mem["id"]))
    actions.addWidget(forget)
    actions.addStretch(1)
    self.detail_layout.addLayout(actions)
    self.detail_layout.addStretch(1)
    self.detail.show()

  def reload_from_store(self) -> None:
    self.set_memories(list(self.store.memories), self.store.selected_memory_id)

  def _render_list(self) -> None:
    while self.list_layout.count():
      item = self.list_layout.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    query = self.search.text().strip().lower()
    items = self._memories
    if query:
      items = [m for m in items if query in m["title"].lower() or query in m.get("body", "").lower()]

    sections: dict[str, list[dict]] = {"Recent": [], "Projects": [], "Preferences": [], "Important": []}
    sections["Recent"] = items[:4]
    for mem in items:
      cat = mem.get("category", "Important")
      if cat in sections and cat != "Recent":
        sections[cat].append(mem)

    any_items = False
    for section, rows in sections.items():
      if section != "Recent":
        rows = [m for m in rows if m.get("category") == section]
      if not rows:
        continue
      any_items = True
      self.list_layout.addWidget(SectionHeader(section))
      for mem in rows:
        card = MemoryCard(mem, active=mem["id"] == self._selected_id)
        card.selected.connect(self.select_memory)
        self.list_layout.addWidget(card)
    self.list_layout.addStretch(1)
    self.empty.setVisible(not any_items)
    self.detail.setVisible(any_items)

  def _add(self) -> None:
    if self._live:
      self.add_requested.emit()
    else:
      self.store.add_memory("New memory", "Something worth remembering.")

  def _forget(self, memory_id: str) -> None:
    if self._live:
      self.forget_requested.emit(memory_id)
    else:
      self.store.forget_memory(memory_id)

  def _on_search(self, text: str) -> None:
    if self._live:
      self.search_changed.emit(text)
    else:
      self._render_list()
