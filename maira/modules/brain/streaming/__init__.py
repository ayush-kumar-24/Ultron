"""Token streaming pipeline from Ollama to UI/event bus subscribers."""

from maira.core.bus.event_bus import EventBus

TOPIC_TOKEN = "brain.token"
TOPIC_COMPLETE = "brain.complete"
TOPIC_ERROR = "brain.error"
TOPIC_CONTEXT = "brain.context"


class TokenStreamer:
  def __init__(self, event_bus: EventBus) -> None:
    self._event_bus = event_bus

  def publish_token(self, token: str) -> None:
    self._event_bus.publish(TOPIC_TOKEN, {"token": token})

  def publish_complete(self, full_text: str) -> None:
    self._event_bus.publish(TOPIC_COMPLETE, {"content": full_text})

  def publish_error(self, message: str) -> None:
    self._event_bus.publish(TOPIC_ERROR, {"message": message})

  def publish_context(self, payload: dict) -> None:
    self._event_bus.publish(TOPIC_CONTEXT, payload)
