"""Chat screen — default workspace with inline voice; mock or live Brain."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QPushButton,
  QScrollArea,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from maira.shared.utils.attachments import visible_text
from maira.ui.prototype.components.command_input import CommandInput
from maira.ui.prototype.components.maira_logo import MairaLogo
from maira.ui.prototype.components.primitives import ErrorBanner, PageHeader
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.theme import tokens as t


class ChatBubble(QFrame):
  _USER_MAX_WIDTH = 560
  _ASSISTANT_MAX_WIDTH = 680
  _MARGIN_H = 14
  _SPACING = 12

  def __init__(self, role: str, content: str, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("Card" if role == "assistant" else "ElevatedCard")
    layout = QHBoxLayout(self)
    layout.setContentsMargins(self._MARGIN_H, 12, self._MARGIN_H, 12)
    layout.setSpacing(self._SPACING)

    logo_space = 0
    if role == "assistant":
      logo = MairaLogo(size="small", glowing=False)
      layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignTop)
      logo_space = max(logo.sizeHint().width(), logo.minimumWidth()) + self._SPACING

    col = QVBoxLayout()
    if role == "assistant":
      name = QLabel("Ultron")
      name.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px;")
      col.addWidget(name)
    self.body = QLabel(visible_text(content) if role == "user" else content)
    self.body.setWordWrap(True)
    self.body.setTextFormat(Qt.TextFormat.PlainText)
    self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    self.body.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 14px; line-height: 1.45;")
    col.addWidget(self.body)
    layout.addLayout(col, stretch=1)

    if role == "user":
      self.setMaximumWidth(self._USER_MAX_WIDTH)
      self._max_text_width = self._USER_MAX_WIDTH - 2 * self._MARGIN_H
    else:
      self.setMaximumWidth(self._ASSISTANT_MAX_WIDTH)
      self._max_text_width = self._ASSISTANT_MAX_WIDTH - 2 * self._MARGIN_H - logo_space
    self._fit_text()

  def set_content(self, text: str) -> None:
    self.body.setText(text)
    self._fit_text()

  def append_content(self, token: str) -> None:
    self.body.setText(self.body.text() + token)
    self._fit_text()

  def _fit_text(self) -> None:
    # A word-wrapped QLabel in an aligned layout gets its one-line size hint,
    # which clips long messages. Size the label from its text instead.
    self.body.ensurePolished()
    metrics = self.body.fontMetrics()
    lines = self.body.text().split("\n") or [""]
    natural = max(metrics.horizontalAdvance(line) for line in lines) + 2
    width = max(1, min(natural, self._max_text_width))
    self.body.setFixedWidth(width)
    self.body.setFixedHeight(self.body.heightForWidth(width))


class VoiceStage(QWidget):
  """Inline voice stage — hovering logo inside Chat."""

  DEFAULT_HINT = "Bolo — aap rukoge toh Ultron jawab dega · Esc ya 〰 button se band karo"

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    layout = QVBoxLayout(self)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setSpacing(18)

    self.logo = MairaLogo(size="hero", glowing=True, animated=True, hovering=True)
    layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignCenter)

    self.status = QLabel("Listening...")
    self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.status.setStyleSheet(
      f"color: {t.TEXT_HEADING}; font-size: 18px; font-weight: 500; letter-spacing: 0.2px;"
    )
    layout.addWidget(self.status)

    self.you = QLabel("")
    self.you.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.you.setWordWrap(True)
    self.you.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 14px;")
    # Full width (no alignment flag): wrapped labels in aligned slots get clipped.
    layout.addWidget(self.you)

    self.reply = QLabel("")
    self.reply.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.reply.setWordWrap(True)
    self.reply.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 15px;")
    # Full width (no alignment flag): wrapped labels in aligned slots get clipped.
    layout.addWidget(self.reply)

    self.hint = QLabel(self.DEFAULT_HINT)
    self.hint.setObjectName("Muted")
    self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(self.hint)

  def reset(self) -> None:
    self.you.setText("")
    self.reply.setText("")
    self.hint.setText(self.DEFAULT_HINT)
    self.set_state("Starting…")

  def set_transcript(self, text: str) -> None:
    self.you.setText(f"Aap: {text}" if text else "")
    self.reply.setText("")

  def set_reply(self, text: str) -> None:
    self.reply.setText(text)

  def set_state(self, state: str) -> None:
    self.status.setText(state)
    active = state.startswith(("Listening", "Speaking", "Processing"))
    self.logo.set_hovering(True)
    self.logo.set_glowing(True)
    self.logo.set_intensity(0.95 if active else 0.45)


class ChatScreen(QWidget):
  send_requested = Signal(str, str)
  new_chat_requested = Signal()
  voice_toggled = Signal(bool)
  voice_listen_start = Signal()
  voice_listen_stop = Signal()
  voice_cancel = Signal()
  dictate_start = Signal()
  dictate_stop = Signal()

  def __init__(self, store: MockStore | None = None, parent=None) -> None:
    super().__init__(parent)
    self.store = store or MockStore()
    self._live = False
    self._voice_backend = False
    self._auto_conversation = False
    self._streaming = False
    self._stream_full = ""
    self._stream_pos = 0
    self._assistant_bubble: ChatBubble | None = None
    self._voice_mode = False
    self._voice_listening = False
    self._dictating = False
    self._llm_hint_shown = False

    root = QVBoxLayout(self)
    root.setContentsMargins(28, 24, 28, 16)
    root.setSpacing(12)

    header_row = QHBoxLayout()
    self.header = PageHeader("Chat", "Private conversation with Ultron")
    self._title_label = self.header.findChildren(QLabel)[0]
    header_row.addWidget(self.header)
    header_row.addStretch(1)
    self.new_chat_btn = QPushButton("New chat")
    self.new_chat_btn.setObjectName("GhostButton")
    self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
    header_row.addWidget(self.new_chat_btn)
    root.addLayout(header_row)

    self.error = ErrorBanner()
    self.error.retry.connect(self.hide_error)
    root.addWidget(self.error)

    self.stage = QStackedWidget()

    self.chat_page = QWidget()
    chat_layout = QVBoxLayout(self.chat_page)
    chat_layout.setContentsMargins(0, 0, 0, 0)
    chat_layout.setSpacing(8)

    self.scroll = QScrollArea()
    self.scroll.setWidgetResizable(True)
    self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.thread = QWidget()
    self.thread_layout = QVBoxLayout(self.thread)
    self.thread_layout.setContentsMargins(0, 0, 8, 0)
    self.thread_layout.setSpacing(12)
    self.thread_layout.addStretch(1)
    self.scroll.setWidget(self.thread)
    chat_layout.addWidget(self.scroll, stretch=1)

    self.thinking = QLabel("Ultron is thinking...")
    self.thinking.setObjectName("Muted")
    self.thinking.hide()
    chat_layout.addWidget(self.thinking)

    self.voice_stage = VoiceStage()
    self.voice_page = QWidget()
    voice_layout = QVBoxLayout(self.voice_page)
    voice_layout.setContentsMargins(0, 0, 0, 0)
    voice_layout.addWidget(self.voice_stage)

    self.stage.addWidget(self.chat_page)
    self.stage.addWidget(self.voice_page)
    root.addWidget(self.stage, stretch=1)

    self.input = CommandInput(compact=True)
    self.input.set_placeholder("Message Ultron...")
    self.input.submitted.connect(self._on_submit)
    self.input.voice_clicked.connect(self._on_mic)
    self.input.talk_clicked.connect(self.toggle_voice_mode)
    self.input.notice.connect(self.store.toast.emit)
    root.addWidget(self.input)

    self._mock_timer = QTimer(self)
    self._mock_timer.timeout.connect(self._tick_mock_stream)

    if not self._live:
      self.reload_from_store()

  def set_live_mode(self, enabled: bool) -> None:
    self._live = enabled
    self.new_chat_btn.setVisible(enabled)

  def set_voice_backend(self, enabled: bool) -> None:
    self._voice_backend = enabled

  def set_auto_conversation(self, enabled: bool) -> None:
    self._auto_conversation = enabled

  def set_voice_unavailable(self, detail: str) -> None:
    self.voice_stage.hint.setText(detail)

  @property
  def voice_mode(self) -> bool:
    return self._voice_mode

  @property
  def dictating(self) -> bool:
    return self._dictating

  def set_header(self, title: str) -> None:
    self._title_label.setText(title or "Chat")

  def set_input_enabled(self, enabled: bool) -> None:
    self.input.editor.setEnabled(enabled)
    self.input.send_btn.setEnabled(enabled)

  def hide_error(self) -> None:
    self.error.hide()

  def show_error(self, title: str, body: str | None = None) -> None:
    if body is None:
      self.error.show_error("Ultron hit a problem.", title)
    else:
      self.error.show_error(title, body)

  def show_ollama_error(self) -> None:
    err = self.store.error_copy("ollama")
    self.error.show_error(err["title"], err["body"])

  def clear_messages(self) -> None:
    while self.thread_layout.count() > 1:
      item = self.thread_layout.takeAt(0)
      if item.widget():
        item.widget().deleteLater()
    self._assistant_bubble = None

  def load_history(self, messages: list[dict], title: str = "Chat") -> None:
    self.clear_messages()
    self.set_header(title)
    for msg in messages:
      self._add_bubble(msg["role"], msg["content"])
    QTimer.singleShot(0, self._scroll_bottom)

  def add_user_message(self, text: str) -> None:
    self._add_bubble("user", text)
    self._scroll_bottom()

  def add_assistant_message(self, text: str) -> None:
    self._add_bubble("assistant", text)
    self._scroll_bottom()

  def begin_assistant_message(self) -> None:
    self.thinking.show()
    self._assistant_bubble = self._add_bubble("assistant", "")
    self._scroll_bottom()

  def append_assistant_token(self, token: str) -> None:
    if self._assistant_bubble is None:
      self.begin_assistant_message()
    assert self._assistant_bubble is not None
    if self.thinking.isVisible():
      self.thinking.hide()
    self._assistant_bubble.append_content(token)
    self._scroll_bottom()

  def complete_assistant_message(self) -> None:
    self.thinking.hide()
    self._assistant_bubble = None

  def _add_bubble(self, role: str, content: str) -> ChatBubble:
    bubble = ChatBubble(role, content)
    align = Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft
    self.thread_layout.insertWidget(self.thread_layout.count() - 1, bubble, alignment=align)
    return bubble

  def _scroll_bottom(self) -> None:
    bar = self.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())

  def _on_submit(self, display: str, prompt: str = "") -> None:
    text = display.strip()
    llm_text = (prompt or display).strip()
    if not llm_text:
      return
    if self._dictating:
      self.voice_cancel.emit()
    if self._voice_mode:
      self.set_voice_mode(False)
    if self._live:
      self.send_requested.emit(text, llm_text)
    else:
      self._mock_send(text)

  def _mock_send(self, text: str) -> None:
    if self._streaming:
      return
    if self.store.force_error == "ollama":
      self.show_ollama_error()
      return
    self.hide_error()
    self._streaming = True
    self.store.append_user_message(text)
    self.add_user_message(text)
    self.thinking.show()
    self._stream_full = self.store.next_stream_reply()
    self._stream_pos = 0
    self._assistant_bubble = self._add_bubble("assistant", "")
    self._mock_timer.start(18)

  def _tick_mock_stream(self) -> None:
    if self._stream_pos >= len(self._stream_full):
      self._mock_timer.stop()
      self.thinking.hide()
      self._streaming = False
      self.store.append_assistant_message(self._stream_full)
      self._assistant_bubble = None
      return
    self._stream_pos = min(len(self._stream_full), self._stream_pos + 2)
    if self._assistant_bubble is not None:
      self._assistant_bubble.set_content(self._stream_full[: self._stream_pos])
    self._scroll_bottom()

  def reload_from_store(self) -> None:
    history = [{"role": m["role"], "content": m["content"]} for m in self.store.conversation]
    self.load_history(history)

  def toggle_voice_mode(self) -> None:
    """Start or end the hands-free voice conversation."""
    self.set_voice_mode(not self._voice_mode)

  def set_voice_mode(self, enabled: bool) -> None:
    if enabled:
      if self._voice_mode:
        return
      if not self._voice_backend:
        self.store.toast.emit("Voice not ready yet")
        return
      if self._dictating:
        self.voice_cancel.emit()
        self.set_dictating(False)
      self._voice_mode = True
      self.voice_stage.reset()
      self.stage.setCurrentWidget(self.voice_page)
      self.input.talk_btn.set_active(True)
      self.input.set_placeholder("Voice conversation on — Esc to stop")
      self.voice_toggled.emit(True)
      return
    if self._dictating:
      self.voice_cancel.emit()
    if self._voice_mode:
      self._voice_mode = False
      self.voice_toggled.emit(False)
    self.stage.setCurrentWidget(self.chat_page)
    self.input.set_placeholder("Message Ultron...")
    self.input.mic_btn.set_active(False)
    self.input.talk_btn.set_active(False)
    self._dictating = False

  def toggle_dictation(self) -> None:
    if not self._voice_backend:
      self.store.toast.emit("Mic not ready yet")
      return
    if self._dictating:
      self.dictate_stop.emit()
    else:
      self.dictate_start.emit()

  def set_dictating(self, active: bool) -> None:
    self._dictating = active
    self.input.mic_btn.set_active(active)
    if active:
      self.input.set_placeholder("Listening… tap mic again when done")
    else:
      self.input.set_placeholder("Message Ultron...")

  def set_placeholder_listening(self, active: bool) -> None:
    if active:
      self.input.set_placeholder("Listening… tap mic again when done")

  def insert_dictation(self, text: str) -> None:
    self.input.append_text(text)

  def _on_mic(self) -> None:
    self.toggle_dictation()

  def set_voice_state(self, state: str) -> None:
    self.voice_stage.set_state(state)
    self._voice_listening = state.startswith("Listening")
    if state.startswith("Listening") and not self._voice_mode:
      self.set_dictating(True)
    elif state in ("Idle", "idle") and self._dictating and not self._voice_mode:
      pass
