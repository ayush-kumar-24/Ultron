"""Ollama API adapter implementing the LLM port."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from maira.core.exceptions import LLMStreamError, LLMUnavailableError
from maira.core.interfaces.llm import LLMProvider

OLLAMA_UNAVAILABLE_USER_MESSAGE = "Ultron can't reach the local AI model."


class OllamaClient(LLMProvider):
  """Reusable HTTP session against a running Ollama service (never spawns ollama.exe)."""

  def __init__(
    self,
    host: str,
    model: str,
    timeout_seconds: float = 120.0,
    *,
    keep_alive: str = "30m",
    availability_cache_seconds: float = 15.0,
  ) -> None:
    self._host = host.rstrip("/")
    self._model = model
    self._timeout = timeout_seconds
    self._keep_alive = keep_alive
    self._availability_cache_seconds = availability_cache_seconds
    self._client = httpx.Client(
      base_url=self._host,
      timeout=httpx.Timeout(timeout_seconds, connect=5.0),
    )
    self._available_cached_at: float | None = None
    self._available_cached_value: bool | None = None

  @property
  def model(self) -> str:
    return self._model

  @property
  def host(self) -> str:
    return self._host

  def close(self) -> None:
    self._client.close()

  def is_available(self, *, force: bool = False) -> bool:
    now = time.perf_counter()
    if (
      not force
      and self._available_cached_value is not None
      and self._available_cached_at is not None
      and (now - self._available_cached_at) < self._availability_cache_seconds
    ):
      return self._available_cached_value

    try:
      response = self._client.get("/api/tags", timeout=5.0)
      ok = response.status_code == 200
    except httpx.HTTPError:
      ok = False

    self._available_cached_value = ok
    self._available_cached_at = now
    return ok

  def list_models(self) -> list[str]:
    try:
      response = self._client.get("/api/tags")
      response.raise_for_status()
    except httpx.HTTPError as exc:
      raise LLMUnavailableError(OLLAMA_UNAVAILABLE_USER_MESSAGE) from exc

    payload = response.json()
    models = payload.get("models", [])
    return [str(item.get("name", "")) for item in models if item.get("name")]

  def chat_stream(
    self,
    messages: Sequence[dict[str, str]],
    *,
    options: dict[str, Any] | None = None,
  ) -> Iterator[str]:
    body: dict[str, Any] = {
      "model": self._model,
      "messages": list(messages),
      "stream": True,
      "keep_alive": self._keep_alive,
    }
    if options:
      body["options"] = options

    try:
      with self._client.stream("POST", "/api/chat", json=body) as response:
        response.raise_for_status()
        self._available_cached_value = True
        self._available_cached_at = time.perf_counter()
        for line in response.iter_lines():
          token = self._parse_stream_line(line)
          if token is not None:
            yield token
    except httpx.HTTPError as exc:
      self._available_cached_value = False
      self._available_cached_at = time.perf_counter()
      raise LLMUnavailableError(OLLAMA_UNAVAILABLE_USER_MESSAGE) from exc

  def _parse_stream_line(self, line: str) -> str | None:
    if not line:
      return None
    try:
      payload: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError as exc:
      raise LLMStreamError("Invalid JSON from Ollama stream") from exc

    if payload.get("done"):
      return None

    message = payload.get("message", {})
    content = message.get("content")
    if content:
      return str(content)
    return None
