"""Brain port — LLM reasoning, context assembly, and response streaming."""

from abc import ABC, abstractmethod

from maira.core.domain.entities import Conversation, Message


class Brain(ABC):
  @abstractmethod
  def send_message(self, text: str) -> None:
    """Process a user message and stream the assistant response via the event bus."""

  @abstractmethod
  def get_history(self) -> list[Message]:
    """Return the active conversation history."""

  @abstractmethod
  def list_conversations(self) -> list[Conversation]:
    """Return all conversations, newest first."""

  @abstractmethod
  def new_conversation(self) -> Conversation:
    """Start a fresh conversation and return it."""

  @abstractmethod
  def open_conversation(self, conversation_id: str) -> Conversation:
    """Switch the active session to an existing conversation."""

  @abstractmethod
  def get_active_conversation(self) -> Conversation:
    """Return metadata for the active conversation."""
