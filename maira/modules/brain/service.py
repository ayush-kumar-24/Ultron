"""Brain facade — primary entry point for chat and reasoning requests."""

import threading

from loguru import logger

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Conversation, Message
from maira.core.exceptions import LLMStreamError, LLMUnavailableError, MairaError
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.llm import LLMProvider
from maira.core.interfaces.memory import Memory
from maira.core.interfaces.automation import Automation
from maira.core.interfaces.desktop import DesktopController
from maira.core.interfaces.planner import Planner
from maira.infrastructure.llm.ollama.client import OLLAMA_UNAVAILABLE_USER_MESSAGE
from maira.infrastructure.persistence.sqlite.repositories import ConversationRepository
from maira.modules.automation.parser import parse_schedule_request
from maira.modules.desktop_controller.intent import parse_desktop_request
from maira.modules.brain.context import (
  ContextAssembler,
  MAIRA_IDENTITY_PROMPT,
  MAIRA_VOICE_PROMPT,
)
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.streaming import TokenStreamer
from maira.modules.memory.worker import MemoryWorker
from maira.modules.planner.briefing import BriefingService
from maira.modules.planner.chat import PlannerChat
from maira.modules.skills.matcher import UnknownSkill
from maira.modules.skills.service import PendingAction, SkillContext, SkillService
from maira.shared.utils.latency import begin_trace, clear_trace, current_trace


class ConversationNotFoundError(MairaError):
  """Raised when opening a conversation that does not exist."""


def _title_from_text(text: str) -> str:
  cleaned = " ".join(text.split())
  if not cleaned:
    return "New chat"
  if len(cleaned) <= 48:
    return cleaned
  return f"{cleaned[:45]}..."


