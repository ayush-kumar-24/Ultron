"""Application entry point."""

import sys

from maira.app.bootstrap import bootstrap


def main() -> None:
  context = bootstrap()
  exit_code = context.qt_app.exec()
  context.lifecycle.run_shutdown()
  sys.exit(exit_code)


if __name__ == "__main__":
  main()
