"""The action agent: file tools, the approval loop, email/WhatsApp, routing, and Ollama tool calls."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from maira.core.interfaces.desktop import DesktopResult
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.modules.agent.actions import ActionTools, Contacts, normalize_phone
from maira.modules.agent.files import FileAccess
from maira.modules.agent.runner import AgentRunner
from maira.modules.agent.service import AgentService, wants_agent
from maira.modules.agent.tools import ToolError


@pytest.fixture
def home(tmp_path) -> Path:
  for name in ("Downloads", "Documents", "Secret"):
    (tmp_path / name).mkdir()
  (tmp_path / "Downloads" / "Ally_Delivery_Plan.txt").write_text("Deliver 40 boxes on Monday.", encoding="utf-8")
  (tmp_path / "Downloads" / "resume_ayush.txt").write_text("Ayush — Python developer", encoding="utf-8")
  (tmp_path / "Secret" / "passwords.txt").write_text("nope", encoding="utf-8")
  return tmp_path


@pytest.fixture
def files(home, tmp_path) -> FileAccess:
  return FileAccess([home / "Downloads", home / "Documents"], tmp_path / "data")


# --- files ---------------------------------------------------------------------------------------


def test_paths_stay_inside_allowed_folders(files, home) -> None:
  assert files.resolve("Downloads/resume_ayush.txt") == (home / "Downloads" / "resume_ayush.txt").resolve()
  assert files.resolve(str(home / "Documents" / "new.txt")).name == "new.txt"
  for bad in (str(home / "Secret" / "passwords.txt"), "Downloads/../Secret/passwords.txt", "C:/Windows/system32"):
    with pytest.raises(ToolError, match="outside the folders"):
      files.resolve(bad)
  with pytest.raises(ToolError, match="does not exist"):
    files.resolve("Downloads/missing.pdf", must_exist=True)


def test_list_find_read(files, home) -> None:
  assert "Allowed folders" in files.list_folder({})
  listing = files.list_folder({"path": "Downloads"})
  assert "Ally_Delivery_Plan.txt" in listing and "resume_ayush.txt" in listing
  found = files.find_files({"query": "delivery plan"})
  assert "Ally_Delivery_Plan.txt" in found
  assert files.find_files({"query": "passwords"}).startswith("No files matching")  # Secret/ is not allowed
  assert "40 boxes" in files.read_file({"path": "Downloads/Ally_Delivery_Plan.txt"})


def test_read_docx(files, home) -> None:
  import zipfile

  path = home / "Documents" / "letter.docx"
  with zipfile.ZipFile(path, "w") as archive:
    archive.writestr("word/document.xml", "<w:document><w:p><w:t>Dear Sir,</w:t></w:p><w:p><w:t>Thanks.</w:t></w:p></w:document>")
  assert "Dear Sir,\nThanks." in files.read_file({"path": str(path)})


def test_changes_are_described_backed_up_and_reversible(files, home) -> None:
  target = home / "Documents" / "notes.txt"
  assert files.confirm_write({"path": "Documents/notes.txt", "content": "hi"}).startswith("Create the file")
  files.write_file({"path": "Documents/notes.txt", "content": "hello world"})
  assert "Replace the file" in files.confirm_write({"path": "Documents/notes.txt", "content": "x"})
  assert "(1 place" in files.confirm_edit({"path": "Documents/notes.txt", "find": "world", "replace": "Ayush"})
  files.edit_file({"path": "Documents/notes.txt", "find": "world", "replace": "Ayush"})
  assert target.read_text() == "hello Ayush"
  assert list(files.backups.rglob("notes.txt"))  # the old version was kept
  with pytest.raises(ToolError, match="is not in"):
    files.check_edit({"path": "Documents/notes.txt", "find": "missing", "replace": "x"})
  with pytest.raises(ToolError, match="text files only"):
    files.check_write({"path": "Documents/report.pdf", "content": "x"})

  assert "→" in files.confirm_move({"source": "Documents/notes.txt", "destination": "Downloads"})
  files.move_file({"source": "Documents/notes.txt", "destination": "Downloads"})
  assert (home / "Downloads" / "notes.txt").exists() and not target.exists()

  assert "Recycle Bin" in files.confirm_delete({"path": "Downloads/notes.txt"})
  result = files.delete_file({"path": "Downloads/notes.txt"})
  assert not (home / "Downloads" / "notes.txt").exists() and ("Recycle Bin" in result or "trash" in result)
  with pytest.raises(ToolError, match="will not delete"):
    files.check_delete({"path": str(home / "Downloads")})


# --- the loop ------------------------------------------------------------------------------------


def call(name, **arguments):
  return {"name": name, "arguments": arguments}


class ScriptedModel:
  def __init__(self, replies):
    self.replies = list(replies)
    self.seen: list[list[dict]] = []

  def __call__(self, messages, schemas):
    self.seen.append(json.loads(json.dumps(messages, default=str)))
    return self.replies.pop(0) if self.replies else {"content": "Done.", "tool_calls": []}


def runner_for(files, model, **kw):
  progress: list[str] = []
  runner = AgentRunner(model, files.tools(), folders=files.describe_roots(), progress=progress.append, **kw)
  return runner, progress


def test_safe_steps_run_and_risky_steps_wait_for_approval(files, home) -> None:
  model = ScriptedModel([
    {"content": "", "tool_calls": [call("find_files", query="delivery plan")]},
    {"content": "", "tool_calls": [call("move_file", source=str(home / "Downloads" / "Ally_Delivery_Plan.txt"),
                                        destination="Documents")]},
    {"content": "Moved the delivery plan to Documents.", "tool_calls": []},
  ])
  runner, progress = runner_for(files, model)
  outcome = runner.start("move my delivery plan to documents")
  assert outcome.kind == "approval" and "Move" in outcome.text and "Documents" in outcome.text
  assert progress == ["• Searching for delivery plan\n"]
  assert (home / "Downloads" / "Ally_Delivery_Plan.txt").exists()  # nothing moved yet

  outcome = runner.approve()
  assert outcome.kind == "done" and outcome.text == "Moved the delivery plan to Documents."
  assert (home / "Documents" / "Ally_Delivery_Plan.txt").exists()
  tool_results = [m for m in model.seen[-1] if m["role"] == "tool"]
  assert "Found 1" in tool_results[0]["content"] and "Moved to" in tool_results[1]["content"]


def test_decline_tells_the_model_and_changes_nothing(files, home) -> None:
  model = ScriptedModel([
    {"content": "", "tool_calls": [call("delete_file", path="Downloads/resume_ayush.txt")]},
    {"content": "Okay, I left it.", "tool_calls": []},
  ])
  runner, _ = runner_for(files, model)
  assert runner.start("delete my resume").kind == "approval"
  outcome = runner.decline()
  assert outcome.text == "Okay, I left it." and (home / "Downloads" / "resume_ayush.txt").exists()
  assert "The user said no" in model.seen[-1][-1]["content"]


def test_impossible_steps_become_errors_not_questions(files) -> None:
  model = ScriptedModel([
    {"content": "", "tool_calls": [call("delete_file", path="C:/Windows/win.ini"), call("teleport")]},
    {"content": "I can't reach that folder.", "tool_calls": []},
  ])
  runner, _ = runner_for(files, model)
  outcome = runner.start("delete win.ini")
  assert outcome.kind == "done" and runner.pending is None
  results = [m["content"] for m in model.seen[-1] if m["role"] == "tool"]
  assert "outside the folders" in results[0] and "no tool called teleport" in results[1]


def test_repeats_step_limit_and_model_errors(files) -> None:
  looping = ScriptedModel([{"content": "", "tool_calls": [call("list_folder", path="Downloads")]}] * 5)
  outcome = runner_for(files, looping)[0].start("look")
  assert outcome.kind == "done" and "repeating" in outcome.text

  model = ScriptedModel([{"content": "", "tool_calls": [call("find_files", query=f"x{i}")]} for i in range(5)])
  assert "step limit" in runner_for(files, model, max_steps=3)[0].start("search").text

  def broken(messages, schemas):
    raise RuntimeError('Model "qwen3.5:4b" is not installed. Run: ollama pull qwen3.5:4b')

  outcome = runner_for(files, broken)[0].start("anything")
  assert outcome.kind == "error" and "ollama pull" in outcome.text


# --- email / WhatsApp / contacts -----------------------------------------------------------------


class FakeSMTP:
  sent: list = []

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    return False

  def login(self, user, password):
    self.user = (user, password)

  def send_message(self, message):
    FakeSMTP.sent.append(message)


class FakeDesktop:
  def __init__(self, ok=True):
    self.steps, self.ok = [], ok

  def run_steps(self, steps):
    self.steps += [(s.kind, s.args) for s in steps]
    return DesktopResult(self.ok or steps[0].kind == "open_url", "done" if self.ok else "no window")


@pytest.fixture
def actions(files, tmp_path):
  FakeSMTP.sent = []
  return ActionTools(
    files, Contacts(tmp_path / "contacts.json"), desktop=FakeDesktop(),
    email_address=lambda: "me@gmail.com", email_password=lambda: "app-pass",
    smtp_factory=FakeSMTP, sleep=lambda _s: None,
  )


def test_email_with_attachment_to_a_saved_contact(actions) -> None:
  actions.save_contact({"name": "Boss", "email": "boss@corp.com", "phone": "+44 7700 900123"})
  args = {"to": ["boss"], "subject": "Delivery plan", "body": "Attached.", "attachments": ["Downloads/Ally_Delivery_Plan.txt"]}
  question = actions.confirm_email(args)
  assert "to boss@corp.com" in question and "Attached: Ally_Delivery_Plan.txt" in question
  assert actions.send_email(args) == "Email sent to boss@corp.com"
  message = FakeSMTP.sent[0]
  assert message["To"] == "boss@corp.com" and [p.get_filename() for p in message.iter_attachments()] == ["Ally_Delivery_Plan.txt"]


def test_email_errors_reach_the_model_before_any_question(actions) -> None:
  with pytest.raises(ToolError, match="No email address"):
    actions.check_email({"to": ["stranger"], "subject": "x", "body": "y"})
  actions.email_password = lambda: ""
  with pytest.raises(ToolError, match="not set up"):
    actions.check_email({"to": ["a@b.co"], "subject": "x", "body": "y"})


def test_whatsapp_opens_chat_and_presses_send(actions) -> None:
  actions.save_contact({"name": "Mom", "phone": "98765 43210"})
  assert "(+919876543210)" in actions.confirm_whatsapp({"to": "mom", "message": "Reaching at 7"})
  assert actions.send_whatsapp({"to": "mom", "message": "Reaching at 7"}) == "WhatsApp message sent to +919876543210"
  kinds = [k for k, _ in actions.desktop.steps]
  assert kinds == ["open_url", "focus", "press"]
  assert "phone=919876543210" in actions.desktop.steps[0][1]["url"] and "Reaching%20at%207" in actions.desktop.steps[0][1]["url"]

  actions.desktop = FakeDesktop(ok=False)
  assert "press Enter" in actions.send_whatsapp({"to": "+919876543210", "message": "hi"})


def test_phone_numbers() -> None:
  assert normalize_phone("98765 43210") == "919876543210"
  assert normalize_phone("+44 7700 900123") == "447700900123"
  with pytest.raises(ToolError):
    normalize_phone("12345")


# --- routing -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
  ("text", "goal"),
  [
    ("send my resume pdf to boss@corp.com", "send my resume pdf to boss@corp.com"),
    ("find the delivery plan in my downloads", "find the delivery plan in my downloads"),
    ("rename report.pdf to final.pdf", "rename report.pdf to final.pdf"),
    ("do: clean up my desktop", "clean up my desktop"),
    ("agent: tell mom on whatsapp I'm late", "tell mom on whatsapp I'm late"),
    ("how do I send an email with python", None),
    ("what is a pdf file", None),
    ("how are you", None),
    ("play kesariya", None),
    ("add task buy milk", None),
  ],
)
def test_wants_agent(text, goal) -> None:
  assert wants_agent(text) == goal


def test_service_yes_no_and_drop(files) -> None:
  model = ScriptedModel([
    {"content": "", "tool_calls": [call("make_folder", path="Documents/Bills")]},
    {"content": "", "tool_calls": [call("write_file", path="Documents/Bills/readme.txt", content="bills")]},
    {"content": "Created it.", "tool_calls": []},
  ])
  service = AgentService(lambda m, msgs, schemas: model(msgs, schemas), files.tools,
                         folders=files.describe_roots, model="qwen3.5:4b")
  assert service.start("make a bills folder with a readme").kind == "approval" and service.waiting
  assert service.answer("haan").text == "Created it." and not service.waiting
  assert service.answer("yes") is None  # nothing pending: normal chat

  model.replies = [{"content": "", "tool_calls": [call("delete_file", path="Documents/Bills")]}]
  service.start("delete it")
  assert service.answer("what's the weather?") is None and not service.waiting  # a new topic drops the task


# --- Ollama tool calls ---------------------------------------------------------------------------


def _client(handler) -> OllamaClient:
  client = OllamaClient("http://ollama", "llama3.2")
  client._client = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(handler))  # noqa: SLF001
  return client


def test_chat_tools_parses_real_and_text_tool_calls() -> None:
  bodies: list[dict] = []

  def handler(request):
    body = json.loads(request.content)
    bodies.append(body)
    if len(bodies) == 1:
      return httpx.Response(400, json={"error": "llama3.2 does not support thinking"})
    if len(bodies) == 2:
      return httpx.Response(200, json={"message": {"content": "", "tool_calls": [
        {"function": {"name": "find_files", "arguments": {"query": "resume"}}}]}})
    return httpx.Response(200, json={"message": {"content": '```json\n{"name": "read_file", "arguments": {"path": "a.txt"}}\n```'}})

  client = _client(handler)
  first = client.chat_tools([{"role": "user", "content": "x"}], [{"type": "function"}], model="qwen3.5:4b")
  assert first["tool_calls"] == [{"name": "find_files", "arguments": {"query": "resume"}}]
  assert bodies[0]["think"] is False and "think" not in bodies[1] and bodies[1]["model"] == "qwen3.5:4b"
  second = client.chat_tools([], [])
  assert second == {"content": "", "tool_calls": [{"name": "read_file", "arguments": {"path": "a.txt"}}]}


@pytest.mark.parametrize(
  ("error", "expected"),
  [("model 'qwen3.5:4b' not found", "ollama pull qwen3.5:4b"), ("llama2 does not support tools", "cannot use tools")],
)
def test_chat_tools_explains_model_problems(error, expected) -> None:
  from maira.core.exceptions import LLMStreamError

  client = _client(lambda request: httpx.Response(400, json={"error": error}))
  with pytest.raises(LLMStreamError, match=expected):
    client.chat_tools([], [], model="qwen3.5:4b")


@pytest.mark.parametrize(
  ("url", "opened"),
  [("whatsapp://send?phone=91&text=hi", "whatsapp://send?phone=91&text=hi"), ("youtube.com", "https://youtube.com"),
   ("mailto:a@b.co", "mailto:a@b.co"), ("localhost:8000", "https://localhost:8000")],
)
def test_open_url_keeps_app_links(monkeypatch, url, opened) -> None:
  from maira.infrastructure.os import platform

  monkeypatch.setattr(platform.webbrowser, "open", lambda _u: None)
  assert platform.open_url(url) == opened


def test_default_folders_include_onedrive(tmp_path) -> None:
  from maira.modules.agent.files import default_folders

  for rel in ("Desktop", "Downloads", "OneDrive/Desktop", "OneDrive/Documents", "OneDrive - Acme/Documents"):
    (tmp_path / rel).mkdir(parents=True)
  names = [str(p.relative_to(tmp_path)) for p in default_folders(tmp_path)]
  assert names == ["Desktop", "OneDrive/Desktop", "OneDrive/Documents", "OneDrive - Acme/Documents", "Downloads"]
  assert default_folders(tmp_path / "Downloads") == [tmp_path / "Downloads"]  # nothing found: home itself
