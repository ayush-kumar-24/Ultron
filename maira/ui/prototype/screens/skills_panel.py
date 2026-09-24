"""Settings → Skills: add any GitHub repo, turn skills on/off, allow scripts."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QMessageBox,
  QPushButton,
  QTreeWidget,
  QTreeWidgetItem,
  QVBoxLayout,
  QWidget,
)

from maira.modules.skills.models import KIND_COMMAND, KIND_REPO, Skill, SkillPack
from maira.modules.skills.service import SkillService
from maira.ui.prototype.theme import tokens as t

_ROLE = Qt.ItemDataRole.UserRole
_KIND_LABEL = {KIND_COMMAND: "command", KIND_REPO: "repo knowledge"}


def _muted(text: str = "") -> QLabel:
  label = QLabel(text)
  label.setObjectName("Muted")
  label.setWordWrap(True)
  return label


def _card() -> tuple[QFrame, QVBoxLayout]:
  card = QFrame()
  card.setObjectName("Card")
  layout = QVBoxLayout(card)
  layout.setContentsMargins(20, 16, 20, 16)
  layout.setSpacing(10)
  return card, layout


class SkillsPanel(QWidget):
  _install_done = Signal(str)  # from the install thread
  _store_changed = Signal()  # from any thread (chat commands change skills too)

  def __init__(self, service: SkillService, parent=None) -> None:
    super().__init__(parent)
    self.service = service
    self.store = service.store
    self._busy = False
    self._refresh_queued = False
    self._install_done.connect(self._on_install_done)
    # Queued: a change made from inside a tree signal must not rebuild the tree under Qt's feet.
    self._store_changed.connect(self._queue_refresh, Qt.ConnectionType.QueuedConnection)

    def notify_change() -> None:
      try:
        self._store_changed.emit()
      except RuntimeError:
        pass  # panel already closed

    self.store.on_change(notify_change)

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(12)

    add_card, add = _card()
    heading = QLabel("Add skills from any GitHub repo")
    heading.setObjectName("Secondary")
    add.addWidget(heading)
    row = QHBoxLayout()
    self.source = QLineEdit()
    self.source.setPlaceholderText("owner/repo, a github.com link (a folder link works too), or a folder on this PC")
    self.source.returnPressed.connect(self.install)
    self.install_btn = QPushButton("Install")
    self.install_btn.setObjectName("GhostButton")
    self.install_btn.clicked.connect(self.install)
    row.addWidget(self.source, stretch=1)
    row.addWidget(self.install_btn)
    add.addLayout(row)
    self.install_state = _muted(
      "Examples: anthropics/skills · obra/superpowers · any repo (its README becomes the skill). "
      "You can also say it in chat: “install skill owner/repo”."
    )
    add.addWidget(self.install_state)
    root.addWidget(add_card)

    list_card, listing = _card()
    top = QHBoxLayout()
    self.count = QLabel("")
    self.count.setObjectName("Secondary")
    top.addWidget(self.count, stretch=1)
    self.search = QLineEdit()
    self.search.setPlaceholderText("Search skills")
    self.search.setMaximumWidth(260)
    self.search.textChanged.connect(self._filter)
    top.addWidget(self.search)
    listing.addLayout(top)

    self.tree = QTreeWidget()
    self.tree.setHeaderLabels(["Skill", "Scripts", "What it does"])
    self.tree.setColumnWidth(0, 230)
    self.tree.setColumnWidth(1, 90)
    self.tree.setMinimumHeight(300)
    self.tree.setRootIsDecorated(True)
    self.tree.setUniformRowHeights(True)
    self.tree.setStyleSheet(
      f"QTreeWidget {{ background: {t.BG_INPUT}; border: 1px solid {t.BORDER}; border-radius: 8px;"
      f" color: {t.TEXT_PRIMARY}; }} QHeaderView::section {{ background: {t.BG_ELEVATED};"
      f" color: {t.TEXT_SECONDARY}; border: none; padding: 6px; }}"
      f" QTreeWidget::item {{ padding: 3px; }} QTreeWidget::item:selected {{ background: {t.BG_HOVER}; }}"
    )
    self.tree.itemChanged.connect(self._item_toggled)
    self.tree.currentItemChanged.connect(lambda *_: self._show_details())
    listing.addWidget(self.tree)
    listing.addWidget(_muted("Tick a skill to use it. Scripts never run unless you allow them here, "
                             "and Ultron still asks before each run."))
    root.addWidget(list_card)

    details_card, details = _card()
    self.details_title = QLabel("Select a skill or repo")
    self.details_title.setObjectName("Secondary")
    self.details_body = _muted("")
    self.details_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    details.addWidget(self.details_title)
    details.addWidget(self.details_body)
    buttons = QHBoxLayout()
    self.scripts_btn = QPushButton("Allow scripts")
    self.update_btn = QPushButton("Update")
    self.remove_btn = QPushButton("Remove repo")
    self.folder_btn = QPushButton("Open folder")
    for button, handler in ((self.scripts_btn, self._toggle_scripts), (self.update_btn, self._update),
                            (self.remove_btn, self._remove), (self.folder_btn, self._open_folder)):
      button.setObjectName("GhostButton")
      button.clicked.connect(handler)
      buttons.addWidget(button)
    buttons.addStretch(1)
    details.addLayout(buttons)
    root.addWidget(details_card)

    self.refresh()

  def _queue_refresh(self) -> None:
    if self._refresh_queued:
      return
    self._refresh_queued = True

    def run() -> None:
      self._refresh_queued = False
      self.refresh()

    QTimer.singleShot(0, self, run)

  # --- list --------------------------------------------------------------------------------

  def refresh(self) -> None:
    current = self._selected_key()
    expanded = {self.tree.topLevelItem(i).data(0, _ROLE)[1] for i in range(self.tree.topLevelItemCount())
                if self.tree.topLevelItem(i).isExpanded()}
    self.tree.blockSignals(True)
    self.tree.clear()
    packs = self.store.packs()
    total = 0
    for pack in packs:
      top = QTreeWidgetItem([f"{pack.label}  ({len(pack.skills)})", "", pack.web_url])
      top.setData(0, _ROLE, ("pack", pack.id))
      top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable)
      enabled = sum(1 for s in pack.skills if s.enabled)
      top.setCheckState(0, Qt.CheckState.Checked if enabled == len(pack.skills) else
                        Qt.CheckState.Unchecked if enabled == 0 else Qt.CheckState.PartiallyChecked)
      for skill in pack.skills:
        total += 1
        kind = _KIND_LABEL.get(skill.kind)
        child = QTreeWidgetItem([
          f"/{skill.name}" + (f"  · {kind}" if kind else ""),
          self._scripts_text(skill),
          skill.description,
        ])
        child.setData(0, _ROLE, ("skill", skill.id))
        child.setToolTip(2, skill.description)
        child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        child.setCheckState(0, Qt.CheckState.Checked if skill.enabled else Qt.CheckState.Unchecked)
        if skill.scripts:
          color = t.STATUS_READY if skill.scripts_allowed else t.TEXT_MUTED
          child.setForeground(1, _brush(color))
        top.addChild(child)
      self.tree.addTopLevelItem(top)
      top.setExpanded(pack.id in expanded or len(packs) == 1)
    self.tree.blockSignals(False)
    self.count.setText(f"{total} skill{'s' if total != 1 else ''} from {len(packs)} repo{'s' if len(packs) != 1 else ''}"
                       if packs else "No skills yet")
    self._filter(self.search.text())
    self._select_key(current)
    self._show_details()

  @staticmethod
  def _scripts_text(skill: Skill) -> str:
    if not skill.scripts:
      return "—"
    return "allowed" if skill.scripts_allowed else f"{len(skill.scripts)} · off"

  def _filter(self, text: str) -> None:
    needle = text.strip().lower()
    for i in range(self.tree.topLevelItemCount()):
      top = self.tree.topLevelItem(i)
      shown = 0
      for j in range(top.childCount()):
        child = top.child(j)
        hit = not needle or needle in child.text(0).lower() or needle in child.text(2).lower()
        child.setHidden(not hit)
        shown += hit
      top.setHidden(bool(needle) and shown == 0 and needle not in top.text(0).lower())
      if needle and shown:
        top.setExpanded(True)

  def _item_toggled(self, item: QTreeWidgetItem, column: int) -> None:
    if column != 0:
      return
    kind, key = item.data(0, _ROLE)
    on = item.checkState(0) != Qt.CheckState.Unchecked
    if kind == "skill":
      skill = self.store.get(key)
      if skill is not None and skill.enabled != on:
        self.store.set_enabled(key, on)
    else:
      self.store.set_pack_enabled(key, on)  # one save for the whole repo

  # --- selection & details ---------------------------------------------------------------------

  def _selected_key(self) -> tuple[str, str] | None:
    item = self.tree.currentItem()
    return tuple(item.data(0, _ROLE)) if item is not None else None

  def _select_key(self, key) -> None:
    if key is None:
      return
    for i in range(self.tree.topLevelItemCount()):
      top = self.tree.topLevelItem(i)
      for item in [top, *[top.child(j) for j in range(top.childCount())]]:
        if tuple(item.data(0, _ROLE)) == tuple(key):
          self.tree.setCurrentItem(item)
          return

  def _selection(self) -> tuple[SkillPack | None, Skill | None]:
    key = self._selected_key()
    if key is None:
      return None, None
    if key[0] == "skill":
      skill = self.store.get(key[1])
      return (self.store.pack(skill.pack) if skill else None), skill
    return self.store.pack(key[1]), None

  def _show_details(self) -> None:
    pack, skill = self._selection()
    self.scripts_btn.setVisible(bool(skill and skill.scripts))
    for button in (self.update_btn, self.remove_btn, self.folder_btn):
      button.setVisible(pack is not None)
    if pack is None:
      self.details_title.setText("Select a skill or repo")
      self.details_body.setText("")
      return
    if skill is None:
      when = (pack.updated_at or pack.installed_at).replace("T", " ")[:16]
      with_scripts = sum(1 for s in pack.skills if s.scripts)
      self.details_title.setText(pack.label)
      self.details_body.setText(
        f"{len(pack.skills)} skills · {with_scripts} with scripts · updated {when} UTC"
        f"{f' · commit {pack.commit[:8]}' if pack.commit else ''}\n{pack.web_url}"
      )
      return
    lines = [skill.description or "(no description)", "", f"Use it: /{skill.name} <request>"]
    if skill.kind == KIND_REPO:
      lines.append("This repo has no SKILL.md, so Ultron learns from its README and agent instruction files.")
    if skill.license:
      lines.append(f"License: {skill.license}")
    if skill.scripts:
      lines.append(f"Scripts ({len(skill.scripts)}): {', '.join(skill.scripts[:6])}{' …' if len(skill.scripts) > 6 else ''}")
      lines.append("Safety check: " + ("; ".join(skill.warnings) if skill.warnings else "nothing unusual found"))
      self.scripts_btn.setText("Block scripts" if skill.scripts_allowed else "Allow scripts…")
    self.details_title.setText(f"/{skill.name} — {pack.label}")
    self.details_body.setText("\n".join(lines))

  def _toggle_scripts(self) -> None:
    _pack, skill = self._selection()
    if skill is None:
      return
    if skill.scripts_allowed:
      self.store.set_scripts_allowed(skill.id, False)
      return
    found = "\n".join(f"• {w}" for w in skill.warnings) or "• nothing unusual found"
    answer = QMessageBox.warning(
      self,
      "Allow scripts?",
      f"Allow /{skill.name} to run its {len(skill.scripts)} script(s) on this PC?\n\n"
      "Scripts run with your permissions. Ultron shows each command and asks before running it, "
      f"and stops it after the time limit.\n\nSafety check:\n{found}\n\n"
      "Only allow skills from people you trust.",
      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
      QMessageBox.StandardButton.No,
    )
    if answer == QMessageBox.StandardButton.Yes:
      self.store.set_scripts_allowed(skill.id, True)

  # --- install / update / remove -------------------------------------------------------------------

  def install(self, text: str | None = None) -> None:
    source = (text if isinstance(text, str) else self.source.text()).strip()
    if not source or self._busy:
      return
    reply = self.service.start_install(source, notify=self._install_done.emit)
    self.install_state.setText(reply.text)
    if reply.text.startswith(("Installing", "Updating")):
      self._set_busy(True)

  def _set_busy(self, busy: bool) -> None:
    self._busy = busy
    self.install_btn.setEnabled(not busy)
    self.update_btn.setEnabled(not busy)
    self.install_btn.setText("Installing…" if busy else "Install")

  def _on_install_done(self, message: str) -> None:
    self._set_busy(False)
    self.install_state.setText(message)
    if message.startswith(("Installed", "Updated")):
      self.source.clear()
    self._queue_refresh()

  def _update(self) -> None:
    pack, _skill = self._selection()
    if pack is not None:
      self.install(pack.web_url)

  def _remove(self) -> None:
    pack, _skill = self._selection()
    if pack is None:
      return
    answer = QMessageBox.question(self, "Remove skills", f"Remove {pack.label} and its {len(pack.skills)} skill(s)?")
    if answer == QMessageBox.StandardButton.Yes:
      self.install_state.setText(self.service.handle(f"remove skills {pack.id}").text)

  def _open_folder(self) -> None:
    pack, skill = self._selection()
    if pack is None:
      return
    folder = self.store.skill_dir(skill) if skill else self.store.pack_dir(pack.id)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _brush(color: str):
  from PySide6.QtGui import QBrush, QColor  # noqa: PLC0415

  return QBrush(QColor(color))
