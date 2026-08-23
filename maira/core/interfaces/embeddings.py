"""Embedding encoder port — text-to-vector conversion."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingEncoder(ABC):
  @abstractmethod
  def is_available(self) -> bool:
    """Return True when the encoder can produce vectors."""

  @abstractmethod
  def encode(self, text: str) -> list[float]:
    """Encode a single text into an embedding vector."""

  @abstractmethod
  def encode_batch(self, texts: list[str]) -> list[list[float]]:
    """Encode multiple texts into embedding vectors."""
