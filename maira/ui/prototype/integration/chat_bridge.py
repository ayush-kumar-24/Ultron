"""Bridge: prototype ChatScreen ↔ BrainService (real streaming)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot

from maira.core.bus.event_bus import EventBus
from maira.core.domain.value_objects import MessageRole
from maira.core.interfaces.brain import Brain
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_ERROR, TOPIC_TOKEN
from maira.shared.utils.async_bridge import run_in_thread
from maira.shared.utils.latency import begin_trace, clear_trace, current_trace
from maira.ui.prototype.screens.chat import ChatScreen


class ProtoChatBridge(QObject):
  _token = Signal(str)
  _complete = Signal(str)
  _error = Signal(str)

  def __init__(
    self,
    brain: Brain,
    event_bus: EventBus,
    view: ChatScreen,
    *,
    model_name: str = "",
  ) -> None:
    super().__init__()
    self._brain = brain
    self._view = view
    self._busy = False
    self._last_user_text = ""
    self._last_prompt = ""
    self._model_name = model_name

    view.set_live_mode(True)
    view.send_requested.connect(self.send_message)
    view.new_chat_requested.connect(self.start_new_chat)
    if hasattr(view, "error") and hasattr(view.error, "retry"):
      view.error.retry.connect(self.retry_last)

    event_bus.subscribe(TOPIC_TOKEN, self._on_token_event)
    event_bus.subscribe(TOPIC_COMPLETE, self._on_complete_event)
    event_bus.subscribe(TOPIC_ERROR, self._on_error_event)

    queued = Qt.ConnectionType.QueuedConnection
    self._token.connect(self._handle_token, queued)
    self._complete.connect(self._handle_complete, queued)
    self._error.connect(self._handle_error, queued)

    self._hydrate()

  def _hydrate(self) -> None:
    conversation = self._brain.get_active_conversation()
    history = []
    for msg in self._brain.get_history():
      role = "user" if msg.role == MessageRole.USER else "assistant"
      if msg.role == MessageRole.SYSTEM:
        continue
      history.append({"role": role, "content": msg.content})
    self._view.load_history(history, title=conversation.title)

  def send_message(self, display: str, prompt: str = "") -> None:
    if self._busy or self._view.voice_mode:
      return
    shown = display.strip()
    cleaned = (prompt or display).strip()
    if not cleaned:
      return

    self._last_user_text = shown
    self._last_prompt = cleaned
    begin_trace(model=self._model_name).mark("controller_received")

    self._view.hide_error()
    self._view.add_user_message(shown)
    self._view.begin_assistant_message()
    self._busy = True
    self._view.set_input_enabled(False)

    thread = run_in_thread(self, lambda: self._brain.send_message(cleaned))
    worker = thread._maira_worker  # type: ignore[attr-defined]
    worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)

  @Slot()
  def retry_last(self) -> None:
    if self._busy or not self._last_user_text:
      return
    self.send_message(self._last_user_text, self._last_prompt)

  @Slot()
  def start_new_chat(self) -> None:
    if self._busy:
      return
    conversation = self._brain.new_conversation()
    self._view.clear_messages()
    self._view.set_header(conversation.title)
    self._view.hide_error()

  def _on_token_event(self, payload: dict) -> None:
    self._token.emit(str(payload.get("token", "")))

  def _on_complete_event(self, payload: dict) -> None:
    self._complete.emit(str(payload.get("content", "")))

  def _on_error_event(self, payload: dict) -> None:
    self._error.emit(str(payload.get("message", "Unknown error")))

  @Slot(str)
  def _on_worker_finished(self, error: str) -> None:
    if error:
      self._view.show_error(error)
      self._view.complete_assistant_message()
    else:
      conversation = self._brain.get_active_conversation()
      self._view.set_header(conversation.title)
    self._busy = False
    self._view.set_input_enabled(True)
    clear_trace()

  @Slot(str)
  def _handle_token(self, token: str) -> None:
    if self._view.voice_mode:
      return
    if token:
      trace = current_trace()
      if trace is not None:
        trace.mark("ui_first_token")
      self._view.append_assistant_token(token)

  @Slot(str)
  def _handle_complete(self, _content: str) -> None:
    if self._view.voice_mode:
      return
    trace = current_trace()
    if trace is not None:
      trace.mark("ui_complete")
    self._view.complete_assistant_message()

  @Slot(str)
  def _handle_error(self, message: str) -> None:
    self._view.show_error(message)
    if not self._view.voice_mode:
      self._view.complete_assistant_message()
