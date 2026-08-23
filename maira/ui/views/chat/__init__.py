"""Chat view — history sidebar, message list, and streaming response display."""

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QListWidgetItem,
  QPushButton,
  QScrollArea,
  QSizePolicy,
  QVBoxLayout,
  QWidget,
)

from maira.core.domain.entities import Conversation, Message
from maira.core.domain.value_objects import MessageRole
from maira.ui.widgets.streaming_label import StreamingLabel


def _format_updated_at(value: datetime) -> str:
  if value.tzinfo is None:
    value = value.replace(tzinfo=timezone.utc)
  local = value.astimezone()
  now = datetime.now(local.tzinfo)
  if local.date() == now.date():
    return local.strftime("%H:%M")
  if local.year == now.year:
    return local.strftime("%d %b")
  return local.strftime("%d %b %Y")


class ChatView(QWidget):
  send_requested = Signal(str)
  new_chat_requested = Signal()
  conversation_selected = Signal(str)
  retry_requested = Signal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self._streaming_label: StreamingLabel | None = None
    self._updating_history = False
    self._build_ui()

  def _build_ui(self) -> None:
    root = QHBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self._history_panel = QWidget()
    self._history_panel.setObjectName("chatHistoryPanel")
    self._history_panel.setFixedWidth(240)
    history_layout = QVBoxLayout(self._history_panel)
    history_layout.setContentsMargins(12, 12, 12, 12)
    history_layout.setSpacing(8)

    history_title = QLabel("History")
    history_title.setObjectName("historyTitle")
    history_layout.addWidget(history_title)

    self._history_list = QListWidget()
    self._history_list.setObjectName("chatHistoryList")
    self._history_list.currentItemChanged.connect(self._on_history_item_changed)
    history_layout.addWidget(self._history_list, stretch=1)

    root.addWidget(self._history_panel)

    chat_panel = QWidget()
    chat_layout = QVBoxLayout(chat_panel)
    chat_layout.setContentsMargins(16, 16, 16, 16)
    chat_layout.setSpacing(12)

    header = QHBoxLayout()
    self._history_toggle = QPushButton("Hide history")
    self._history_toggle.setObjectName("historyToggleButton")
    self._history_toggle.setCheckable(True)
    self._history_toggle.setChecked(True)
    self._history_toggle.setToolTip("Show or hide chat history")
    self._history_toggle.toggled.connect(self._on_history_toggled)
    header.addWidget(self._history_toggle)

    self._header_label = QLabel("New chat")
    self._header_label.setObjectName("chatHeader")
    header.addWidget(self._header_label, stretch=1)

    self._new_chat_button = QPushButton("New chat")
    self._new_chat_button.setObjectName("newChatButton")
    self._new_chat_button.clicked.connect(self.new_chat_requested.emit)
    header.addWidget(self._new_chat_button)

    self._context_toggle = QPushButton("Context")
    self._context_toggle.setObjectName("contextToggleButton")
    self._context_toggle.setCheckable(True)
    self._context_toggle.setToolTip("Show memories injected into the AI prompt")
    self._context_toggle.toggled.connect(self._on_context_toggled)
    header.addWidget(self._context_toggle)
    chat_layout.addLayout(header)

    self._error_banner = QLabel()
    self._error_banner.setObjectName("errorBanner")
    self._error_banner.setWordWrap(True)
    self._error_banner.hide()

    self._retry_button = QPushButton("Retry")
    self._retry_button.hide()
    self._retry_button.clicked.connect(self.retry_requested.emit)

    error_row = QHBoxLayout()
    error_row.addWidget(self._error_banner, stretch=1)
    error_row.addWidget(self._retry_button)
    chat_layout.addLayout(error_row)

    self._context_panel = QLabel("No memories injected yet.")
    self._context_panel.setObjectName("contextDebugPanel")
    self._context_panel.setWordWrap(True)
    self._context_panel.hide()
    chat_layout.addWidget(self._context_panel)

    self._scroll = QScrollArea()
    self._scroll.setWidgetResizable(True)
    self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    self._message_host = QWidget()
    self._message_layout = QVBoxLayout(self._message_host)
    self._message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    self._message_layout.setSpacing(10)
    self._scroll.setWidget(self._message_host)
    chat_layout.addWidget(self._scroll, stretch=1)

    input_row = QHBoxLayout()
    self._input = QLineEdit()
    self._input.setPlaceholderText("Message Maira…")
    self._input.returnPressed.connect(self._on_send)
    input_row.addWidget(self._input, stretch=1)

    self._send_button = QPushButton("Send")
    self._send_button.clicked.connect(self._on_send)
    input_row.addWidget(self._send_button)

    chat_layout.addLayout(input_row)
    root.addWidget(chat_panel, stretch=1)

  def _on_history_toggled(self, visible: bool) -> None:
    self._history_panel.setVisible(visible)
    self._history_toggle.setText("Hide history" if visible else "Show history")

  def _on_context_toggled(self, visible: bool) -> None:
    self._context_panel.setVisible(visible)

  def set_context_debug_visible(self, visible: bool) -> None:
    self._context_toggle.blockSignals(True)
    self._context_toggle.setChecked(visible)
    self._context_toggle.blockSignals(False)
    self._context_panel.setVisible(visible)

  def set_context_debug(self, titles: list[str], char_count: int = 0) -> None:
    if not titles:
      self._context_panel.setText("No memories injected for this message.")
      return
    lines = "\n".join(f"• {title}" for title in titles)
    self._context_panel.setText(
      f"Injected memories ({char_count} chars):\n{lines}"
    )

  def _on_send(self) -> None:
    text = self._input.text().strip()
    if not text:
      return
    self._input.clear()
    self.send_requested.emit(text)

  def _on_history_item_changed(
    self,
    current: QListWidgetItem | None,
    _previous: QListWidgetItem | None,
  ) -> None:
    if self._updating_history or current is None:
      return
    conversation_id = current.data(Qt.ItemDataRole.UserRole)
    if conversation_id:
      self.conversation_selected.emit(str(conversation_id))

  def show_error(self, message: str) -> None:
    self._error_banner.setText(message)
    self._error_banner.show()
    self._retry_button.show()

  def hide_error(self) -> None:
    self._error_banner.hide()
    self._retry_button.hide()

  def set_header(self, title: str) -> None:
    self._header_label.setText(title)

  def set_conversation_list(
    self,
    conversations: list[Conversation],
    active_id: str | None,
  ) -> None:
    self._updating_history = True
    self._history_list.clear()
    active_row = -1
    for index, conversation in enumerate(conversations):
      stamp = _format_updated_at(conversation.updated_at)
      item = QListWidgetItem(f"{conversation.title}\n{stamp}")
      item.setData(Qt.ItemDataRole.UserRole, conversation.id)
      item.setToolTip(conversation.title)
      self._history_list.addItem(item)
      if conversation.id == active_id:
        active_row = index
    if active_row >= 0:
      self._history_list.setCurrentRow(active_row)
    self._updating_history = False

  def clear_messages(self) -> None:
    while self._message_layout.count():
      item = self._message_layout.takeAt(0)
      widget = item.widget()
      if widget is not None:
        widget.deleteLater()
    self._streaming_label = None

  def load_history(self, messages: list[Message]) -> None:
    self.clear_messages()
    for message in messages:
      if message.role == MessageRole.USER:
        self.add_user_message(message.content)
      elif message.role == MessageRole.ASSISTANT:
        self.add_assistant_message(message.content)
    self._scroll_to_bottom()

  def add_user_message(self, text: str) -> None:
    label = QLabel(text)
    label.setObjectName("userBubble")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    self._message_layout.addWidget(label)
    self._scroll_to_bottom()

  def add_assistant_message(self, text: str) -> None:
    label = QLabel(text)
    label.setObjectName("assistantBubble")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    self._message_layout.addWidget(label)
    self._scroll_to_bottom()

  def begin_assistant_message(self) -> StreamingLabel:
    self._streaming_label = StreamingLabel()
    self._streaming_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    self._message_layout.addWidget(self._streaming_label)
    self._scroll_to_bottom()
    return self._streaming_label

  def append_assistant_token(self, token: str) -> None:
    if self._streaming_label is None:
      self._streaming_label = self.begin_assistant_message()
    self._streaming_label.append_token(token)
    self._scroll_to_bottom()

  def complete_assistant_message(self) -> None:
    if self._streaming_label is not None:
      self._streaming_label.set_complete()
    self._streaming_label = None
    self._scroll_to_bottom()

  def set_input_enabled(self, enabled: bool) -> None:
    self._input.setEnabled(enabled)
    self._send_button.setEnabled(enabled)
    self._new_chat_button.setEnabled(enabled)
    self._history_list.setEnabled(enabled)

  def _scroll_to_bottom(self) -> None:
    bar = self._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
