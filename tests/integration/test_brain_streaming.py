"""Integration tests for brain streaming with Ollama."""

import pytest

from maira.app.settings import load_settings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.modules.brain.service import BrainService
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN


@pytest.fixture
def ollama_client() -> OllamaClient:
  settings = load_settings()
  return OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
  )


@pytest.mark.integration
def test_brain_streaming_with_ollama(ollama_client: OllamaClient) -> None:
  if not ollama_client.is_available():
    pytest.skip("Ollama is not running")

  models = ollama_client.list_models()
  settings = load_settings()
  configured = settings.ollama.model
  if not any(name == configured or name.startswith(f"{configured}:") for name in models):
    pytest.skip(f"Model {configured} is not installed")

  bus = EventBus()
  tokens: list[str] = []
  completed: list[str] = []

  bus.subscribe(TOPIC_TOKEN, lambda p: tokens.append(p["token"]))
  bus.subscribe(TOPIC_COMPLETE, lambda p: completed.append(p["content"]))

  brain = BrainService(ollama_client, bus)
  brain.send_message("Reply with exactly the word: pong")

  assert tokens
  assert completed
  assert brain.get_history()[-1].role.value == "assistant"
