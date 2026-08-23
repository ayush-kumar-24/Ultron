"""Dependency injection container."""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class Container:
  def __init__(self) -> None:
    self._factories: dict[str, Callable[[], Any]] = {}
    self._singletons: dict[str, Any] = {}

  def register(self, key: str, factory: Callable[[], Any], *, singleton: bool = True) -> None:
    self._factories[key] = factory
    if singleton and key in self._singletons:
      del self._singletons[key]

  def register_instance(self, key: str, instance: Any) -> None:
    self._singletons[key] = instance

  def resolve(self, key: str) -> Any:
    if key in self._singletons:
      return self._singletons[key]
    if key not in self._factories:
      raise KeyError(f"Service not registered: {key}")
    instance = self._factories[key]()
    self._singletons[key] = instance
    return instance

  def try_resolve(self, key: str) -> Any | None:
    try:
      return self.resolve(key)
    except KeyError:
      return None
