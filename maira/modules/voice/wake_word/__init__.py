"""Wake-word provider abstraction (optional; PTT remains primary)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class WakeWordProvider(ABC):
  @abstractmethod
  def get_provider_name(self) -> str: ...

  @abstractmethod
  def is_available(self) -> tuple[bool, str]: ...

  @abstractmethod
  def start(self) -> None: ...

  @abstractmethod
  def stop(self) -> None: ...


class NullWakeWordProvider(WakeWordProvider):
  def get_provider_name(self) -> str:
    return "none"

  def is_available(self) -> tuple[bool, str]:
    return False, "Wake word not configured (push-to-talk is available)"

  def start(self) -> None:
    return

  def stop(self) -> None:
    return
