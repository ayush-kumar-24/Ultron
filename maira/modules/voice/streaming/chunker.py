"""Sentence/phrase chunker for speak-while-generate TTS."""

from __future__ import annotations

import re


class TextChunker:
  """Accumulate streamed tokens and emit speakable chunks at boundaries."""

  def __init__(self, *, min_chars: int = 12, max_chars: int = 160) -> None:
    self._min_chars = max(1, min_chars)
    self._max_chars = max(self._min_chars, max_chars)
    self._buffer = ""

  def push(self, token: str) -> list[str]:
    if not token:
      return []
    self._buffer += token
    return self._extract(flush=False)

  def flush(self) -> list[str]:
    chunks = self._extract(flush=True)
    leftover = self._buffer.strip()
    self._buffer = ""
    if leftover:
      chunks.append(leftover)
    return chunks

  def reset(self) -> None:
    self._buffer = ""

  def _extract(self, *, flush: bool) -> list[str]:
    chunks: list[str] = []
    while True:
      match = re.search(r"[.!?]\s|\n", self._buffer)
      if match:
        end = match.end()
        candidate = self._buffer[:end].strip()
        self._buffer = self._buffer[end:]
        if len(candidate) >= self._min_chars:
          chunks.append(candidate)
        elif candidate:
          # Too short — keep attached to following text
          self._buffer = candidate + " " + self._buffer
          break
        continue

      if len(self._buffer) >= self._max_chars:
        # Soft split on last space
        split_at = self._buffer.rfind(" ", 0, self._max_chars)
        if split_at < self._min_chars:
          split_at = self._max_chars
        candidate = self._buffer[:split_at].strip()
        self._buffer = self._buffer[split_at:].lstrip()
        if candidate:
          chunks.append(candidate)
        continue

      if flush:
        break
      break
    return chunks
