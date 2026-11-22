"""Application entry point."""

from __future__ import annotations

import sys

from maira.app.bootstrap import bootstrap, run_headless


def main() -> None:
  headless = "--headless" in sys.argv
  if headless:
    sys.argv = [arg for arg in sys.argv if arg != "--headless"]
    run_headless()
    return

  context = bootstrap()
  if context is None:
    # Another Ultron is already running and has been brought to the front.
    sys.exit(0)
  exit_code = context.qt_app.exec()
  context.lifecycle.run_shutdown()
  sys.exit(exit_code)


if __name__ == "__main__":
  main()
