"""Domain and application exception hierarchy."""


class MairaError(Exception):
    """Base exception for Maira."""


class LLMUnavailableError(MairaError):
    """Raised when the local LLM provider is unreachable."""


class LLMStreamError(MairaError):
    """Raised when streaming from the LLM fails mid-response."""
