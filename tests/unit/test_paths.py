"""Unit tests for path utilities."""

from maira.shared.utils import paths


def test_project_root_exists() -> None:
  root = paths.project_root()
  assert root.is_dir()
  assert (root / "maira").is_dir()


def test_data_dir_created(tmp_path, monkeypatch) -> None:
  monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
  data = paths.data_dir()
  assert data == tmp_path / "data"
  assert data.is_dir()


def test_logs_dir_created(tmp_path, monkeypatch) -> None:
  monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
  logs = paths.logs_dir()
  assert logs == tmp_path / "data" / "logs"
  assert logs.is_dir()


def test_config_paths(tmp_path, monkeypatch) -> None:
  monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
  (tmp_path / "config").mkdir()
  (tmp_path / "config" / "default.yaml").write_text("app:\n  name: Test\n", encoding="utf-8")

  assert paths.config_dir() == tmp_path / "config"
  assert paths.default_config_path() == tmp_path / "config" / "default.yaml"
  assert paths.user_config_path() == tmp_path / "data" / "config.yaml"


def test_database_path(tmp_path, monkeypatch) -> None:
  monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
  assert paths.database_path() == tmp_path / "data" / "maira.db"
  assert (tmp_path / "data").is_dir()


def test_chroma_dir(tmp_path, monkeypatch) -> None:
  monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
  assert paths.chroma_dir() == tmp_path / "data" / "chroma"
  assert (tmp_path / "data" / "chroma").is_dir()
