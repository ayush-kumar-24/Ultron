"""Configures Loguru from ``config/logging.yaml`` and routes logs to file/console."""

from loguru import logger

from maira.infrastructure.config.yaml_loader import load_yaml
from maira.shared.utils.paths import config_dir, logs_dir


def setup_logging() -> None:
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
