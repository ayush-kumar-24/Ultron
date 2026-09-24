"""Typed application settings."""

from dataclasses import dataclass

from maira.infrastructure.config.yaml_loader import deep_merge, load_yaml
from maira.shared.utils.paths import default_config_path, user_config_path


@dataclass(frozen=True)
class OllamaSettings:
  host: str
  model: str
  timeout_seconds: float
  keep_alive: str


@dataclass(frozen=True)
class AppSettings:
  name: str
  offline_first: bool


@dataclass(frozen=True)
class PathSettings:
  data_dir: str
  plugins_dir: str


@dataclass(frozen=True)
class MemorySettings:
  embedding_model: str
  chroma_path: str
  recall_top_k: int
  background_encoding: bool
  recall_mode: str


@dataclass(frozen=True)
class ContextSettings:
  max_memories: int
  max_context_chars: int
  show_debug: bool
  history_messages: int
  log_latency: bool


@dataclass(frozen=True)
class VoiceSettings:
  enabled: bool
  whisper_model: str
  whisper_device: str
  whisper_compute_type: str
  sample_rate: int
  stt_provider: str
  tts_provider: str
  tts_engine: str
  tts_voice: str
  tts_lang: str
  allow_tts_fallback: bool
  language: str
  silence_seconds: float
  max_reply_tokens: int
  auto_speak: bool
  interrupt_on_speech: bool
  max_model_download_gb: float
  chunk_min_chars: int
  chunk_max_chars: int
  warmup: bool
  whisper_beam_size: int


@dataclass(frozen=True)
class DesktopSettings:
  enabled: bool
  allow_input: bool


@dataclass(frozen=True)
class BackgroundSettings:
  close_to_tray: bool
  start_minimized: bool


@dataclass(frozen=True)
class NotificationSettings:
  enabled: bool
  windows_toast: bool
  snooze_minutes: int


@dataclass(frozen=True)
class BriefingSettings:
  enabled: bool
  time: str  # "HH:MM", local time
  until: str  # after this, skip today's automatic briefing
  speak: bool
  name: str  # used in the greeting


@dataclass(frozen=True)
class TaskSettings:
  remind_at_due: bool  # a task with a clock time gets a reminder then
  roll_over: bool  # unfinished tasks from earlier days move to today


@dataclass(frozen=True)
class Settings:
  app: AppSettings
  paths: PathSettings
  ollama: OllamaSettings
  memory: MemorySettings
  context: ContextSettings
  voice: VoiceSettings
  desktop: DesktopSettings
  background: BackgroundSettings
  notifications: NotificationSettings
  briefing: BriefingSettings
  tasks: TaskSettings

  @property
  def app_name(self) -> str:
    return self.app.name


