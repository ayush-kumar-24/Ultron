"""Configures Loguru from ``config/logging.yaml`` and routes logs to file/console."""

import faulthandler

from loguru import logger

from maira.infrastructure.config.yaml_loader import load_yaml
from maira.shared.utils.paths import config_dir, logs_dir


_crash_log = None


def _enable_crash_log() -> None:
  """Native crashes (e.g. inside Windows APIs) bypass Python logging; record them."""
  global _crash_log
  if _crash_log is not None:
    return
  try:
    _crash_log = open(logs_dir() / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(file=_crash_log, all_threads=True)
  except OSError:
    faulthandler.enable()


def setup_logging() -> None:
  _enable_crash_log()
  logging_yaml = load_yaml(config_dir() / "logging.yaml")
  level = str(logging_yaml.get("level", "INFO"))
  rotation = str(logging_yaml.get("rotation", "10 MB"))
  retention = str(logging_yaml.get("retention", "7 days"))

  logger.remove()
  logger.add(lambda msg: print(msg, end=""), level=level, colorize=True)
  logger.add(
    logs_dir() / "maira.log",
    level=level,
    rotation=rotation,
    retention=retention,
    encoding="utf-8",
  )