class BrainService(Brain):
  def __init__(
    self,
    llm: LLMProvider,
    event_bus: EventBus,
    repository: ConversationRepository,
    session: ConversationSession | None = None,
    memory: Memory | None = None,
    *,
    max_memories: int = 5,
    max_context_chars: int = 2000,
    history_messages: int = 24,
    log_latency: bool = True,
    memory_worker: MemoryWorker | None = None,
    recall_mode: str = "keyword",
    automation: Automation | None = None,
    desktop: DesktopController | None = None,
    planner: Planner | None = None,
    briefing: BriefingService | None = None,
    skills: SkillService | None = None,
  ) -> None:
    self._llm = llm
    self._repo = repository
    self._session = session or ConversationSession()
    self._bus = event_bus
    self._streamer = TokenStreamer(event_bus)
    self._context = ContextAssembler(
      memory,
      max_memories=max_memories,
      max_context_chars=max_context_chars,
    )
    self._history_messages = max(2, history_messages)
    self._log_latency = log_latency
    self._memory_worker = memory_worker
    self._recall_mode = recall_mode if recall_mode in {"keyword", "semantic"} else "keyword"
    self._automation = automation
    self._desktop = desktop
    self._planner_chat = (
      PlannerChat(planner, briefing or BriefingService(planner, automation)) if planner is not None else None
    )
    self._skills = skills
    if skills is not None:
      skills.set_notifier(self.announce)  # "skills installed" arrives later in chat
    # One message at a time: chat, voice and announcements share one session.
    self._turn_lock = threading.RLock()
    self._conversation = self._load_or_create_conversation()

  def _load_or_create_conversation(self) -> Conversation:
    conversation = self._repo.get_latest_conversation()
    if conversation is None:
      conversation = self._repo.create_conversation("New chat")
      self._session.clear()
      return conversation

    self._session.load(self._repo.get_messages(conversation.id))
    return conversation

  def send_message(
    self,
    text: str,
    *,
    voice: bool = False,
    max_tokens: int | None = None,
  ) -> None:
    with self._turn_lock:
      self._send_message(text, voice=voice, max_tokens=max_tokens)

  def announce(self, text: str) -> None:
    """Post an assistant message nobody asked for (e.g. the daily briefing)."""
    reply = text.strip()
    if not reply:
      return
    with self._turn_lock:
      assistant_message = self._session.add_assistant_message(reply)
      self._repo.add_message(self._conversation.id, assistant_message)
      self._streamer.publish_token(reply)
      self._streamer.publish_complete(reply)

  def _send_message(
    self,
    text: str,
    *,
    voice: bool,
    max_tokens: int | None,
  ) -> None:
    cleaned = text.strip()
    if not cleaned:
      return

    # Skills: "install skill owner/repo", "my skills", and yes/no to running a skill script.
    if self._skills is not None and self._try_skill_command(cleaned, voice=voice):
      return

    # Tasks and notes ("add task …", "what's pending", "done 2") — works by voice too.
    if self._planner_chat is not None and self._try_planner_from_chat(cleaned):
      return

    # Timed reminders ("remind me in 10 minutes to …") — chat and voice.
    if self._automation is not None:
      if self._try_schedule_from_chat(cleaned):
        return

    # Immediate desktop OS control (open / type / click / hotkey / play).
    if not voice:
      if self._desktop is None:
        logger.warning("Desktop controller not wired — play/open commands will use LLM only")
      elif self._try_desktop_from_chat(cleaned):
        return

    skill: SkillContext | None = None
    if self._skills is not None:
      found = self._skills.select(cleaned, voice=voice)
      if isinstance(found, UnknownSkill):
        self._reply_locally(cleaned, self._skills.unknown_reply(found))
        return
      skill = found

    model_name = getattr(self._llm, "model", "") or ""
    trace = current_trace() or begin_trace(model=model_name)
    trace.model = model_name or trace.model
    trace.mark("brain_start")

    # Soft availability check (cached on OllamaClient) — avoids a fresh RTT every turn.
    if not self._llm.is_available():
      self._streamer.publish_error(OLLAMA_UNAVAILABLE_USER_MESSAGE)
      clear_trace()
      return

    user_message = self._session.add_user_message(cleaned)
    is_first_turn = len(self._session.get_messages()) == 1

    if voice:
      system_prompt = MAIRA_VOICE_PROMPT
      predict = max_tokens if max_tokens is not None else 64
      # Slightly warmer than before so Hinglish feels natural, still grounded.
      llm_options = {"num_predict": predict, "temperature": 0.5}
      recent_only = min(3, self._history_messages)
      self._streamer.publish_context(
        {"query": cleaned, "memory_ids": [], "memory_titles": [], "char_count": 0}
      )
    else:
      # Keyword recall stays on the hot path; semantic encode/store is background.
      assembled = self._context.assemble(cleaned, recall_mode=self._recall_mode)
      system_prompt = assembled.system_prompt or MAIRA_IDENTITY_PROMPT
      llm_options = {"temperature": 0.7}
      recent_only = self._history_messages
      self._streamer.publish_context(
        {
          "query": cleaned,
          "memory_ids": list(assembled.memory_ids),
          "memory_titles": list(assembled.memory_titles),
          "char_count": assembled.char_count,
        }
      )

    if skill is not None and self._skills is not None:
      system_prompt = f"{skill.prompt}\n\n---\n\n{system_prompt}"
      # Ollama's default context (2048–4096 tokens) would silently cut the skill off.
      llm_options["num_ctx"] = self._skills.context_window
      self._bus.publish("skill.used", {"name": skill.skill.name, "explicit": skill.explicit})

    trace.mark("context_done")

    llm_messages = self._build_llm_messages(
      system_prompt,
      recent_only=recent_only,
      max_content_chars=280 if voice else None,
    )
    trace.prompt_messages = len(llm_messages)
    trace.prompt_chars = sum(len(item.get("content", "")) for item in llm_messages)
    if voice and self._log_latency:
      logger.info(
        "[MAIRA VOICE BRAIN] prompt_msgs={} prompt_chars={} model={}",
        trace.prompt_messages,
        trace.prompt_chars,
        model_name,
      )

    chunks: list[str] = []
    try:
      trace.mark("ollama_start")
      for token in self._llm.chat_stream(llm_messages, options=llm_options):
        chunks.append(token)
        trace.note_token()
        self._streamer.publish_token(token)
    except (LLMUnavailableError, LLMStreamError) as exc:
      self._session.discard_last_user_message()
      message = str(exc) if str(exc) else OLLAMA_UNAVAILABLE_USER_MESSAGE
      if "Cannot reach Ollama" in message or "Ollama is not running" in message:
        message = OLLAMA_UNAVAILABLE_USER_MESSAGE
      self._streamer.publish_error(message)
      clear_trace()
      return

    full_response = "".join(chunks)
    if skill is not None and self._skills is not None:
      offer = self._skills.after_reply(skill, full_response)
      if offer:
        self._streamer.publish_token(offer)
        full_response += offer
    assistant_message = self._session.add_assistant_message(full_response)

    with self._repo.transaction():
      self._repo.add_message(self._conversation.id, user_message)
      self._repo.add_message(self._conversation.id, assistant_message)
      if is_first_turn and self._conversation.title == "New chat":
        title = _title_from_text(cleaned)
        self._repo.update_title(self._conversation.id, title)
        refreshed = self._repo.get_conversation(self._conversation.id)
        if refreshed is not None:
          self._conversation = refreshed

    if self._memory_worker is not None and not voice:
      self._memory_worker.enqueue(cleaned, role="user")

    trace.mark("complete")
    if self._log_latency:
      trace.log_summary()
    self._streamer.publish_complete(full_response)

  def _try_planner_from_chat(self, cleaned: str) -> bool:
    assert self._planner_chat is not None
    try:
      reply = self._planner_chat.handle(cleaned)
    except Exception:  # noqa: BLE001
      logger.exception("Planner command failed; falling back to the LLM")
      return False
    if reply is None:
      return False
    self._reply_locally(cleaned, reply.text)
    if reply.changed:
      self._bus.publish("planner.changed", {"reason": "chat"})
    if reply.speech:
      self._bus.publish("briefing.requested", {"speech": reply.speech})
    logger.info("Planner from chat: {}", reply.text.splitlines()[0])
    return True

  def _try_skill_command(self, cleaned: str, *, voice: bool) -> bool:
    assert self._skills is not None
    try:
      reply = self._skills.handle(cleaned)
    except Exception:  # noqa: BLE001
      logger.exception("Skill command failed; falling back to the LLM")
      return False
    if reply is None:
      return False
    if reply.action is not None:
      self._run_skill_action(cleaned, reply.action, voice=voice)
    else:
      self._reply_locally(cleaned, reply.text)
    return True

  def _run_skill_action(self, cleaned: str, action: PendingAction, *, voice: bool) -> None:
    """The user said yes: run the script (or install its package), then explain the output."""
    assert self._skills is not None
    self._streamer.publish_context({"query": cleaned, "memory_ids": [], "memory_titles": [], "char_count": 0})
    if action.plan is not None:
      self._streamer.publish_token(f"Running `{action.plan.display}`…\n\n")
    elif action.package:
      self._streamer.publish_token(f"Installing {action.package}…\n\n")
    text, result = self._skills.run_action(action)
    if result is None or action.plan is None:
      self._streamer.publish_token(text)
      self._finish_local(cleaned, text)
      return

    report = SkillService.format_result(action.plan.display, result)
    self._streamer.publish_token(report)
    reply = report
    if self._llm.is_available():
      context = self._skills.context_for(action.skill)
      system_prompt = f"{context.prompt}\n\n---\n\n{MAIRA_VOICE_PROMPT if voice else MAIRA_IDENTITY_PROMPT}"
      messages = self._build_llm_messages(system_prompt, recent_only=min(6, self._history_messages))
      messages.append({"role": "user", "content": self._skills.followup_prompt(action.plan.display, result)})
      explanation: list[str] = []
      self._streamer.publish_token("\n\n")
      try:
        options = {"temperature": 0.3, "num_ctx": self._skills.context_window}
        for token in self._llm.chat_stream(messages, options=options):
          explanation.append(token)
          self._streamer.publish_token(token)
      except (LLMUnavailableError, LLMStreamError):
        logger.warning("Could not explain the script output; showing it as is")
      answer = "".join(explanation).strip()
      if answer:
        reply = f"{report}\n\n{answer}"
        offer = self._skills.after_reply(context, answer)
        if offer:
          self._streamer.publish_token(offer)
          reply += offer
    self._finish_local(cleaned, reply)

  def _finish_local(self, cleaned: str, reply: str) -> None:
    """Save a turn whose reply was already streamed, then mark it complete."""
    user_message = self._session.add_user_message(cleaned)
    is_first_turn = len(self._session.get_messages()) == 1
    assistant_message = self._session.add_assistant_message(reply)
    with self._repo.transaction():
      self._repo.add_message(self._conversation.id, user_message)
      self._repo.add_message(self._conversation.id, assistant_message)
      if is_first_turn and self._conversation.title == "New chat":
        self._repo.update_title(self._conversation.id, _title_from_text(cleaned))
        refreshed = self._repo.get_conversation(self._conversation.id)
        if refreshed is not None:
          self._conversation = refreshed
    self._streamer.publish_complete(reply)

  def _reply_locally(self, cleaned: str, reply: str) -> None:
    """Answer without the LLM: save both turns and stream the reply."""
    user_message = self._session.add_user_message(cleaned)
    is_first_turn = len(self._session.get_messages()) == 1
    assistant_message = self._session.add_assistant_message(reply)
    with self._repo.transaction():
      self._repo.add_message(self._conversation.id, user_message)
      self._repo.add_message(self._conversation.id, assistant_message)
      if is_first_turn and self._conversation.title == "New chat":
        self._repo.update_title(self._conversation.id, _title_from_text(cleaned))
        refreshed = self._repo.get_conversation(self._conversation.id)
        if refreshed is not None:
          self._conversation = refreshed
    self._streamer.publish_context(
      {"query": cleaned, "memory_ids": [], "memory_titles": [], "char_count": 0}
    )
    self._streamer.publish_token(reply)
    self._streamer.publish_complete(reply)

  def _try_schedule_from_chat(self, cleaned: str) -> bool:
    assert self._automation is not None
    parsed = parse_schedule_request(cleaned)
    if parsed is None:
      return False

    self._automation.create(
      parsed.title,
      parsed.instruction,
      parsed.run_at,
      action_type=parsed.action_type,
      action_payload=parsed.action_payload,
      recurrence=parsed.recurrence,
    )

    user_message = self._session.add_user_message(cleaned)
    is_first_turn = len(self._session.get_messages()) == 1
    confirmation = parsed.confirmation
    assistant_message = self._session.add_assistant_message(confirmation)

    with self._repo.transaction():
      self._repo.add_message(self._conversation.id, user_message)
      self._repo.add_message(self._conversation.id, assistant_message)
      if is_first_turn and self._conversation.title == "New chat":
        title = _title_from_text(cleaned)
        self._repo.update_title(self._conversation.id, title)
        refreshed = self._repo.get_conversation(self._conversation.id)
        if refreshed is not None:
          self._conversation = refreshed

    self._streamer.publish_context(
      {"query": cleaned, "memory_ids": [], "memory_titles": [], "char_count": 0}
    )
    self._streamer.publish_token(confirmation)
    self._streamer.publish_complete(confirmation)
    self._bus.publish("automation.changed", {"reason": "created"})
    logger.info("Scheduled automation from chat: {}", parsed.title)
    return True

  def _try_desktop_from_chat(self, cleaned: str) -> bool:
    assert self._desktop is not None
    parsed = parse_desktop_request(cleaned)
    if parsed is None:
      return False

    # Clarification-only replies (incomplete command) — no OS steps.
    if not parsed.steps:
      confirmation = parsed.confirmation
      user_message = self._session.add_user_message(cleaned)
      is_first_turn = len(self._session.get_messages()) == 1
      assistant_message = self._session.add_assistant_message(confirmation)
      with self._repo.transaction():
        self._repo.add_message(self._conversation.id, user_message)
        self._repo.add_message(self._conversation.id, assistant_message)
        if is_first_turn and self._conversation.title == "New chat":
          title = _title_from_text(cleaned)
          self._repo.update_title(self._conversation.id, title)
          refreshed = self._repo.get_conversation(self._conversation.id)
          if refreshed is not None:
            self._conversation = refreshed
      self._streamer.publish_token(confirmation)
      self._streamer.publish_complete(confirmation)
      return True

    result = self._desktop.run_steps(list(parsed.steps))
    if result.ok:
      confirmation = parsed.confirmation
      if result.details:
        confirmation = f"{parsed.confirmation} ({'; '.join(result.details)})"
    else:
      confirmation = f"Desktop action failed: {result.message}"

    user_message = self._session.add_user_message(cleaned)
    is_first_turn = len(self._session.get_messages()) == 1
    assistant_message = self._session.add_assistant_message(confirmation)

    with self._repo.transaction():
      self._repo.add_message(self._conversation.id, user_message)
      self._repo.add_message(self._conversation.id, assistant_message)
      if is_first_turn and self._conversation.title == "New chat":
        title = _title_from_text(cleaned)
        self._repo.update_title(self._conversation.id, title)
        refreshed = self._repo.get_conversation(self._conversation.id)
        if refreshed is not None:
          self._conversation = refreshed

    self._streamer.publish_context(
      {"query": cleaned, "memory_ids": [], "memory_titles": [], "char_count": 0}
    )
    self._streamer.publish_token(confirmation)
    self._streamer.publish_complete(confirmation)
    self._bus.publish("desktop.ran", {"ok": result.ok, "message": result.message})
    logger.info("Desktop from chat ok={} msg={}", result.ok, result.message)
    return True

  def _build_llm_messages(
    self,
    system_prompt: str,
    *,
    recent_only: int | None = None,
    max_content_chars: int | None = None,
  ) -> list[dict[str, str]]:
    payload = self._session.to_llm_payload()
    if recent_only is not None and len(payload) > recent_only:
      payload = payload[-recent_only:]
    if max_content_chars is not None and max_content_chars > 0:
      trimmed: list[dict[str, str]] = []
      for item in payload:
        content = item.get("content", "")
        if len(content) > max_content_chars:
          content = content[: max_content_chars - 3] + "..."
        trimmed.append({"role": item["role"], "content": content})
      payload = trimmed
    if not system_prompt:
      return payload
    return [{"role": "system", "content": system_prompt}, *payload]

  def get_history(self) -> list[Message]:
    return self._session.get_messages()

  def list_conversations(self) -> list[Conversation]:
    return self._repo.list_conversations()

  def new_conversation(self) -> Conversation:
    self._conversation = self._repo.create_conversation("New chat")
    self._session.clear()
    return self._conversation

  def open_conversation(self, conversation_id: str) -> Conversation:
    conversation = self._repo.get_conversation(conversation_id)
    if conversation is None:
      raise ConversationNotFoundError(f"Conversation not found: {conversation_id}")
    self._conversation = conversation
    self._session.load(self._repo.get_messages(conversation_id))
    return conversation

  def get_active_conversation(self) -> Conversation:
    return self._conversation
