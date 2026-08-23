"""Unit tests for chat latency helpers and streaming UI batching."""

from maira.shared.utils.latency import ChatLatencyTrace, begin_trace, clear_trace, current_trace


def test_latency_trace_ttft_and_total() -> None:
  trace = ChatLatencyTrace(model="llama3.2:latest")
  trace.request_start = 100.0
  trace.ollama_start = 100.1
  trace.first_token = 100.4
  trace.complete = 101.0
  trace.token_count = 20
  assert abs((trace.ttft or 0) - 0.3) < 1e-9
  assert abs((trace.total or 0) - 1.0) < 1e-9
  assert abs((trace.tokens_per_second or 0) - (20 / 0.6)) < 1e-6
  clear_trace()


def test_begin_trace_sets_current() -> None:
  clear_trace()
  trace = begin_trace(model="x")
  assert current_trace() is trace
  clear_trace()
  assert current_trace() is None
