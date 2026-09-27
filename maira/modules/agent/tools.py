"""What a tool is: a name and description for the model, a way to run it, and whether to ask first."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
  """A tool could not do what was asked; the message goes back to the model."""


@dataclass(frozen=True)
class Tool:
  name: str
  description: str
  properties: dict[str, dict[str, Any]]  # JSON-schema properties of the arguments
  run: Callable[[dict[str, Any]], str]
  required: tuple[str, ...] = ()
  # Returns a plain-English line to show the user before running; None = no approval needed.
  confirm: Callable[[dict[str, Any]], str] | None = None
  # Checks the arguments before asking the user (so we never ask about an impossible step).
  check: Callable[[dict[str, Any]], None] | None = field(default=None)

  def schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {"type": "object", "properties": self.properties, "required": list(self.required)},
      },
    }


def text_arg(args: dict[str, Any], key: str, default: str = "") -> str:
  value = args.get(key, default)
  return default if value is None else str(value).strip()


def list_arg(args: dict[str, Any], key: str) -> list[str]:
  value = args.get(key) or []
  if isinstance(value, str):
    value = [part for part in value.replace(";", ",").split(",")]
  return [str(item).strip() for item in value if str(item).strip()]
