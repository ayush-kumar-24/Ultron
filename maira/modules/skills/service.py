"""Skills in conversation: chat commands, choosing a skill, and approved script runs."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from maira.modules.skills import envs
from maira.modules.skills.matcher import SkillMatch, SkillMatcher, UnknownSkill, explicit_request
from maira.modules.skills.models import KIND_REPO, Skill
from maira.modules.skills.prompt import build_skill_prompt
from maira.modules.skills.runner import RunError, RunPlan, RunResult, execute, extract_command, missing_module, plan_run
from maira.modules.skills.source import SourceError, parse_source
from maira.modules.skills.store import SkillError, SkillStore

PENDING_SECONDS = 10 * 60
_YES = re.compile(r"^(?:yes|y|yeah|yep|ok|okay|sure|run|run it|go|go ahead|do it|haan|han|ha|haa|haanji|ji|theek hai|thik hai|chalao|chala do|chalao na|kar do|karo|install|install it|install karo)[.! ]*$", re.IGNORECASE)
_NO = re.compile(r"^(?:no|n|nope|cancel|stop|don'?t|nahi|nahin|na|mat|mat karo|rehne do|chhodo|skip)[.! ]*$", re.IGNORECASE)

_SRC = r"(?P<src>(?:https?://)?(?:www\.)?github\.com/\S+|git@github\.com:\S+|[\w.-]+/[\w.-]+(?:/\S*)?|[A-Za-z]:[\\/]\S.*?|~?/\S.*?)"
_INSTALL = [
  re.compile(rf"^(?:please\s+)?(?:install|add|adopt|learn|get|download|import|use)\s+(?:(?:this|the|a|new|these)\s+)?(?:skills?|repo|repository|github\s+repo)\s+(?:from\s+)?{_SRC}\s*$", re.IGNORECASE),
  re.compile(rf"^(?:please\s+)?(?:install|adopt|import)\s+(?:from\s+)?{_SRC}\s*$", re.IGNORECASE),
  re.compile(rf"^(?:yeh\s+|ye\s+|is\s+)?{_SRC}\s+(?:wala\s+|wali\s+)?(?:skills?\s+|repo\s+)?(?:install|add|adopt|seekh|sikh|learn|le)\s*(?:karo|kar\s+lo|kar\s+do|lo|le|na)?\s*$", re.IGNORECASE),
  re.compile(r"^(?P<src>(?:https?://)?(?:www\.)?github\.com/[\w.-]+/[\w.-]+\S*)\s*$", re.IGNORECASE),
]
_LIST = re.compile(r"^(?:(?:show|list|see)\s+(?:me\s+)?(?:all\s+|my\s+)*(?:installed\s+)?skills|(?:my|all|installed)\s+skills|skills|what\s+skills\s+(?:do\s+you\s+have|are\s+installed|have\s+you\s+learn(?:ed|t))|(?:kaunse|konse|kon\s+se|kaun\s+se)\s+skills?\s+(?:hain|hai|h)|skills?\s+(?:dikhao|batao|list))\s*\??$", re.IGNORECASE)
_REMOVE = [
  re.compile(r"^(?:remove|delete|uninstall|forget)\s+(?:the\s+)?(?:skills?|repo)\s+(?P<name>.+?)\s*$", re.IGNORECASE),
  re.compile(r"^(?P<name>.+?)\s+(?:skills?|repo)\s+(?:hatao|hata\s+do|delete\s+karo|remove\s+karo|uninstall\s+karo)\s*$", re.IGNORECASE),
]
_UPDATE = [
  re.compile(r"^update\s+(?:all\s+)?(?:(?:my|the)\s+)?(?:skills?|repo)(?:\s+(?P<name>.+?))?\s*$", re.IGNORECASE),
  re.compile(r"^(?:(?P<name>.+?)\s+)?skills?\s+update\s+(?:karo|kar\s+do)\s*$", re.IGNORECASE),
]
_TOGGLE = [
  (re.compile(r"^(?:turn\s+off|disable|stop\s+using)\s+(?:the\s+)?skills?\s+(?P<name>.+?)\s*$", re.IGNORECASE), False),
  (re.compile(r"^(?:turn\s+on|enable|start\s+using)\s+(?:the\s+)?skills?\s+(?P<name>.+?)\s*$", re.IGNORECASE), True),
  (re.compile(r"^(?P<name>.+?)\s+skills?\s+(?:band\s+karo|off\s+karo|disable\s+karo)\s*$", re.IGNORECASE), False),
  (re.compile(r"^(?P<name>.+?)\s+skills?\s+(?:chalu\s+karo|on\s+karo|enable\s+karo)\s*$", re.IGNORECASE), True),
]
_INFO = [
  re.compile(r"^(?:what\s+(?:does|is)\s+(?:the\s+)?(?P<name>[\w./-]+)\s+skill(?:\s+do)?|(?:about|info|describe)\s+(?:the\s+)?skill\s+(?P<name2>[\w./-]+)|skill\s+(?P<name3>[\w./-]+)\s+(?:info|details|kya\s+karta\s+hai))\s*\??$", re.IGNORECASE),
]


@dataclass(frozen=True)
class PendingAction:
  kind: str  # "run" or "pip"
  skill: Skill
  plan: RunPlan | None = None
  package: str = ""
  created: float = 0.0


@dataclass(frozen=True)
class SkillReply:
  """A local reply (no LLM). ``action`` is set when the user approved a run."""

  text: str
  action: PendingAction | None = None


@dataclass(frozen=True)
class SkillContext:
  skill: Skill
  request: str
  prompt: str  # goes before the normal system prompt
  explicit: bool


class SkillService:
  def __init__(
    self,
    store: SkillStore,
    *,
    enabled: bool = True,
    auto_use: bool = True,
    max_chars: int = 6000,
    context_window: int = 8192,
    script_timeout: int = 120,
  ) -> None:
    self.store = store
    self.enabled = enabled
    self.auto_use = auto_use
    self.max_chars = max_chars
    self.context_window = context_window
    self.script_timeout = script_timeout
    self.envs_dir = store.root / "envs"
    self._lock = threading.Lock()
    self._matcher: SkillMatcher | None = None
    self._pending: PendingAction | None = None
    self._installing: set[str] = set()
    self._notify: Callable[[str], None] = lambda _text: None
    self._on_change: Callable[[], None] = lambda: None
    store.on_change(self._store_changed)

  def set_notifier(self, notify: Callable[[str], None]) -> None:
    """Where background results go (the brain posts them in chat)."""
    self._notify = notify

  def set_change_listener(self, listener: Callable[[], None]) -> None:
    self._on_change = listener

  def _store_changed(self) -> None:
    with self._lock:
      self._matcher = None
    self._on_change()

  def _get_matcher(self) -> SkillMatcher:
    with self._lock:
      if self._matcher is None:
        self._matcher = SkillMatcher(self.store.skills(enabled_only=True))
      return self._matcher

  # --- chat commands ------------------------------------------------------------------

  def handle(self, text: str) -> SkillReply | None:
    """Skill commands and yes/no to a pending run. None = not about skills."""
    reply = self._answer_pending(text)
    if reply is not None:
      return reply
    for pattern in _INSTALL:
      match = pattern.match(text.strip())
      if match:
        return self.start_install(match.group("src"))
    if _LIST.match(text.strip()):
      return SkillReply(self.describe_all())
    for pattern in _REMOVE:
      match = pattern.match(text.strip())
      if match:
        return SkillReply(self._remove(match.group("name")))
    for pattern in _UPDATE:
      match = pattern.match(text.strip())
      if match:
        return self._update(match.group("name") or "")
    for pattern, on in _TOGGLE:
      match = pattern.match(text.strip())
      if match:
        return SkillReply(self._toggle(match.group("name"), on))
    for pattern in _INFO:
      match = pattern.match(text.strip())
      if match:
        name = match.group("name") or match.group("name2") or match.group("name3")
        found = self.store.find(name)
        if found:
          return SkillReply(self.describe(found[0]))
    return None

  def start_install(self, source_text: str, *, notify: Callable[[str], None] | None = None) -> SkillReply:
    try:
      source = parse_source(source_text)
    except SourceError as exc:
      return SkillReply(str(exc))
    key = source.label.lower()
    with self._lock:
      if key in self._installing:
        return SkillReply(f"{source.label} is already being installed.")
      self._installing.add(key)
    already = self.store.find_pack(source.web_url) is not None

    def work() -> None:
      tell = notify or self._notify
      try:
        report = self.store.install(source)
        tell(self._after_install(report))
      except (SkillError, SourceError, RuntimeError, OSError) as exc:
        logger.warning("Skill install failed for {}: {}", source.label, exc)
        tell(f"Couldn't install {source.label}: {exc}")
      except Exception as exc:  # noqa: BLE001
        logger.exception("Skill install crashed")
        tell(f"Couldn't install {source.label}: {exc}")
      finally:
        with self._lock:
          self._installing.discard(key)

    threading.Thread(target=work, name="ultron-skill-install", daemon=True).start()
    verb = "Updating" if already else "Installing"
    return SkillReply(f"{verb} skills from {source.label}… I'll tell you here when it's ready.")

  def _after_install(self, report) -> str:
    text = report.summary
    skills = report.pack.skills
    first = skills[0] if skills else None
    if first is not None:
      if first.kind == KIND_REPO:
        text += f' Ask about it normally, or say "/{first.name} <question>".'
      else:
        text += f' Use one by asking normally, or "/{first.name} <request>".'
    with_scripts = [s for s in skills if s.scripts]
    if len(skills) == 1 and with_scripts:
      text += " It includes scripts; they stay off until you allow them in Settings → Skills."
    elif with_scripts:
      text += (
        f" {len(with_scripts)} of them include scripts; those stay off until you allow them in "
        "Settings → Skills."
      )
    return text

  def _remove(self, name: str) -> str:
    pack = self.store.find_pack(name)
    if pack is not None:
      self.store.remove_pack(pack.id)
      rmtree_env = self.envs_dir / pack.id
      if rmtree_env.exists():
        from maira.modules.skills.fetch import rmtree  # noqa: PLC0415

        rmtree(rmtree_env)
      return f"Removed {pack.label} ({len(pack.skills)} skill{'s' if len(pack.skills) != 1 else ''})."
    found = self.store.find(name)
    if not found:
      return f'No skill called "{name}". Say "my skills" to see them.'
    skill = found[0]
    pack = self.store.pack(skill.pack)
    if pack is not None and len(pack.skills) == 1:
      self.store.remove_pack(pack.id)
      return f"Removed {skill.name}."
    self.store.set_enabled(skill.id, False)
    label = pack.label if pack else skill.pack
    return (
      f"{skill.name} is part of {label}, so I turned it off. "
      f'To delete the whole repo say "remove skills {label}".'
    )

  def _update(self, name: str) -> SkillReply:
    packs = self.store.packs()
    if not packs:
      return SkillReply("No skills installed yet.")
    if not name.strip() or name.strip().lower() in ("all", "sab", "sabhi", "everything"):
      targets = packs
    else:
      pack = self.store.find_pack(name)
      if pack is None:
        found = self.store.find(name)
        pack = self.store.pack(found[0].pack) if found else None
      if pack is None:
        return SkillReply(f'No skills from "{name}". Say "my skills" to see them.')
      targets = [pack]
    replies = [self.start_install(p.web_url) for p in targets]
    return SkillReply(replies[0].text if len(replies) == 1 else f"Updating {len(replies)} skill repos… I'll tell you when done.")

  def _toggle(self, name: str, on: bool) -> str:
    pack = self.store.find_pack(name)
    if pack is not None:
      self.store.set_pack_enabled(pack.id, on)
      return f"{'Turned on' if on else 'Turned off'} all {len(pack.skills)} skills from {pack.label}."
    found = self.store.find(name)
    if not found:
      return f'No skill called "{name}". Say "my skills" to see them.'
    self.store.set_enabled(found[0].id, on)
    return f"{'Turned on' if on else 'Turned off'} {found[0].name}."

  def describe(self, skill: Skill) -> str:
    pack = self.store.pack(skill.pack)
    lines = [f"/{skill.name} — from {pack.label if pack else skill.pack}", skill.description or "(no description)"]
    state = "on" if skill.enabled else "off"
    if skill.scripts:
      scripts = "allowed" if skill.scripts_allowed else "not allowed (Settings → Skills)"
      lines.append(f"Status: {state}. {len(skill.scripts)} script(s), {scripts}.")
    else:
      lines.append(f"Status: {state}. Instructions only, no scripts.")
    return "\n".join(lines)

  def describe_all(self) -> str:
    packs = self.store.packs()
    if not packs:
      return (
        "No skills yet. Give me any GitHub repo, for example:\n"
        "install skill anthropics/skills\n"
        "install skill https://github.com/obra/superpowers"
      )
    lines = [f"Skills ({sum(len(p.skills) for p in packs)}):"]
    for pack in packs:
      names = []
      for skill in pack.skills[:12]:
        mark = "" if skill.enabled else " (off)"
        names.append(f"{skill.name}{mark}")
      more = f" +{len(pack.skills) - 12} more" if len(pack.skills) > 12 else ""
      lines.append(f"• {pack.label}: {', '.join(names)}{more}")
    lines.append('Use one by asking normally, or "/name <request>". Manage them in Settings → Skills.')
    return "\n".join(lines)

  # --- approvals ------------------------------------------------------------------------

  @property
  def pending(self) -> PendingAction | None:
    with self._lock:
      if self._pending and time.monotonic() - self._pending.created > PENDING_SECONDS:
        self._pending = None
      return self._pending

  def _answer_pending(self, text: str) -> SkillReply | None:
    pending = self.pending
    if pending is None:
      return None
    with self._lock:
      self._pending = None  # any reply settles it
    if _YES.match(text.strip()):
      return SkillReply("", action=pending)
    if _NO.match(text.strip()):
      return SkillReply("Okay, not running it.")
    return None  # something else: forget the offer, answer normally

  def _offer(self, action: PendingAction) -> None:
    with self._lock:
      self._pending = action

  def run_action(self, action: PendingAction) -> tuple[str, RunResult | None]:
    """Do an approved action. Returns (text for the chat, result for a follow-up answer)."""
    if action.kind == "pip":
      ok, tail = envs.pip_install(self.envs_dir, action.skill.pack, action.package)
      if ok:
        return f"Installed {action.package} for {action.skill.name}. Ask again and I'll retry.", None
      return f"Couldn't install {action.package}:\n{tail}", None
    assert action.plan is not None
    skill = self.store.get(action.skill.id)
    if skill is None or not skill.scripts_allowed:
      return f"Scripts are no longer allowed for {action.skill.name}.", None
    result = execute(action.plan, cwd=self.store.work_dir, timeout=self.script_timeout)
    module = missing_module(result.output) if not result.ok else None
    if module:
      package = envs.pip_name(module)
      self._offer(PendingAction("pip", skill, package=package, created=time.monotonic()))
      return (
        f"The script needs the Python package **{package}**. Install it for this skill "
        f"(in its own environment, Ultron is not affected)? Say **yes** or **no**."
      ), None
    return "", result

  @staticmethod
  def format_result(display: str, result: RunResult) -> str:
    if result.timed_out:
      status = "stopped: took too long"
    elif result.ok:
      status = f"done in {result.seconds}s"
    else:
      status = f"failed (exit code {result.code})"
    body = result.output or "(no output)"
    return f"Ran `{display}` — {status}.\n```\n{body}\n```"

  # --- choosing a skill for a message --------------------------------------------------------

  def select(self, text: str, *, voice: bool = False) -> SkillContext | UnknownSkill | None:
    if not self.enabled or not self.store.packs():
      return None
    if self.auto_use:
      found = self._get_matcher().match(text)
    else:
      found = explicit_request(text, self.store.skills(enabled_only=True))
    if isinstance(found, UnknownSkill):
      disabled = [s for s in self.store.find(found.name) if not s.enabled]
      return UnknownSkill(found.name if not disabled else f"{found.name} (turned off)")
    if not isinstance(found, SkillMatch):
      return None
    budget = min(self.max_chars, 2000) if voice else self.max_chars
    request = found.request or text
    prompt = build_skill_prompt(self.store, found.skill, request, budget)
    logger.info("Using skill {} ({}, score {})", found.skill.id, "asked" if found.explicit else "auto", found.score)
    return SkillContext(found.skill, request, prompt, found.explicit)

  def context_for(self, skill: Skill, request: str = "") -> SkillContext:
    current = self.store.get(skill.id) or skill
    prompt = build_skill_prompt(self.store, current, request, self.max_chars)
    return SkillContext(current, request, prompt, explicit=True)

  def unknown_reply(self, missing: UnknownSkill) -> str:
    if missing.name.endswith("(turned off)"):
      name = missing.name.removesuffix(" (turned off)")
      return f'The {name} skill is turned off. Say "turn on skill {name}" to use it.'
    return f'No skill called "{missing.name}". Say "my skills" to see them, or "install skill owner/repo".'

  def after_reply(self, context: SkillContext, reply: str) -> str:
    """Offer to run a script the model asked for. Returns text to add to the reply."""
    skill = self.store.get(context.skill.id) or context.skill
    if not skill.scripts:
      return ""
    command = extract_command(reply, skill.scripts)
    if command is None:
      return ""
    if not skill.scripts_allowed:
      return f"\n\n(Scripts are off for {skill.name}. You can allow them in Settings → Skills.)"
    python = envs.env_python(self.envs_dir, skill.pack)
    try:
      plan = plan_run(
        command,
        self.store.skill_dir(skill),
        skill.scripts,
        python=str(python) if python.exists() else None,
      )
    except RunError as exc:
      return f"\n\n(Can't run that: {exc})"
    self._offer(PendingAction("run", skill, plan=plan, created=time.monotonic()))
    return f"\n\nRun `{plan.display}`? Say **run** (or haan) to start, or **cancel**."

  def followup_prompt(self, display: str, result: RunResult) -> str:
    return (
      f"I ran `{display}`. Exit code {result.code}{' (timed out)' if result.timed_out else ''}.\n"
      f"Output:\n```\n{result.output or '(no output)'}\n```\n"
      "Explain the result to me in a few short sentences. If another script run is needed, "
      "write one ```run block."
    )
