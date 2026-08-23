"""Chat controller — sends user input to Brain, streams tokens to the view."""

from PySide6.QtCore import QObject, Qt, Signal, Slot

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.brain import Brain
from maira.modules.brain.streaming import (
  TOPIC_COMPLETE,
  TOPIC_CONTEXT,
  TOPIC_ERROR,
  TOPIC_TOKEN,
)
from maira.shared.utils.async_bridge import run_in_thread
from maira.shared.utils.latency import begin_trace, clear_trace, current_trace
from maira.ui.views.chat import ChatView


class ChatController(QObject):
  """Bridges Brain event-bus tokens to the ChatView on the UI thread."""

  _token = Signal(str)
  _complete = Signal(str)
  _error = Signal(str)
  _context = Signal(object)

  def __init__(
    self,
    brain: Brain,
    event_bus: EventBus,
    view: ChatView,
    *,
    show_context_debug: bool = False,
    model_name: str = "",
  ) -> None:
    super().__init__()
    self._brain = brain
    self._view = view
    self._busy = False
    self._last_user_text = ""
    self._model_name = model_name

    event_bus.subscribe(TOPIC_TOKEN, self._on_token_event)
    event_bus.subscribe(TOPIC_COMPLETE, self._on_complete_event)
    event_bus.subscribe(TOPIC_ERROR, self._on_error_event)
    event_bus.subscribe(TOPIC_CONTEXT, self._on_context_event)

    queued = Qt.ConnectionType.QueuedConnection
    self._token.connect(self._handle_token, queued)
    self._complete.connect(self._handle_complete, queued)
    self._error.connect(self._handle_error, queued)
    self._context.connect(self._handle_context, queued)

    view.send_requested.connect(self.send_message)
    view.new_chat_requested.connect(self.start_new_chat)
    view.conversation_selected.connect(self.open_conversation)
    view.retry_requested.connect(self.retry_last)
    view.set_context_debug_visible(show_context_debug)

    self._hydrate_view()

  def _refresh_history_list(self) -> None:
    active = self._brain.get_active_conversation()
    self._view.set_conversation_list(self._brain.list_conversations(), active.id)

  def _show_active_conversation(self) -> None:
    conversation = self._brain.get_active_conversation()
    self._view.hide_error()
    self._view.set_header(conversation.title)
    self._view.load_history(self._brain.get_history())
    self._refresh_history_list()

  def _hydrate_view(self) -> None:
    self._show_active_conversation()

  def _on_token_event(self, payload: dict) -> None:
    self._token.emit(str(payload.get("token", "")))

  def _on_complete_event(self, payload: dict) -> None:
    self._complete.emit(str(payload.get("content", "")))

  def _on_error_event(self, payload: dict) -> None:
    self._error.emit(str(payload.get("message", "Unknown error")))

  def _on_context_event(self, payload: dict) -> None:
    self._context.emit(payload)

  @Slot(str)
  def send_message(self, text: str) -> None:
    if self._busy:
      return

    cleaned = text.strip()
    if not cleaned:
      return

    self._last_user_text = cleaned
    begin_trace(model=self._model_name).mark("controller_received")

    self._view.hide_error()
    self._view.add_user_message(cleaned)
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
    self.send_message(self._last_user_text)

  @Slot()
  def start_new_chat(self) -> None:
    if self._busy:
      return
    conversation = self._brain.new_conversation()
    self._view.hide_error()
    self._view.clear_messages()
    self._view.set_header(conversation.title)
    self._view.set_context_debug([], 0)
    self._refresh_history_list()

  @Slot(str)
  def open_conversation(self, conversation_id: str) -> None:
    if self._busy:
      return
    active = self._brain.get_active_conversation()
    if conversation_id == active.id:
      return
    self._brain.open_conversation(conversation_id)
    self._show_active_conversation()

  @Slot(str)
  def _on_worker_finished(self, error: str) -> None:
    if error:
      self._view.show_error(error)
      self._view.complete_assistant_message()
    else:
      conversation = self._brain.get_active_conversation()
      self._view.set_header(conversation.title)
      self._refresh_history_list()
    self._busy = False
    self._view.set_input_enabled(True)
    clear_trace()

  @Slot(str)
  def _handle_token(self, token: str) -> None:
    if token:
      trace = current_trace()
      if trace is not None:
        trace.mark("ui_first_token")
      self._view.append_assistant_token(token)

  @Slot(str)
  def _handle_complete(self, _content: str) -> None:
    trace = current_trace()
    if trace is not None:
      trace.mark("ui_complete")
    self._view.complete_assistant_message()

  @Slot(str)
  def _handle_error(self, message: str) -> None:
    self._view.show_error(message)
    self._view.complete_assistant_message()

  @Slot(object)
  def _handle_context(self, payload: object) -> None:
    data = payload if isinstance(payload, dict) else {}
    titles = [str(item) for item in data.get("memory_titles", [])]
    char_count = int(data.get("char_count", 0) or 0)
    self._view.set_context_debug(titles, char_count)
