"""High-resolution chat latency instrumentation (monotonic clocks only)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ChatLatencyTrace:
  """Marks along one chat request using time.perf_counter()."""

  request_start: float = field(default_factory=time.perf_counter)
  controller_received: float | None = None
  brain_start: float | None = None
  context_done: float | None = None
  ollama_start: float | None = None
  first_token: float | None = None
  ui_first_token: float | None = None
  last_token: float | None = None
  complete: float | None = None
  ui_complete: float | None = None
  token_count: int = 0
  prompt_chars: int = 0
  prompt_messages: int = 0
  model: str = ""

  def mark(self, name: str) -> None:
    now = time.perf_counter()
    if name == "controller_received":
      self.controller_received = now
    elif name == "brain_start":
      self.brain_start = now
    elif name == "context_done":
      self.context_done = now
    elif name == "ollama_start":
      self.ollama_start = now
    elif name == "first_token":
      if self.first_token is None:
        self.first_token = now
      self.last_token = now
    elif name == "ui_first_token":
      if self.ui_first_token is None:
        self.ui_first_token = now
    elif name == "complete":
      self.complete = now
    elif name == "ui_complete":
      self.ui_complete = now

  def note_token(self) -> None:
    self.token_count += 1
    self.mark("first_token")

  def elapsed(self, end: float | None, start: float | None = None) -> float | None:
    if end is None:
      return None
    origin = self.request_start if start is None else start
    if origin is None:
      return None
    return end - origin

  @property
  def ttft(self) -> float | None:
    if self.first_token is None:
      return None
    origin = self.ollama_start if self.ollama_start is not None else self.request_start
    return self.first_token - origin

  @property
  def ttft_ui(self) -> float | None:
    if self.ui_first_token is None:
      return None
    return self.ui_first_token - self.request_start

  @property
  def total(self) -> float | None:
    end = self.complete if self.complete is not None else self.ui_complete
    if end is None:
      return None
    return end - self.request_start

  @property
  def tokens_per_second(self) -> float | None:
    if self.first_token is None or self.complete is None or self.token_count <= 0:
      return None
    duration = self.complete - self.first_token
    if duration <= 0:
      return None
    return self.token_count / duration

  def as_dict(self) -> dict[str, Any]:
    return {
      "model": self.model,
      "ttft_seconds": _round(self.ttft),
      "ttft_ui_seconds": _round(self.ttft_ui),
      "total_seconds": _round(self.total),
      "tokens": self.token_count,
      "tokens_per_second": _round(self.tokens_per_second),
      "prompt_chars": self.prompt_chars,
      "prompt_messages": self.prompt_messages,
      "context_seconds": _round(
        None
        if self.context_done is None or self.brain_start is None
        else self.context_done - self.brain_start
      ),
    }

  def log_summary(self) -> None:
    data = self.as_dict()
    logger.info(
      "[MAIRA LATENCY] model={} TTFT={:.3f}s TTFT_UI={} total={} tokens={} tok/s={} "
      "prompt_msgs={} prompt_chars={} context_s={}",
      data.get("model") or "?",
      data.get("ttft_seconds") or -1.0,
      data.get("ttft_ui_seconds"),
      data.get("total_seconds"),
      data.get("tokens"),
      data.get("tokens_per_second"),
      data.get("prompt_messages"),
      data.get("prompt_chars"),
      data.get("context_seconds"),
    )


def _round(value: float | None) -> float | None:
  if value is None:
    return None
  return round(value, 4)


# Thread-local-ish current trace for UI bridges (single active chat turn).
_current_trace: ChatLatencyTrace | None = None


def begin_trace(*, model: str = "") -> ChatLatencyTrace:
  global _current_trace
  _current_trace = ChatLatencyTrace(model=model)
  return _current_trace


def current_trace() -> ChatLatencyTrace | None:
  return _current_trace


def clear_trace() -> None:
  global _current_trace
  _current_trace = None
