"""Unit tests for settings loading."""

from maira.app.settings import load_settings
from maira.infrastructure.config.yaml_loader import deep_merge


def test_load_settings_defaults() -> None:
  settings = load_settings()
  assert settings.app.name == "Ultron"
  assert settings.app.offline_first is True
  assert settings.ollama.host == "http://127.0.0.1:11434"
  assert settings.ollama.model == "llama3.2:latest"
  assert settings.ollama.timeout_seconds == 120.0
  assert settings.ollama.keep_alive == "30m"
  assert settings.memory.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
  assert settings.memory.recall_top_k == 5
  assert settings.context.max_memories == 5
  assert settings.context.max_context_chars == 2000
  assert settings.context.show_debug is False
  assert settings.context.history_messages == 24
  assert settings.context.log_latency is True
  assert settings.voice.whisper_model == "base"
  assert settings.voice.whisper_beam_size == 5
  assert settings.voice.sample_rate == 16000
  assert settings.voice.tts_engine == "kokoro"
  assert settings.voice.tts_provider == "kokoro"
  assert settings.voice.stt_provider == "faster_whisper"
  assert settings.voice.tts_voice == "af_heart"
  assert settings.voice.tts_lang == "a"
  assert settings.voice.allow_tts_fallback is False
  assert settings.voice.language == ""
  assert settings.voice.silence_seconds == 0.9
  assert settings.voice.max_reply_tokens == 64
  assert settings.voice.max_model_download_gb == 1.0
  assert settings.voice.warmup is True
  assert settings.desktop.enabled is True
  assert settings.desktop.allow_input is True
  assert settings.memory.background_encoding is True
  assert settings.memory.recall_mode == "keyword"
  assert settings.background.close_to_tray is True
  assert settings.background.start_minimized is False
  assert settings.notifications.enabled is True
  assert settings.notifications.windows_toast is True
  assert settings.notifications.snooze_minutes == 10


def test_deep_merge_nested() -> None:
  base = {"ollama": {"host": "http://localhost:11434", "model": "a"}}
  override = {"ollama": {"model": "b"}}
  merged = deep_merge(base, override)
  assert merged["ollama"]["host"] == "http://localhost:11434"
  assert merged["ollama"]["model"] == "b"
