from maira.app.settings import load_settings


def test_presence_defaults() -> None:
  settings = load_settings()
  assert settings.presence.enabled is True
  assert settings.presence.start_hidden is True
  assert settings.presence.autostart is True
  assert settings.presence.orb_visible is True
  assert settings.presence.hotkey == "Ctrl+Alt+U"
