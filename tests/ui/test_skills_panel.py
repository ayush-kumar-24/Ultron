"""Settings → Skills: install from a folder, toggle, allow scripts, search, remove."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from maira.modules.skills.service import SkillService
from maira.modules.skills.store import SkillStore
from maira.ui.prototype.screens.skills_panel import SkillsPanel
from tests.unit.test_skills import PDF_SKILL, _write


@pytest.fixture
def repo(tmp_path):
  folder = tmp_path / "myskills"
  _write(folder / "pdf/SKILL.md", PDF_SKILL)
  _write(folder / "pdf/scripts/count_pages.py", "import subprocess\nprint(1)\n")
  _write(folder / "notes/SKILL.md", "---\nname: notes\ndescription: Tidy meeting notes\n---\nBullets.\n")
  return folder


@pytest.fixture
def panel(qtbot, tmp_path):
  service = SkillService(SkillStore(tmp_path / "skills"))
  widget = SkillsPanel(service)
  qtbot.addWidget(widget)
  return widget


def _children(panel: SkillsPanel) -> dict[str, object]:
  top = panel.tree.topLevelItem(0)
  return {top.child(i).text(0).split()[0]: top.child(i) for i in range(top.childCount())}


def test_install_toggle_scripts_search_remove(qtbot, panel, repo, monkeypatch) -> None:
  assert panel.count.text() == "No skills yet"
  panel.source.setText(str(repo))
  panel.install_btn.click()
  assert panel.install_btn.text() == "Installing…"
  qtbot.waitUntil(lambda: panel.tree.topLevelItemCount() == 1 and not panel._busy, timeout=10000)  # noqa: SLF001
  assert panel.install_state.text().startswith("Installed myskills: 2 skills")
  assert panel.count.text() == "2 skills from 1 repo"
  items = _children(panel)
  assert set(items) == {"/pdf", "/notes"}
  assert items["/pdf"].text(1) == "1 · off" and items["/notes"].text(1) == "—"

  store = panel.store
  _children(panel)["/notes"].setCheckState(0, Qt.CheckState.Unchecked)
  qtbot.waitUntil(lambda: not store.get("local-myskills/notes").enabled)
  qtbot.waitUntil(lambda: panel.tree.topLevelItem(0).checkState(0) == Qt.CheckState.PartiallyChecked)

  panel.tree.setCurrentItem(_children(panel)["/pdf"])
  assert "runs other programs" in panel.details_body.text()
  assert panel.scripts_btn.isVisibleTo(panel) and panel.scripts_btn.text() == "Allow scripts…"
  monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.No)
  panel.scripts_btn.click()
  assert not store.get("local-myskills/pdf").scripts_allowed
  monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
  panel.scripts_btn.click()
  assert store.get("local-myskills/pdf").scripts_allowed
  qtbot.waitUntil(lambda: _children(panel)["/pdf"].text(1) == "allowed")
  assert panel.scripts_btn.text() == "Block scripts"  # selection kept across refresh

  panel.search.setText("meeting")
  assert _children(panel)["/pdf"].isHidden() and not _children(panel)["/notes"].isHidden()
  panel.search.clear()

  panel.tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
  qtbot.waitUntil(lambda: not any(s.enabled for s in store.skills()))

  panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
  monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
  panel.remove_btn.click()
  qtbot.waitUntil(lambda: panel.tree.topLevelItemCount() == 0)
  assert panel.install_state.text().startswith("Removed myskills")


def test_bad_source_and_chat_changes_refresh(qtbot, panel, repo) -> None:
  panel.install("https://gitlab.com/a/b")
  assert "Only GitHub" in panel.install_state.text() and not panel._busy  # noqa: SLF001
  panel.store.install(str(repo))  # e.g. installed from chat
  qtbot.waitUntil(lambda: panel.tree.topLevelItemCount() == 1)
