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
  exit_code = context.qt_app.exec()
  context.lifecycle.run_shutdown()
  sys.exit(exit_code)


if __name__ == "__main__":
  main()
