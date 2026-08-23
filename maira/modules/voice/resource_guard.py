"""Reduce ML-library CPU contention so Ollama can get first-token priority.

Whisper (CTranslate2) and Kokoro (PyTorch) default to using many CPU threads.
After STT (and while LLM runs), temporarily lower those pools so llama3.2
is not starved. Models stay loaded — no cold reloads.
"""

from __future__ import annotations

import gc
import os
from contextlib import contextmanager
from typing import Iterator

from loguru import logger

_saved: dict[str, int] = {}


def _get_torch_threads() -> int | None:
  try:
    import torch

    return int(torch.get_num_threads())
  except Exception:  # noqa: BLE001
    return None


def _set_torch_threads(n: int) -> None:
  try:
    import torch

    torch.set_num_threads(max(1, n))
  except Exception:  # noqa: BLE001
    return


def _set_ct2_threads(n: int) -> None:
  try:
    import ctranslate2

    if hasattr(ctranslate2, "set_num_threads"):
      ctranslate2.set_num_threads(max(1, n))
  except Exception:  # noqa: BLE001
    return


def snapshot_resources() -> dict:
  out: dict = {
    "python_rss_mb": None,
    "cpu_percent": None,
    "ollama_rss_mb": None,
    "llama_server_rss_mb": None,
  }
  try:
    import psutil

    proc = psutil.Process()
    out["python_rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
    out["cpu_percent"] = psutil.cpu_percent(interval=0.05)
    ollama_total = 0.0
    for p in psutil.process_iter(["name", "memory_info"]):
      name = (p.info.get("name") or "").lower()
      mem = p.info.get("memory_info")
      if mem is None:
        continue
      rss_mb = mem.rss / (1024 * 1024)
      if "llama-server" in name or "ollama_llama" in name:
        out["llama_server_rss_mb"] = round(rss_mb, 1)
      if "ollama" in name or "llama" in name:
        ollama_total += rss_mb
    if ollama_total:
      out["ollama_rss_mb"] = round(ollama_total, 1)
  except Exception:  # noqa: BLE001
    pass
  return out


@contextmanager
def llm_cpu_priority(*, torch_threads: int = 1, ct2_threads: int = 1) -> Iterator[None]:
  """Temporarily shrink Torch/CTranslate2 thread pools during Ollama TTFT."""
  prev_torch = _get_torch_threads()
  prev_omp = os.environ.get("OMP_NUM_THREADS")
  prev_mkl = os.environ.get("MKL_NUM_THREADS")

  try:
    _set_torch_threads(torch_threads)
    _set_ct2_threads(ct2_threads)
    os.environ["OMP_NUM_THREADS"] = str(max(1, torch_threads))
    os.environ["MKL_NUM_THREADS"] = str(max(1, torch_threads))
    gc.collect()
    logger.debug(
      "[MAIRA VOICE] llm_cpu_priority on (torch_threads={}, was={})",
      torch_threads,
      prev_torch,
    )
    yield
  finally:
    if prev_torch is not None:
      _set_torch_threads(prev_torch)
    if prev_omp is None:
      os.environ.pop("OMP_NUM_THREADS", None)
    else:
      os.environ["OMP_NUM_THREADS"] = prev_omp
    if prev_mkl is None:
      os.environ.pop("MKL_NUM_THREADS", None)
    else:
      os.environ["MKL_NUM_THREADS"] = prev_mkl
    # Restore CT2 to a moderate pool for next STT (not full assault)
    restore_ct2 = prev_torch if prev_torch is not None else max(2, (os.cpu_count() or 4) // 2)
    _set_ct2_threads(min(restore_ct2, 4))
    logger.debug("[MAIRA VOICE] llm_cpu_priority off")
