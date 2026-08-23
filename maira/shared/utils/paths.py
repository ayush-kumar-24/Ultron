"""Resolves user data dir, config paths, and platform-specific locations."""

from pathlib import Path


def project_root() -> Path:
  return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
  path = project_root() / "data"
  path.mkdir(parents=True, exist_ok=True)
  return path


def logs_dir() -> Path:
  path = data_dir() / "logs"
  path.mkdir(parents=True, exist_ok=True)
  return path


def config_dir() -> Path:
  return project_root() / "config"


def user_config_path() -> Path:
  return data_dir() / "config.yaml"


def default_config_path() -> Path:
  return config_dir() / "default.yaml"


def database_path() -> Path:
  return data_dir() / "maira.db"


def chroma_dir() -> Path:
  path = data_dir() / "chroma"
  path.mkdir(parents=True, exist_ok=True)
  return path
