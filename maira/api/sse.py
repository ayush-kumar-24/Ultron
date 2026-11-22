"""Shared helpers for the `data: {json}` streaming endpoints."""

from __future__ import annotations

import json

STREAM_HEADERS = {
  "Cache-Control": "no-cache, no-transform",
  "Connection": "keep-alive",
  "X-Accel-Buffering": "no",
}


def sse(payload: dict) -> str:
  return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
