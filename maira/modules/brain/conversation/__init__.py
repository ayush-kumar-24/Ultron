"""Conversation session management — turns, roles, and in-memory history."""

from maira.core.domain.entities import Message
from maira.core.domain.value_objects import MessageRole


class ConversationSession:
  """In-memory conversation for a single chat session."""

  def __init__(self) -> None:
    self._messages: list[Message] = []

  def load(self, messages: list[Message]) -> None:
    self._messages = list(messages)

  def add_user_message(self, text: str) -> Message:
    message = Message(role=MessageRole.USER, content=text)
    self._messages.append(message)
    return message

  def add_assistant_message(self, text: str) -> Message:
    message = Message(role=MessageRole.ASSISTANT, content=text)
    self._messages.append(message)
    return message

  def discard_last_user_message(self) -> None:
    if self._messages and self._messages[-1].role == MessageRole.USER:
      self._messages.pop()

  def get_messages(self) -> list[Message]:
    return list(self._messages)

  def to_llm_payload(self) -> list[dict[str, str]]:
    return [message.to_llm_dict() for message in self._messages]

  def clear(self) -> None:
    self._messages.clear()
