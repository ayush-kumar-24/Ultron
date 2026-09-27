"""The agent inside chat: routing, streamed steps, yes/no approvals, and what stays normal chat."""

from __future__ import annotations

import pytest

from maira.core.bus.event_bus import EventBus
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.agent.files import FileAccess
from maira.modules.agent.service import AgentService
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE
from maira.shared.utils.attachments import compose_message
from tests.unit.test_agent import ScriptedModel, call
from tests.unit.test_brain_skills import ScriptedLLM


@pytest.fixture
def setup(tmp_path):
  downloads = tmp_path / "Downloads"
  downloads.mkdir()
  (downloads / "resume.txt").write_text("Ayush — Python developer", encoding="utf-8")
  files = FileAccess([downloads], tmp_path / "data")
  model = ScriptedModel([])
  agent = AgentService(lambda name, msgs, schemas: model(msgs, schemas), files.tools,
                       folders=files.describe_roots, model="qwen3.5:4b")
  storage = SqliteStorage(tmp_path / "b.db")
  apply_migrations(storage)
  bus = EventBus()
  done: list[str] = []
  bus.subscribe(TOPIC_COMPLETE, lambda p: done.append(p["content"]))
  llm = ScriptedLLM(["chat reply", "chat reply"])
  brain = BrainService(llm, bus, ConversationRepository(storage), agent=agent, context_window=8192)
  return brain, llm, model, downloads, done


def test_goal_runs_with_steps_and_approval(setup) -> None:
  brain, llm, model, downloads, done = setup
  model.replies = [
    {"content": "", "tool_calls": [call("find_files", query="resume")]},
    {"content": "", "tool_calls": [call("move_file", source=str(downloads / "resume.txt"),
                                        destination=str(downloads / "resume_2026.txt"))]},
    {"content": "Renamed it to resume_2026.txt.", "tool_calls": []},
  ]
  brain.send_message("rename my resume file to resume_2026")
  assert done[-1].startswith("• Searching for resume\n\nI'd like to:\nMove ")
  assert "Say **yes**" in done[-1] and (downloads / "resume.txt").exists()

  brain.send_message("haan")
  assert done[-1].startswith("• Moving ") and done[-1].endswith("\n\nRenamed it to resume_2026.txt.")
  assert (downloads / "resume_2026.txt").exists()
  assert llm.calls == []  # the chat model was never used
  history = [m.content for m in brain.get_history()]
  assert history[0] == "rename my resume file to resume_2026" and history[2] == "haan"


def test_normal_chat_and_attachments_skip_the_agent(setup, tmp_path) -> None:
  brain, llm, model, _downloads, done = setup
  brain.send_message("how do I send an email with python?")
  assert done[-1] == "chat reply" and llm.options[-1]["num_ctx"] == 8192

  note = tmp_path / "plan.txt"
  note.write_text("send the pdf to the client", encoding="utf-8")
  _display, prompt, _errors = compose_message("summarize this file", [note])
  brain.send_message(prompt)
  assert done[-1] == "chat reply" and model.seen == []


def test_model_problem_is_explained(setup) -> None:
  brain, _llm, model, _downloads, done = setup

  def missing(messages, schemas):
    raise RuntimeError('Model "qwen3.5:4b" is not installed. Run: ollama pull qwen3.5:4b')

  brain._agent._model_call = lambda name, msgs, schemas: missing(msgs, schemas)  # noqa: SLF001
  brain.send_message("do: list my downloads folder")
  assert done[-1].startswith("I couldn't do that:") and "ollama pull qwen3.5:4b" in done[-1]
