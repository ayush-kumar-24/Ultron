"""Skills from any repo: source parsing, download, discovery, store, matching, scripts, chat."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from maira.modules.skills.discover import discover, first_paragraph, split_frontmatter
from maira.modules.skills.fetch import FetchError, fetch, safe_extract_zip
from maira.modules.skills.matcher import SkillMatch, SkillMatcher, UnknownSkill
from maira.modules.skills.models import Skill
from maira.modules.skills.prompt import build_skill_prompt
from maira.modules.skills.runner import RunError, execute, extract_command, plan_run
from maira.modules.skills.service import SkillService
from maira.modules.skills.source import SkillSource, SourceError, parse_source
from maira.modules.skills.store import SkillStore

PDF_SKILL = """---
name: pdf
description: Use this skill whenever the user wants to merge, split or fill PDF files.
license: MIT
---
# PDF guide

Use pypdf. For forms read forms.md first.
Run `python scripts/count_pages.py file.pdf` to count pages.
"""


def _write(path: Path, text: str) -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")
  return path


@pytest.fixture
def skill_repo(tmp_path: Path) -> Path:
  repo = tmp_path / "repo"
  _write(repo / "README.md", "# Skills\n\nA collection of skills.\n")
  _write(repo / "skills/pdf/SKILL.md", PDF_SKILL)
  _write(repo / "skills/pdf/forms.md", "# Forms\nFill fields with fill_form.py.\n")
  _write(repo / "skills/pdf/scripts/count_pages.py", "import sys\nprint('pages:', len(sys.argv[1:]))\n")
  _write(repo / "skills/notes/SKILL.md", "---\nname: meeting-notes\ndescription: Write tidy meeting notes with action items and owners.\n---\nUse bullet points.\n")
  _write(repo / "template/SKILL.md", "---\nname: template-skill\ndescription: Replace me\n---\n")
  _write(repo / "node_modules/x/SKILL.md", "---\nname: ignored\n---\n")
  return repo


# --- source ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
  ("text", "expected"),
  [
    ("anthropics/skills", ("anthropics", "skills", "", "")),
    ("https://github.com/anthropics/skills", ("anthropics", "skills", "", "")),
    ("github.com/anthropics/skills.git", ("anthropics", "skills", "", "")),
    ("https://github.com/anthropics/skills/tree/main/skills/pdf", ("anthropics", "skills", "main", "skills/pdf")),
    ("https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md", ("anthropics", "skills", "main", "skills/pdf")),
    ("git@github.com:obra/superpowers.git", ("obra", "superpowers", "", "")),
    ("<https://www.github.com/obra/superpowers>.", ("obra", "superpowers", "", "")),
  ],
)
def test_parse_source(text, expected) -> None:
  source = parse_source(text)
  assert (source.owner, source.repo, source.ref, source.subpath) == expected


@pytest.mark.parametrize("text", ["", "https://gitlab.com/a/b", "https://github.com/onlyowner", "github.com/a/b/tree/main/../../x"])
def test_parse_source_rejects(text) -> None:
  with pytest.raises(SourceError):
    parse_source(text)


def test_parse_local_folder(tmp_path) -> None:
  source = parse_source(str(tmp_path))
  assert source.is_local and source.label == tmp_path.name
  with pytest.raises(SourceError):
    parse_source(str(tmp_path / "missing"))


# --- download ------------------------------------------------------------------------------


def _zip(entries: dict[str, bytes], symlink: str | None = None) -> bytes:
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, "w") as archive:
    for name, data in entries.items():
      archive.writestr(name, data)
    if symlink:
      info = zipfile.ZipInfo(symlink)
      info.external_attr = 0o120777 << 16
      archive.writestr(info, "/etc/passwd")
  return buffer.getvalue()


def test_safe_extract_zip_blocks_escapes(tmp_path) -> None:
  data = _zip(
    {"repo-main/SKILL.md": b"ok", "repo-main/../../evil.txt": b"x", "repo-main/a/b.txt": b"b"},
    symlink="repo-main/link",
  )
  safe_extract_zip(data, tmp_path / "out")
  assert (tmp_path / "out/SKILL.md").read_text() == "ok"
  assert (tmp_path / "out/a/b.txt").exists()
  assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "out/link").exists()


def test_fetch_local_folder_skips_heavy_dirs(skill_repo, tmp_path) -> None:
  result = fetch(parse_source(str(skill_repo)), tmp_path / "dest")
  assert (result.path / "skills/pdf/SKILL.md").exists()
  assert not (result.path / "node_modules").exists()


def _git(*args: str, cwd: Path) -> None:
  subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_fetch_with_git_subfolder_and_branch(skill_repo, tmp_path, monkeypatch) -> None:
  _git("init", "-q", "-b", "main", cwd=skill_repo)
  _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=skill_repo)
  _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=skill_repo)
  _git("branch", "feature/x", cwd=skill_repo)
  monkeypatch.setattr(SkillSource, "clone_url", property(lambda self: skill_repo.as_uri()))

  result = fetch(parse_source("github.com/me/repo/tree/feature/x/skills/pdf"), tmp_path / "dest")
  assert result.ref == "feature/x" and len(result.commit) == 40
  assert (result.path / "SKILL.md").exists() and not (result.path / ".git").exists()

  with pytest.raises(FetchError):
    fetch(parse_source("github.com/me/repo/tree/main/no/such/folder"), tmp_path / "dest2")


def test_fetch_zip_when_git_missing(skill_repo, tmp_path, monkeypatch) -> None:
  entries = {f"repo-HEAD/{p.relative_to(skill_repo).as_posix()}": p.read_bytes() for p in skill_repo.rglob("*") if p.is_file()}
  data = _zip(entries)

  class Response:
    status_code = 200

    def raise_for_status(self) -> None:
      pass

    def iter_bytes(self):
      yield data

    def __enter__(self):
      return self

    def __exit__(self, *exc):
      return False

  import httpx

  urls: list[str] = []
  monkeypatch.setattr("maira.modules.skills.fetch.shutil.which", lambda _name: None)
  monkeypatch.setattr(httpx, "stream", lambda method, url, **kw: urls.append(url) or Response())
  result = fetch(parse_source("me/repo"), tmp_path / "dest")
  assert urls == ["https://github.com/me/repo/archive/HEAD.zip"]
  assert (result.path / "skills/pdf/scripts/count_pages.py").exists()


# --- discovery -------------------------------------------------------------------------------


def test_discover_skill_files(skill_repo) -> None:
  found = {s.name: s for s in discover(skill_repo)}
  assert set(found) == {"pdf", "meeting-notes"}  # template and node_modules skipped
  pdf = found["pdf"]
  assert pdf.folder == "skills/pdf" and pdf.entry == "skills/pdf/SKILL.md" and pdf.license == "MIT"
  assert pdf.scripts == ["scripts/count_pages.py"]


def test_discover_commands_and_repo_fallback(tmp_path) -> None:
  plugin = tmp_path / "plugin"
  _write(plugin / ".claude-plugin/plugin.json", "{}")
  _write(plugin / "commands/review.md", "---\ndescription: Review the diff\n---\nReview $ARGUMENTS carefully.\n")
  _write(plugin / ".claude/commands/git/commit.md", "Write a commit message.\n")
  found = {s.name: s for s in discover(plugin)}
  assert found["review"].kind == "command" and found["review"].description == "Review the diff"
  assert "git-commit" in found

  plain = tmp_path / "plain"
  _write(plain / "README.md", "# Tool\n\n[![badge](x.svg)](y)\n\nTool converts **CSV** files to [JSON](http://x).\n")
  _write(plain / "AGENTS.md", "Always run tests.\n")
  _write(plain / "tool.py", "print(1)\n")
  (skill,) = discover(plain, name_hint="My Tool")
  assert (skill.name, skill.kind, skill.entry) == ("my-tool", "repo", "README.md")
  assert skill.description == "Tool converts CSV files to JSON."
  assert skill.scripts == ["tool.py"]

  empty = tmp_path / "empty"
  _write(empty / "main.go", "package main\n")
  (only,) = discover(empty, name_hint="empty")
  assert only.kind == "repo" and "empty" in only.description


def test_frontmatter_tolerates_broken_yaml() -> None:
  meta, body = split_frontmatter("---\nname: x\ndescription: Use when: things break\n---\nBody")
  assert meta == {"name": "x", "description": "Use when: things break"} and body == "Body"
  assert split_frontmatter("no front matter") == ({}, "no front matter")
  assert first_paragraph("# T\n\n<p align=center><img src=x></p>\n\nShort.\n\nA real paragraph about it.") == "A real paragraph about it."


def test_duplicate_names_get_unique(tmp_path) -> None:
  _write(tmp_path / "a/pdf/SKILL.md", "---\nname: pdf\ndescription: one\n---\n")
  _write(tmp_path / "b/pdf/SKILL.md", "---\nname: pdf\ndescription: two\n---\n")
  names = sorted(s.name for s in discover(tmp_path))
  assert names == ["b-pdf", "pdf"] or names == ["a-pdf", "pdf"]


# --- store -------------------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> SkillStore:
  return SkillStore(tmp_path / "skills")


def test_install_update_remove(store, skill_repo, tmp_path) -> None:
  report = store.install(str(skill_repo))
  assert not report.was_installed and sorted(report.added) == ["meeting-notes", "pdf"]
  pack = report.pack
  assert pack.id == "local-repo"
  pdf = store.find("/pdf")[0]
  assert pdf.id == "local-repo/pdf" and pdf.enabled and not pdf.scripts_allowed and pdf.scripts_hash
  assert "Use pypdf" in store.read_entry(pdf)

  store.set_scripts_allowed(pdf.id, True)
  store.set_enabled("local-repo/meeting-notes", False)
  again = SkillStore(store.root)  # registry survives a restart
  assert again.get(pdf.id).scripts_allowed and not again.get("local-repo/meeting-notes").enabled

  # Update: same scripts keep permission; the disabled skill stays disabled.
  report = store.install(str(skill_repo))
  assert report.was_installed and store.get(pdf.id).scripts_allowed
  assert not store.get("local-repo/meeting-notes").enabled

  # Changed script content must be approved again.
  _write(skill_repo / "skills/pdf/scripts/count_pages.py", "print('changed')\n")
  store.install(str(skill_repo))
  assert not store.get(pdf.id).scripts_allowed

  assert store.find_pack(str(skill_repo)) is not None
  store.remove_pack(pack.id)
  assert store.packs() == [] and not (store.packs_dir / pack.id).exists()


def test_failed_install_keeps_old_version(store, skill_repo) -> None:
  store.install(str(skill_repo))
  shutil.rmtree(skill_repo)
  with pytest.raises(Exception):
    store.install(SkillSource(local_path=str(skill_repo)))
  assert store.find("pdf") and (store.packs_dir / "local-repo/skills/pdf/SKILL.md").exists()


# --- matching -------------------------------------------------------------------------------


def _skill(name: str, description: str, kind: str = "skill") -> Skill:
  return Skill(id=f"p/{name}", name=name, description=description, kind=kind, pack="p", folder="", entry="")


SKILLS = [
  _skill("pdf", "Use this skill whenever the user wants to merge, split, fill or read PDF files."),
  _skill("xlsx", "Create and edit spreadsheet files: Excel workbooks, formulas, charts, CSV."),
  _skill("writing-plans", "Use when you have a spec or requirements for a multi-step task."),
  _skill("review", "Review code", kind="command"),
]


@pytest.mark.parametrize(
  ("text", "name", "rest"),
  [
    ("/pdf merge a.pdf b.pdf", "pdf", "merge a.pdf b.pdf"),
    ("use the pdf skill to split report.pdf", "pdf", "split report.pdf"),
    ("pdf skill se merge karo", "pdf", "merge karo"),
    ("/review", "review", ""),
  ],
)
def test_explicit_skill(text, name, rest) -> None:
  match = SkillMatcher(SKILLS).match(text)
  assert isinstance(match, SkillMatch) and match.explicit
  assert (match.skill.name, match.request) == (name, rest)


def test_unknown_skill_by_name() -> None:
  assert SkillMatcher(SKILLS).match("/nothing do x") == UnknownSkill("nothing")
  assert SkillMatcher(SKILLS).match("use foo skill for y") == UnknownSkill("foo")


@pytest.mark.parametrize(
  ("text", "name"),
  [
    ("merge these two pdf files", "pdf"),
    ("make an excel sheet of my expenses", "xlsx"),
    ("how are you", None),
    ("plan my day", None),
    ("add task call mom at 6pm", None),
    ("review my code", None),  # commands only run when called by name
  ],
)
def test_auto_match(text, name) -> None:
  match = SkillMatcher(SKILLS).match(text)
  assert (match.skill.name if match else None) == name


def test_disabled_skills_are_not_matched() -> None:
  off = _skill("pdf", SKILLS[0].description)
  off.enabled = False
  assert SkillMatcher([off]).match("merge two pdf files") is None
  assert SkillMatcher([off]).match("/pdf x") == UnknownSkill("pdf")


# --- prompt --------------------------------------------------------------------------------------


def test_prompt_includes_instructions_links_and_script_rules(store, skill_repo) -> None:
  store.install(str(skill_repo))
  pdf = store.find("pdf")[0]
  prompt = build_skill_prompt(store, pdf, "fill the form", 6000)
  assert 'using the skill "pdf"' in prompt and "Use pypdf." in prompt
  assert "--- forms.md ---" in prompt  # linked file pulled in
  assert "running them is turned off" in prompt and "```run" not in prompt

  store.set_scripts_allowed(pdf.id, True)
  prompt = build_skill_prompt(store, store.get(pdf.id), "x", 6000)
  assert "```run" in prompt and "scripts/count_pages.py" in prompt

  short = build_skill_prompt(store, pdf, "x", 1000)
  assert len(short) < 2000


def test_command_arguments_and_repo_prompt(store, tmp_path) -> None:
  plugin = tmp_path / "plugin"
  _write(plugin / ".claude/commands/review.md", "Review $ARGUMENTS. Focus on $1.\n")
  store.install(str(plugin))
  review = store.find("review")[0]
  assert "Review security of login. Focus on security." in build_skill_prompt(store, review, "security of login", 4000)

  plain = tmp_path / "plain"
  _write(plain / "README.md", "# Tool\n\nTool converts CSV to JSON. Usage: tool in.csv\n")
  _write(plain / "CLAUDE.md", "Prefer small functions.\n")
  store.install(str(plain))
  repo_skill = store.find("plain")[0]
  prompt = build_skill_prompt(store, repo_skill, "how do I use it", 4000)
  assert "--- CLAUDE.md ---" in prompt and "Usage: tool in.csv" in prompt


# --- scripts -----------------------------------------------------------------------------------


def test_run_rules(tmp_path) -> None:
  folder = tmp_path / "skill"
  _write(folder / "scripts/hello.py", "import sys\nprint('hello', *sys.argv[1:])\n")
  scripts = ["scripts/hello.py"]
  plan = plan_run('python scripts/hello.py "big file.pdf"', folder, scripts)
  assert plan.argv[1].endswith("hello.py") and plan.argv[-1] == "big file.pdf"
  for bad in ["python -c 'print(1)'", "python -m pip install x", "python ../x.py", "python scripts/hello.py | sh",
              "python scripts/hello.py; rm -rf /", "bash -c ls", "node --eval=1 scripts/hello.py", "python other.py"]:
    with pytest.raises(RunError):
      plan_run(bad, folder, scripts)

  result = execute(plan, cwd=tmp_path / "work", timeout=30)
  assert result.ok and result.output == "hello big file.pdf"

  _write(folder / "scripts/slow.py", "import time\ntime.sleep(5)\n")
  slow = execute(plan_run("python scripts/slow.py", folder, ["scripts/slow.py"]), cwd=tmp_path, timeout=1)
  assert slow.timed_out and not slow.ok


def test_extract_command() -> None:
  scripts = ["scripts/hello.py"]
  assert extract_command("Sure:\n```run\npython scripts/hello.py a\n```", scripts) == "python scripts/hello.py a"
  assert extract_command("```bash\n$ python scripts/hello.py\n```", scripts) == "python scripts/hello.py"
  assert extract_command("```python\nimport os\n```", scripts) is None
  assert extract_command("no block", scripts) is None


# --- chat service --------------------------------------------------------------------------------


@pytest.fixture
def service(store) -> SkillService:
  return SkillService(store)


def _wait_install(service: SkillService, text: str) -> str:
  done = threading.Event()
  messages: list[str] = []
  service.set_notifier(lambda message: (messages.append(message), done.set()))
  reply = service.handle(text)
  assert reply is not None
  assert done.wait(20), reply.text
  return messages[0]


@pytest.mark.parametrize(
  "text",
  ["install skill {p}", "add skills from {p}", "install {p}", "{p} skill install karo", "adopt repo {p}"],
)
def test_install_phrases(service, skill_repo, text) -> None:
  message = _wait_install(service, text.format(p=skill_repo))
  assert message.startswith("Installed repo: 2 skills")
  assert "1 of them include scripts" in message


def test_non_skill_messages_pass_through(service) -> None:
  for text in ["add task buy milk", "learn python/django", "how are you", "yes", "remind me in 5 minutes"]:
    assert service.handle(text) is None


def test_list_remove_toggle_info(service, store, skill_repo) -> None:
  assert "No skills yet" in service.handle("my skills").text
  store.install(str(skill_repo))
  listing = service.handle("what skills do you have").text
  assert "repo: " in listing and "pdf" in listing
  assert "Turned off pdf" in service.handle("turn off skill pdf").text
  assert "pdf (off)" in service.handle("skills").text
  assert "Turned on" in service.handle("pdf skill chalu karo").text
  assert "Instructions only" in service.handle("what does the meeting-notes skill do").text
  assert "turned it off" in service.handle("remove skill pdf").text  # part of a bigger repo
  assert "Removed repo" in service.handle("remove skills repo").text
  assert store.packs() == []


def test_script_offer_and_run(service, store, skill_repo) -> None:
  store.install(str(skill_repo))
  context = service.select("/pdf count pages of a.pdf")
  reply = "I'll count them.\n```run\npython scripts/count_pages.py a.pdf\n```"
  assert "Scripts are off" in service.after_reply(context, reply)
  assert service.pending is None

  store.set_scripts_allowed(context.skill.id, True)
  offer = service.after_reply(service.select("/pdf count pages"), reply)
  assert "Say **run**" in offer and service.pending is not None
  assert service.handle("cancel").text == "Okay, not running it."
  assert service.pending is None

  service.after_reply(service.select("/pdf count pages"), reply)
  approved = service.handle("haan")
  assert approved.action is not None
  text, result = service.run_action(approved.action)
  assert text == "" and result.ok and result.output == "pages: 1"
  assert "done in" in SkillService.format_result(approved.action.plan.display, result)


def test_missing_package_offer(service, store, skill_repo, monkeypatch) -> None:
  _write(skill_repo / "skills/pdf/scripts/count_pages.py", "import pypdf_not_installed_x\n")
  store.install(str(skill_repo))
  pdf = store.find("pdf")[0]
  store.set_scripts_allowed(pdf.id, True)
  service.after_reply(service.select("/pdf x"), "```run\npython scripts/count_pages.py\n```")
  text, result = service.run_action(service.handle("run").action)
  assert result is None and "pypdf_not_installed_x" in text
  installed: list = []
  monkeypatch.setattr("maira.modules.skills.envs.pip_install", lambda d, pack, pkg: (installed.append(pkg), (True, ""))[1])
  text, _ = service.run_action(service.handle("yes").action)
  assert installed == ["pypdf_not_installed_x"] and text.startswith("Installed")


def test_select_respects_settings(store, skill_repo) -> None:
  store.install(str(skill_repo))
  auto = SkillService(store)
  assert auto.select("merge two pdf files").skill.name == "pdf"
  manual = SkillService(store, auto_use=False)
  assert manual.select("merge two pdf files") is None
  assert manual.select("/pdf merge").skill.name == "pdf"
  off = SkillService(store, enabled=False)
  assert off.select("/pdf merge") is None
  store.set_enabled("local-repo/pdf", False)
  assert "turned off" in auto.unknown_reply(auto.select("/pdf merge"))
