"""Qt UI tests run headless unless a platform is chosen explicitly."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
