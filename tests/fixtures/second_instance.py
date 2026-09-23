"""Run a second SingleInstanceGuard in its own process (tests only).

Usage: python -m tests.fixtures.second_instance <server_name> <build_id>
Prints ACQUIRED or REFUSED.
"""

import sys

from PySide6.QtCore import QCoreApplication

from maira.app.single_instance import SingleInstanceGuard

if __name__ == "__main__":
  app = QCoreApplication(sys.argv)
  guard = SingleInstanceGuard(sys.argv[1], build_id=sys.argv[2], takeover_timeout_s=10)
  print("ACQUIRED" if guard.try_acquire() else "REFUSED", flush=True)
  guard.release()
