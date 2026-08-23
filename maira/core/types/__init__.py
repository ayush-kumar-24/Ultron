"""Shared type aliases and generic protocols used across modules."""

from collections.abc import Callable
from typing import Any, TypeAlias

EventHandler: TypeAlias = Callable[[Any], None]
