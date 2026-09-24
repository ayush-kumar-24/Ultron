"""Connect the Settings screen to the running app (restart, voices, status)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from loguru import logger

from maira.app.container import Container
from maira.modules.voice import voice_tools
from maira.shared.utils.paths import data_dir, logs_dir
from maira.ui.prototype.screens.live_settings import SettingsActions

_ENGINE_NAMES = {"kokoro": "Kokoro", "chatterbox": "Chatterbox", "indic_parler": "Indic Parler"}


def _optional(container: Container, name: str) -> Any:
  try:
    return container.resolve(name)
  except Exception:  # noqa: BLE001 — not registered in tests / older setups
    return None


def status_rows(container: Container) -> list[tuple[str, bool, str]]:
  """(name, ok, detail) for Settings → System status. Never raises."""
  rows: list[tuple[str, bool, str]] = []
  settings = container.resolve("settings")

  try:
    llm_ok = bool(container.resolve("llm").is_available())
  except Exception:  # noqa: BLE001
    llm_ok = False
  rows.append((
    "AI (Ollama)",
    llm_ok,
    f"{settings.ollama.model} ready" if llm_ok else f"not reachable at {settings.ollama.host} — start Ollama",
  ))

  provider = settings.voice.tts_provider
  installed = voice_tools.is_installed(provider)
  engine = _ENGINE_NAMES.get(provider, provider)
  fix = 'pip install -e ".[voice]"' if provider == "kokoro" else "Settings → Voice → Install"
  rows.append(("Voice", installed, f"{engine} installed" if installed else f"{engine} not installed — {fix}"))

  try:
    voice = container.resolve("voice")
    stt_ok = bool(voice._stt.is_available())  # noqa: SLF001
    mic_ok = bool(voice._audio.is_available())  # noqa: SLF001
  except Exception:  # noqa: BLE001
    stt_ok = mic_ok = False
  rows.append(("Speech recognition", stt_ok, f"Whisper {settings.voice.whisper_model}" if stt_ok else 'not installed — pip install -e ".[voice]"'))
  rows.append(("Microphone", mic_ok, "found" if mic_ok else "no input device"))

  notifications = _optional(container, "notifications")
  has_backend = bool(notifications is not None and notifications.has_backend())
  if not settings.notifications.enabled:
    rows.append(("Notifications", False, "turned off in Settings → Tasks"))
  else:
    rows.append(("Notifications", has_backend, "Windows pop-ups on" if has_backend else "shown inside the app only"))

  autostart = _optional(container, "autostart")
  if autostart is not None and autostart.is_supported():
    on = autostart.is_enabled()
    rows.append(("Start with Windows", on, "on" if on else "off"))

  rows.append(("Data folder", True, str(data_dir())))
  return rows


def build_settings_actions(
  container: Container,
  *,
  on_name_changed: Callable[[str], None] | None = None,
) -> SettingsActions:
  settings = container.resolve("settings")
  restart = _optional(container, "restart")
  autostart = _optional(container, "autostart")
  notifications = _optional(container, "notifications")
  lifecycle = _optional(container, "lifecycle")

  previewer = voice_tools.VoicePreviewer()
  if lifecycle is not None:
    lifecycle.on_shutdown(previewer.close)

  def preview(provider: str, values: dict):
    text = str(values.get("text") or voice_tools.PREVIEW_TEXT)
    return previewer.preview(provider, values, text)

  def test_notification() -> str:
    if notifications is None or not settings.notifications.enabled:
      return "Notifications are turned off (Settings → Tasks & reminders)."
    backend = notifications.send_test()
    if backend is None:
      return "No notification could be shown — see data/logs/maira.log."
    return f"Test notification sent ({backend})."

  def diagnostics() -> list[str]:
    from maira.modules.voice.diagnostics import collect_diagnostics  # noqa: PLC0415

    lines = collect_diagnostics(container).as_lines()
    lines.append(f"Voice engine: {settings.voice.tts_provider}")
    lines.append(f"Python: {sys.executable}")
    return lines

  live: dict[str, Callable[[Any], None]] = {}
  if on_name_changed is not None:
    live["briefing.name"] = lambda value: on_name_changed(str(value or ""))

  def set_autostart(on: bool) -> bool:
    if autostart is None:
      return False
    result = autostart.set_enabled(on)
    logger.info("Start with Windows set from Settings: {}", result)
    return result

  return SettingsActions(
    restart=restart,
    send_test_notification=test_notification,
    status=lambda: status_rows(container),
    ollama_models=voice_tools.ollama_models,
    autostart_supported=(lambda: autostart.is_supported()) if autostart is not None else None,
    autostart_enabled=(lambda: autostart.is_enabled()) if autostart is not None else None,
    set_autostart=set_autostart if autostart is not None else None,
    preview_voice=preview,
    is_voice_installed=voice_tools.is_installed,
    install_command=voice_tools.install_command,
    diagnostics=diagnostics,
    data_dir=data_dir(),
    logs_dir=logs_dir(),
    live=live,
  )
