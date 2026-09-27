"""The bundled sample_skills/pdf-page-splitter: install, run, and check its output.

This exercises the real skill pipeline (install -> discover -> safety scan -> approve
scripts -> extract a ```run block -> plan_run -> execute) end to end against the
script Ultron actually ships, not a synthetic fixture.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from maira.modules.skills.runner import execute, extract_command, plan_run
from maira.modules.skills.store import SkillStore
from maira.shared.utils.paths import project_root

SAMPLE_SKILL = project_root() / "sample_skills" / "pdf-page-splitter"


@pytest.fixture
def store(tmp_path: Path) -> SkillStore:
  store = SkillStore(tmp_path / "skills")
  store.install(str(SAMPLE_SKILL))
  skill = store.get("local-pdf-page-splitter/pdf-page-splitter")
  store.set_scripts_allowed(skill.id, True)
  return store


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
  """A 6-page PDF, each page labeled with its number, for checking extracted content."""
  path = tmp_path / "report.pdf"
  doc = pymupdf.open()
  for number in range(1, 7):
    page = doc.new_page()
    page.insert_text((72, 72), f"page {number}")
  doc.save(path)
  doc.close()
  return path


def _run(store: SkillStore, args: str) -> tuple:
  skill = store.get("local-pdf-page-splitter/pdf-page-splitter")
  reply = f"Doing it.\n\n```run\npython scripts/split_pdf.py {args}\n```"
  command = extract_command(reply, skill.scripts)
  plan = plan_run(command, store.skill_dir(skill), skill.scripts)
  return execute(plan, cwd=store.work_dir, timeout=30), plan


def _texts(path: Path) -> list[str]:
  doc = pymupdf.open(path)
  return [page.get_text().strip() for page in doc]


def test_skill_installs_with_no_warnings(store) -> None:
  skill = store.get("local-pdf-page-splitter/pdf-page-splitter")
  assert skill.scripts == ["scripts/split_pdf.py"]
  assert skill.warnings == []  # a bundled skill should not trip its own safety scan
  assert "split" in skill.description.lower()


def test_extracts_a_page_range_in_order(store, sample_pdf, tmp_path) -> None:
  out = tmp_path / "range.pdf"
  result, _plan = _run(store, f'"{sample_pdf}" "{out}" --pages 2-4')
  assert result.ok, result.output
  assert "has 6 page(s)" in result.output and "Wrote 3 page(s) [2,3,4]" in result.output
  assert _texts(out) == ["page 2", "page 3", "page 4"]


def test_extracts_a_mixed_list_preserving_order_and_repeats(store, sample_pdf, tmp_path) -> None:
  out = tmp_path / "mixed.pdf"
  result, _plan = _run(store, f'"{sample_pdf}" "{out}" --pages 5,1,3-4,1')
  assert result.ok, result.output
  assert _texts(out) == ["page 5", "page 1", "page 3", "page 4", "page 1"]


def test_splits_each_page_into_its_own_file(store, sample_pdf, tmp_path) -> None:
  out_dir = tmp_path / "pages"
  result, _plan = _run(store, f'"{sample_pdf}" "{out_dir}" --each')
  assert result.ok, result.output
  assert "Wrote 6 single-page file(s)" in result.output
  names = sorted(p.name for p in out_dir.iterdir())
  assert names == [f"page_{n}.pdf" for n in range(1, 7)]  # 6 pages: single-digit, no padding
  assert _texts(out_dir / "page_3.pdf") == ["page 3"]


def test_bare_output_name_lands_next_to_the_input(store, sample_pdf) -> None:
  result, _plan = _run(store, f'"{sample_pdf}" only_page_1.pdf --pages 1')
  assert result.ok, result.output
  expected = sample_pdf.parent / "only_page_1.pdf"
  assert expected.exists() and _texts(expected) == ["page 1"]


def test_out_of_range_page_is_a_clean_error_not_a_crash(store, sample_pdf, tmp_path) -> None:
  out = tmp_path / "bad.pdf"
  result, _plan = _run(store, f'"{sample_pdf}" "{out}" --pages 42')
  assert not result.ok and result.code == 1
  assert "Page 42 is out of range (this PDF has 6 page(s))" in result.output
  assert not out.exists()


def test_missing_input_file_is_a_clean_error(store, tmp_path) -> None:
  out = tmp_path / "out.pdf"
  missing = tmp_path / "does_not_exist.pdf"
  result, _plan = _run(store, f'"{missing}" "{out}" --pages 1')
  assert not result.ok and "Input file not found" in result.output


def test_only_the_declared_script_can_run(store) -> None:
  skill = store.get("local-pdf-page-splitter/pdf-page-splitter")
  with pytest.raises(Exception):
    plan_run("python -c 'print(1)'", store.skill_dir(skill), skill.scripts)
