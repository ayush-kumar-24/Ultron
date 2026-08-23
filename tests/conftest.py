"""Shared pytest configuration."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
  config.addinivalue_line(
    "markers",
    "integration: tests requiring external services such as Ollama",
  )