def load_settings() -> Settings:
  raw = load_yaml(default_config_path())
  user = load_yaml(user_config_path())
  merged = deep_merge(raw, user)

  app_raw = merged.get("app", {})
  paths_raw = merged.get("paths", {})
  ollama_raw = merged.get("ollama", {})
  memory_raw = merged.get("memory", {})
  context_raw = merged.get("context", {})
  voice_raw = merged.get("voice", {})
  desktop_raw = merged.get("desktop", {})
  background_raw = merged.get("background", {})
  notifications_raw = merged.get("notifications", {})
  briefing_raw = merged.get("briefing", {})
  tasks_raw = merged.get("tasks", {})
  stt_raw = voice_raw.get("stt", {}) if isinstance(voice_raw.get("stt"), dict) else {}
  tts_raw = voice_raw.get("tts", {}) if isinstance(voice_raw.get("tts"), dict) else {}
  behavior_raw = voice_raw.get("behavior", {}) if isinstance(voice_raw.get("behavior"), dict) else {}
  limits_raw = voice_raw.get("limits", {}) if isinstance(voice_raw.get("limits"), dict) else {}

  tts_provider = str(
    voice_raw.get("tts_provider")
    or tts_raw.get("provider")
    or voice_raw.get("tts_engine", "kokoro")
  )
  stt_provider = str(
    voice_raw.get("stt_provider") or stt_raw.get("provider") or "faster_whisper"
  )

  return Settings(
    app=AppSettings(
      name=str(app_raw.get("name", "Ultron")),
      offline_first=bool(app_raw.get("offline_first", True)),
    ),
    paths=PathSettings(
      data_dir=str(paths_raw.get("data_dir", "data")),
      plugins_dir=str(paths_raw.get("plugins_dir", "plugins_external")),
    ),
    ollama=OllamaSettings(
      host=str(ollama_raw.get("host", "http://127.0.0.1:11434")),
      model=str(ollama_raw.get("model", "llama3.2:latest")),
      timeout_seconds=float(ollama_raw.get("timeout_seconds", 120)),
      keep_alive=str(ollama_raw.get("keep_alive", "30m")),
    ),
    memory=MemorySettings(
      embedding_model=str(
        memory_raw.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
      ),
      chroma_path=str(memory_raw.get("chroma_path", "data/chroma")),
      recall_top_k=int(memory_raw.get("recall_top_k", 5)),
      background_encoding=bool(memory_raw.get("background_encoding", True)),
      recall_mode=str(memory_raw.get("recall_mode", "keyword")),
    ),
    context=ContextSettings(
      max_memories=int(context_raw.get("max_memories", 5)),
      max_context_chars=int(context_raw.get("max_context_chars", 2000)),
      show_debug=bool(context_raw.get("show_debug", False)),
      history_messages=int(context_raw.get("history_messages", 24)),
      log_latency=bool(context_raw.get("log_latency", True)),
    ),
    voice=VoiceSettings(
      enabled=bool(voice_raw.get("enabled", True)),
      whisper_model=str(
        stt_raw.get("model") or voice_raw.get("whisper_model", "base")
      ),
      whisper_device=str(
        stt_raw.get("device") or voice_raw.get("whisper_device", "cpu")
      ),
      whisper_compute_type=str(voice_raw.get("whisper_compute_type", "int8")),
      sample_rate=int(voice_raw.get("sample_rate", 16000)),
      stt_provider=stt_provider,
      tts_provider=tts_provider,
      tts_engine=str(voice_raw.get("tts_engine", tts_provider)),
      tts_voice=str(tts_raw.get("voice") or voice_raw.get("tts_voice", "af_heart")),
      tts_lang=str(voice_raw.get("tts_lang", "a")),
      allow_tts_fallback=bool(voice_raw.get("allow_tts_fallback", False)),
      language=str(voice_raw.get("language") or ""),
      silence_seconds=float(
        behavior_raw.get("silence_timeout") or voice_raw.get("silence_seconds", 0.9)
      ),
      max_reply_tokens=int(voice_raw.get("max_reply_tokens", 64)),
      auto_speak=bool(behavior_raw.get("auto_speak", voice_raw.get("auto_speak", True))),
      interrupt_on_speech=bool(
        behavior_raw.get("interrupt_on_speech", voice_raw.get("interrupt_on_speech", True))
      ),
      max_model_download_gb=float(
        limits_raw.get("max_model_download_gb", voice_raw.get("max_model_download_gb", 1))
      ),
      chunk_min_chars=int(voice_raw.get("chunk_min_chars", 16)),
      chunk_max_chars=int(voice_raw.get("chunk_max_chars", 90)),
      warmup=bool(voice_raw.get("warmup", True)),
      whisper_beam_size=int(
        stt_raw.get("beam_size") or voice_raw.get("whisper_beam_size", 5)
      ),
    ),
    desktop=DesktopSettings(
      enabled=bool(desktop_raw.get("enabled", True)),
      allow_input=bool(desktop_raw.get("allow_input", True)),
    ),
    background=BackgroundSettings(
      close_to_tray=bool(background_raw.get("close_to_tray", True)),
      start_minimized=bool(background_raw.get("start_minimized", False)),
    ),
    notifications=NotificationSettings(
      enabled=bool(notifications_raw.get("enabled", True)),
      windows_toast=bool(notifications_raw.get("windows_toast", True)),
      snooze_minutes=max(1, int(notifications_raw.get("snooze_minutes", 10))),
    ),
    briefing=BriefingSettings(
      enabled=bool(briefing_raw.get("enabled", True)),
      time=str(briefing_raw.get("time", "08:00")),
      until=str(briefing_raw.get("until", "12:00")),
      speak=bool(briefing_raw.get("speak", True)),
      name=str(briefing_raw.get("name") or ""),
    ),
    tasks=TaskSettings(
      remind_at_due=bool(tasks_raw.get("remind_at_due", True)),
      roll_over=bool(tasks_raw.get("roll_over", True)),
    ),
  )
