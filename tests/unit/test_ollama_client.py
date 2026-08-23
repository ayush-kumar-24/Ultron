"""Unit tests for Ollama client."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from maira.core.exceptions import LLMUnavailableError
from maira.infrastructure.llm.ollama.client import OLLAMA_UNAVAILABLE_USER_MESSAGE, OllamaClient


def test_is_available_false_on_connection_error() -> None:
  client = OllamaClient("http://127.0.0.1:9", "test")
  with patch.object(client._client, "get", side_effect=httpx.ConnectError("down")):
    assert client.is_available(force=True) is False
  client.close()


def test_is_available_true_on_200() -> None:
  client = OllamaClient("http://127.0.0.1:11434", "test")
  response = MagicMock(status_code=200)
  with patch.object(client._client, "get", return_value=response):
    assert client.is_available(force=True) is True
  client.close()


def test_is_available_uses_cache() -> None:
  client = OllamaClient("http://127.0.0.1:11434", "test", availability_cache_seconds=60)
  response = MagicMock(status_code=200)
  mock_get = MagicMock(return_value=response)
  with patch.object(client._client, "get", mock_get):
    assert client.is_available(force=True) is True
    assert client.is_available() is True
  assert mock_get.call_count == 1
  client.close()


def test_list_models_raises_when_unreachable() -> None:
  client = OllamaClient("http://127.0.0.1:9", "test")
  with patch.object(client._client, "get", side_effect=httpx.ConnectError("down")):
    with pytest.raises(LLMUnavailableError, match="can't reach"):
      client.list_models()
  client.close()


def test_list_models_parses_names() -> None:
  client = OllamaClient("http://127.0.0.1:11434", "test")
  response = MagicMock()
  response.json.return_value = {"models": [{"name": "llama3.2"}, {"name": "mistral"}]}
  response.raise_for_status = MagicMock()
  with patch.object(client._client, "get", return_value=response):
    assert client.list_models() == ["llama3.2", "mistral"]
  client.close()


def test_chat_stream_yields_tokens_and_reuses_client() -> None:
  client = OllamaClient("http://127.0.0.1:11434", "llama3.2:latest")
  lines = [
    json.dumps({"message": {"content": "Hello"}, "done": False}),
    json.dumps({"message": {"content": " world"}, "done": False}),
    json.dumps({"done": True}),
  ]

  mock_response = MagicMock()
  mock_response.iter_lines.return_value = iter(lines)
  mock_response.raise_for_status = MagicMock()
  mock_response.__enter__ = MagicMock(return_value=mock_response)
  mock_response.__exit__ = MagicMock(return_value=False)

  with patch.object(client._client, "stream", return_value=mock_response) as mock_stream:
    tokens = list(client.chat_stream([{"role": "user", "content": "Hi"}]))
    body = mock_stream.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:latest"
    assert body["stream"] is True
    assert body["keep_alive"] == "30m"

  assert tokens == ["Hello", " world"]
  client.close()


def test_chat_stream_maps_errors_to_user_message() -> None:
  client = OllamaClient("http://127.0.0.1:9", "test")
  with patch.object(client._client, "stream", side_effect=httpx.ConnectError("down")):
    with pytest.raises(LLMUnavailableError) as exc:
      list(client.chat_stream([{"role": "user", "content": "Hi"}]))
  assert str(exc.value) == OLLAMA_UNAVAILABLE_USER_MESSAGE
  client.close()
