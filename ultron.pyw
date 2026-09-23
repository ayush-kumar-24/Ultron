"""Windowless launcher: double-click, or used by "Start with Windows".

Running this file puts the project folder on sys.path, so it works from any
working directory (Windows starts Run-key programs in System32).
"""

from maira.__main__ import main

if __name__ == "__main__":
  main()
