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

  def chat_tools(
    self,
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
    options: dict[str, Any] | None = None,
    timeout: float = 600.0,
  ) -> dict[str, Any]:
    """One non-streaming turn that may call tools.

    Returns {"content": str, "tool_calls": [{"name": str, "arguments": dict}]}.
    Thinking is switched off: on a CPU it can add minutes per step.
    """
    body: dict[str, Any] = {
      "model": model or self._model,
      "messages": list(messages),
      "tools": list(tools),
      "stream": False,
      "keep_alive": self._keep_alive,
      "think": False,
    }
    if options:
      body["options"] = options
    try:
      response = self._client.post("/api/chat", json=body, timeout=httpx.Timeout(timeout, connect=5.0))
      if response.status_code == 400 and "think" in response.text.lower():
        body.pop("think")  # a model without a thinking switch
        response = self._client.post("/api/chat", json=body, timeout=httpx.Timeout(timeout, connect=5.0))
      if response.status_code in (400, 404):
        detail = _error_text(response)
        if "not found" in detail.lower():
          raise LLMStreamError(f'Model "{body["model"]}" is not installed. Run: ollama pull {body["model"]}')
        if "tool" in detail.lower():
          raise LLMStreamError(f'Model "{body["model"]}" cannot use tools. Try qwen3.5:4b or gemma4:e4b.')
        raise LLMStreamError(detail or "Ollama rejected the request")
      response.raise_for_status()
    except httpx.HTTPError as exc:
      self._available_cached_value = False
      self._available_cached_at = time.perf_counter()
      raise LLMUnavailableError(OLLAMA_UNAVAILABLE_USER_MESSAGE) from exc
    self._available_cached_value = True
    self._available_cached_at = time.perf_counter()
    message = response.json().get("message", {}) or {}
    content = str(message.get("content") or "")
    calls = [_normalize_call(c) for c in message.get("tool_calls") or []]
    calls = [c for c in calls if c is not None]
    if not calls:
      text_call = _call_from_text(content)
      if text_call is not None:
        calls, content = [text_call], ""
    return {"content": content, "tool_calls": calls}

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


def _error_text(response: httpx.Response) -> str:
  try:
    return str(response.json().get("error") or response.text)
  except ValueError:
    return response.text


def _normalize_call(raw: Any) -> dict[str, Any] | None:
  function = (raw or {}).get("function") if isinstance(raw, dict) else None
  if not isinstance(function, dict) or not function.get("name"):
    return None
  arguments = function.get("arguments") or {}
  if isinstance(arguments, str):
    try:
      arguments = json.loads(arguments)
    except json.JSONDecodeError:
      arguments = {}
  return {"name": str(function["name"]), "arguments": arguments if isinstance(arguments, dict) else {}}


def _call_from_text(content: str) -> dict[str, Any] | None:
  """Small models sometimes write the call as JSON text instead of a real tool call."""
  text = content.strip()
  if text.startswith("```"):
    text = text.strip("`")
    text = text[text.find("{"):] if "{" in text else text
  start, end = text.find("{"), text.rfind("}")
  if start < 0 or end <= start:
    return None
  try:
    data = json.loads(text[start : end + 1])
  except json.JSONDecodeError:
    return None
  if not isinstance(data, dict):
    return None
  name = data.get("name") or data.get("tool") or data.get("function")
  arguments = data.get("arguments", data.get("parameters", data.get("args", {})))
  if not isinstance(name, str) or not isinstance(arguments, dict):
    return None
  return {"name": name, "arguments": arguments}
