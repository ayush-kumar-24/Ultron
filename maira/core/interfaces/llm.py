"""LLM provider port — low-level local model inference (Ollama adapter)."""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence


class LLMProvider(ABC):
  @abstractmethod
  def is_available(self) -> bool:
    """Return True if the provider is reachable."""

  @abstractmethod
  def list_models(self) -> list[str]:
    """Return installed model names."""

  @abstractmethod
  def chat_stream(
    self,
    messages: Sequence[dict[str, str]],
    *,
    options: dict | None = None,
  ) -> Iterator[str]:
    """Stream assistant response tokens from a chat completion."""
