"""Headless API entry: python -m maira.api"""

from __future__ import annotations

from maira.app.bootstrap import run_headless

if __name__ == "__main__":
  run_headless()
