"""Skills through the brain: commands, skill prompt, approval, script run and explanation."""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from maira.core.bus.event_bus import EventBus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN
from maira.modules.skills.service import SkillService
from maira.modules.skills.store import SkillStore
from tests.unit.test_brain_service import FakeLLM
from tests.unit.test_skills import PDF_SKILL, _write


class ScriptedLLM(FakeLLM):
  """Replies from a queue and records the options of each call."""

  def __init__(self, replies: list[str]) -> None:
    super().__init__()
    self.replies = list(replies)
    self.options: list[dict | None] = []

  def chat_stream(self, messages: Sequence[dict[str, str]], *, options: dict | None = None) -> Iterator[str]:
    self.calls.append(list(messages))
    self.options.append(options)
    yield self.replies.pop(0) if self.replies else "ok"


@pytest.fixture
def setup(tmp_path: Path):
  repo = tmp_path / "repo"
  _write(repo / "skills/pdf/SKILL.md", PDF_SKILL)
  _write(repo / "skills/pdf/scripts/count_pages.py", "import sys\nprint('pages:', 7)\n")
  store = SkillStore(tmp_path / "skills")
  store.install(str(repo))
  skills = SkillService(store, context_window=9000)
  storage = SqliteStorage(tmp_path / "b.db")
  apply_migrations(storage)
  bus = EventBus()
  events: dict[str, list] = {"done": [], "used": [], "tokens": []}
  bus.subscribe(TOPIC_COMPLETE, lambda p: events["done"].append(p["content"]))
  bus.subscribe(TOPIC_TOKEN, lambda p: events["tokens"].append(p.get("token", "")))
  bus.subscribe("skill.used", lambda p: events["used"].append(p["name"]))

  def make(replies: list[str]) -> tuple[BrainService, ScriptedLLM]:
    llm = ScriptedLLM(replies)
    return BrainService(llm, bus, ConversationRepository(storage), skills=skills), llm

  return store, skills, make, events


def test_skill_prompt_and_context_window(setup) -> None:
  _store, _skills, make, events = setup
  brain, llm = make(["Use pypdf's PdfWriter."])
  brain.send_message("how do I merge two pdf files?")
  system = llm.calls[0][0]["content"]
  assert system.startswith('You are using the skill "pdf"') and "Use pypdf." in system
  assert llm.options[0]["num_ctx"] == 9000
  assert events["used"] == ["pdf"] and events["done"][-1] == "Use pypdf's PdfWriter."

  brain.send_message("how are you")  # no skill: normal prompt
  assert not llm.calls[1][0]["content"].startswith("You are using the skill")
  assert "num_ctx" not in (llm.options[1] or {})


def test_unknown_skill_and_commands_skip_the_llm(setup) -> None:
  _store, _skills, make, events = setup
  brain, llm = make([])
  brain.send_message("/nope do x")
  brain.send_message("my skills")
  assert llm.calls == []
  assert 'No skill called "nope"' in events["done"][0]
  assert "repo: pdf" in events["done"][1]
  assert [m.content for m in brain.get_history()][:2] == ["/nope do x", events["done"][0]]


def test_install_result_arrives_in_chat(setup, tmp_path) -> None:
  _store, _skills, make, events = setup
  other = tmp_path / "other"
  _write(other / "README.md", "# Other\n\nA tool that renames photos by date.\n")
  brain, _llm = make([])
  arrived = threading.Event()
  events_done = events["done"]
  brain._bus.subscribe(TOPIC_COMPLETE, lambda p: "Installed other" in p["content"] and arrived.set())  # noqa: SLF001
  brain.send_message(f"install skill {other}")
  assert events_done[0].startswith("Installing skills from other")
  assert arrived.wait(20)
  assert brain.get_history()[-1].content.startswith("Installed other: 1 skill (other).")


def test_script_needs_permission_then_approval(setup) -> None:
  store, _skills, make, events = setup
  run_reply = "Counting pages.\n```run\npython scripts/count_pages.py a.pdf\n```"
  brain, llm = make([run_reply, run_reply, "The PDF has 7 pages."])

  brain.send_message("/pdf how many pages in a.pdf")
  assert "Scripts are off for pdf" in events["done"][-1]

  store.set_scripts_allowed("local-repo/pdf", True)
  brain.send_message("/pdf how many pages in a.pdf")
  assert "Say **run**" in events["done"][-1]

  brain.send_message("haan")
  final = events["done"][-1]
  assert "Ran `python scripts/count_pages.py a.pdf` — done in" in final
  assert "pages: 7" in final and final.endswith("The PDF has 7 pages.")
  followup = llm.calls[-1][-1]["content"]
  assert followup.startswith("I ran `python scripts/count_pages.py a.pdf`. Exit code 0.")
  assert brain.get_history()[-2].content == "haan"

  brain.send_message("haan")  # nothing pending any more: normal chat
  assert llm.calls[-1][-1]["content"] == "haan"


def test_cancel_and_other_message_drop_the_offer(setup) -> None:
  store, skills, make, events = setup
  store.set_scripts_allowed("local-repo/pdf", True)
  run_reply = "```run\npython scripts/count_pages.py\n```"
  brain, _llm = make([run_reply, run_reply, "a document format"])
  brain.send_message("/pdf count")
  brain.send_message("mat karo")
  assert events["done"][-1] == "Okay, not running it." and skills.pending is None
  brain.send_message("/pdf count")
  assert skills.pending is not None
  brain.send_message("what is a pdf anyway")
  assert skills.pending is None
