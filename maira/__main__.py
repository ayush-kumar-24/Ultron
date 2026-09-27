"""Application entry point."""

import sys

from maira.app.bootstrap import bootstrap


def main() -> None:
  context = bootstrap()
  if context is None:
    # Another Ultron is already running and has been brought to the front.
    sys.exit(0)
  exit_code = context.qt_app.exec()
  context.lifecycle.run_shutdown()
  sys.exit(exit_code)


if __name__ == "__main__":
  main()
