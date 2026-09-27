"""Every control on the Settings screen must really change the app's settings."""

from __future__ import annotations

import pytest
import yaml

import maira.app.settings as settings_mod
from maira.app.settings_schema import CATEGORIES, FIELDS, field_by_path, fields_for
from maira.app.user_config import UserConfig

# A non-default value for every kind of field.
SAMPLES = {
  "text": "Test value",
  "time": "06:45",
  "file": "C:/voices/me.wav",
}


def _sample(field, default):
  if field.kind == "bool":
    return not default
  if field.kind == "int":
    return int(field.minimum) if default != int(field.minimum) else int(field.maximum)
  if field.kind == "float":
    return field.minimum if abs(default - field.minimum) > 1e-9 else field.maximum
  if field.kind == "choice":
    for value, _label in field.options:
      if value != default:
        return value
    return "custom-model:1b"
  return SAMPLES[field.kind]


@pytest.mark.parametrize("field", FIELDS, ids=[f.path for f in FIELDS])
def test_every_field_reaches_the_app(field, tmp_path, monkeypatch) -> None:
  user_file = tmp_path / "config.yaml"
  monkeypatch.setattr(settings_mod, "user_config_path", lambda: user_file)
  config = UserConfig(user_file)
  default = field.read(settings_mod.load_settings())
  value = _sample(field, default)
  assert value != default

  config.set(field.path, value)
  for path, extra in (field.also_sets(value) if field.also_sets else {}).items():
    config.set(path, extra)

  assert field.read(settings_mod.load_settings()) == value


def test_setting_a_default_removes_the_override(tmp_path) -> None:
  config = UserConfig(tmp_path / "c.yaml")
  config.set("briefing.time", "07:00")
  assert config.is_overridden("briefing.time")
  config.set("briefing.time", "08:00")  # the default
  assert not config.is_overridden("briefing.time")
  assert yaml.safe_load((tmp_path / "c.yaml").read_text(encoding="utf-8")) is None


def test_values_that_yaml_could_misread_survive(tmp_path) -> None:
  config = UserConfig(tmp_path / "c.yaml")
  for path, value in [("briefing.time", "07:30"), ("voice.language", "no"), ("briefing.name", "on")]:
    config.set(path, value)
  again = UserConfig(tmp_path / "c.yaml")
  assert again.get("briefing.time") == "07:30"
  assert again.get("voice.language") == "no"
  assert again.get("briefing.name") == "on"


def test_other_keys_in_the_user_file_are_kept(tmp_path) -> None:
  path = tmp_path / "c.yaml"
  path.write_text("custom:\n  thing: 1\nbriefing:\n  name: Ayush\n", encoding="utf-8")
  config = UserConfig(path)
  config.set("briefing.time", "07:00")
  saved = yaml.safe_load(path.read_text(encoding="utf-8"))
  assert saved == {"custom": {"thing": 1}, "briefing": {"name": "Ayush", "time": "07:00"}}


def test_kokoro_voice_also_sets_language_code() -> None:
  field = field_by_path("voice.tts.voice")
  assert field.also_sets("bf_emma") == {"voice.tts_lang": "b"}
  assert field.also_sets("hf_alpha") == {"voice.tts_lang": "h"}


def test_categories_are_complete() -> None:
  keys = {key for key, _ in CATEGORIES}
  assert {f.category for f in FIELDS} <= keys
  assert all(fields_for(key) for key in keys - {"status"})
  assert len({f.path for f in FIELDS}) == len(FIELDS)
