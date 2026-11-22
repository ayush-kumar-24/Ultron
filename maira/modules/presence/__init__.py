"""Desktop presence — orb state, not Qt widgets (those live in maira.ui.presence)."""

from maira.modules.presence.mapper import apply_presence_event
from maira.modules.presence.state import PresenceState

__all__ = ["PresenceState", "apply_presence_event"]
