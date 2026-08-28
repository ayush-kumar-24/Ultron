"""GET /system/health — cheap probe the frontend uses to detect a live backend."""

from __future__ import annotations

import time

from fastapi import APIRouter

from maira.api.deps import get_container, get_settings

router = APIRouter(tags=["system"])


@router.get("/system/health")
def health() -> dict:
  started = time.perf_counter()
  settings = get_settings()
  container = get_container()
  memory = container.try_resolve("memory")
  try:
    memory_count = len(memory.list_memories()) if memory is not None else 0
  except Exception:  # noqa: BLE001
    memory_count = 0

  model = settings.ollama.model
  ok = True
  llm = container.try_resolve("llm")
  if llm is not None:
    model = getattr(llm, "model", None) or model
    try:
      ok = bool(llm.is_available())
    except Exception:  # noqa: BLE001
      ok = False

  latency_ms = int((time.perf_counter() - started) * 1000)
  return {
    "ok": ok,
    "local": True,
    "model": model,
    "latencyMs": latency_ms,
    "memoryCount": memory_count,
  }
