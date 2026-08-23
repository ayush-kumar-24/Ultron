"""Standalone UI prototype package (mock-data only).

Launch with:
  python -m maira.ui.prototype
"""

__all__ = ["main"]


def main() -> int:
  from maira.ui.prototype.__main__ import main as _main

  return _main()
