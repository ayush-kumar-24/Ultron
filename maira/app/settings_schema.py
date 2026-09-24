"""Every setting the Settings screen can change, in one list.

Each field names its YAML path in data/config.yaml and how to read the
resulting value back from ``Settings`` (used by tests to prove every control
really reaches the app).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

CATEGORIES: list[tuple[str, str]] = [
  ("general", "General"),
  ("voice", "Voice"),
  ("listening", "Listening"),
  ("ai", "AI model"),
  ("briefing", "Daily briefing"),
  ("tasks", "Tasks & reminders"),
  ("control", "Desktop control"),
  ("skills", "Skills"),
  ("developer", "Developer"),
  ("status", "System status"),
]

KOKORO_VOICES: list[tuple[str, str]] = [
  ("af_heart", "Heart — warm (US, female)"),
  ("af_bella", "Bella (US, female)"),
  ("af_nicole", "Nicole — soft (US, female)"),
  ("af_sarah", "Sarah (US, female)"),
  ("af_sky", "Sky (US, female)"),
  ("af_nova", "Nova (US, female)"),
  ("bf_emma", "Emma (UK, female)"),
  ("bf_isabella", "Isabella (UK, female)"),
  ("bf_lily", "Lily (UK, female)"),
  ("hf_alpha", "Alpha (Hindi accent, female)"),
  ("hf_beta", "Beta (Hindi accent, female)"),
  ("am_adam", "Adam (US, male)"),
  ("bm_george", "George (UK, male)"),
  ("hm_omega", "Omega (Hindi accent, male)"),
]

PARLER_SPEAKERS: list[tuple[str, str]] = [
  ("Divya", "Divya (female)"),
  ("Leela", "Leela (female)"),
  ("Maya", "Maya (female)"),
  ("Sita", "Sita (female)"),
  ("Rohit", "Rohit (male)"),
  ("Karan", "Karan (male)"),
]


@dataclass(frozen=True)
class Field:
  path: str  # YAML path in data/config.yaml
  label: str
  kind: str  # text | choice | bool | int | float | time | file
  category: str
  read: Callable[[Any], Any]  # Settings -> effective value
  help: str = ""
  options: list[tuple[Any, str]] = field(default_factory=list)
  editable: bool = False  # choice that also accepts typed values
  minimum: float = 0
  maximum: float = 100
  step: float = 1
  restart: bool = True  # takes effect after "Restart now"
  # Only shown when another setting has one of these values, e.g. provider == chatterbox.
  visible_when: tuple[str, tuple[Any, ...]] | None = None
  # Extra paths written alongside, e.g. a Kokoro voice also sets its language code.
  also_sets: Callable[[Any], dict[str, Any]] | None = None


_CHATTERBOX = ("voice.tts.provider", ("chatterbox",))
_PARLER = ("voice.tts.provider", ("indic_parler",))
_KOKORO = ("voice.tts.provider", ("kokoro",))
_HEAVY = ("voice.tts.provider", ("chatterbox", "indic_parler"))

FIELDS: list[Field] = [
  # --- General -------------------------------------------------------------------
  Field("briefing.name", "Your name", "text", "general", lambda s: s.briefing.name,
        help="Used in greetings and the daily briefing.", restart=False),
  Field("background.close_to_tray", "Keep running when the window is closed", "bool", "general",
        lambda s: s.background.close_to_tray, help="Reminders keep working from the tray icon."),
  Field("background.start_minimized", "Start hidden in the tray", "bool", "general",
        lambda s: s.background.start_minimized),
  # --- Voice ---------------------------------------------------------------------
  Field("voice.tts.provider", "Voice engine", "choice", "voice", lambda s: s.voice.tts_provider,
        options=[("kokoro", "Kokoro — built in, fast"),
                 ("chatterbox", "Chatterbox — most natural (install)"),
                 ("indic_parler", "Indic Parler — Indian voices (install)")],
        help="Chatterbox and Indic Parler download a few GB once. Preview before applying."),
  Field("voice.tts.voice", "Kokoro voice", "choice", "voice", lambda s: s.voice.tts_voice,
        options=KOKORO_VOICES, visible_when=_KOKORO,
        also_sets=lambda v: {"voice.tts_lang": str(v)[:1] or "a"}),
  Field("voice.tts.speaker", "Speaker", "choice", "voice", lambda s: s.voice.tts_speaker,
        options=PARLER_SPEAKERS, editable=True, visible_when=_PARLER),
  Field("voice.tts.language", "Pronunciation", "choice", "voice", lambda s: s.voice.tts_language,
        options=[("auto", "Auto (Hindi for Devanagari text)"), ("hi", "Hindi"), ("en", "English")],
        visible_when=_CHATTERBOX, help="Try Hindi and English to hear which reads Hinglish better."),
  Field("voice.tts.reference_audio", "Voice sample (optional)", "file", "voice",
        lambda s: s.voice.tts_reference_audio, visible_when=_CHATTERBOX,
        help="A clean 5–15 second .wav of any voice. Chatterbox will speak like it."),
  Field("voice.tts.exaggeration", "Expressiveness", "float", "voice", lambda s: s.voice.tts_exaggeration,
        minimum=0.25, maximum=1.0, step=0.05, visible_when=_CHATTERBOX),
  Field("voice.tts.device", "Run on", "choice", "voice", lambda s: s.voice.tts_device,
        options=[("auto", "Auto (GPU if available)"), ("cuda", "NVIDIA GPU"), ("cpu", "CPU")],
        visible_when=_HEAVY),
  Field("voice.behavior.auto_speak", "Speak replies in voice conversation", "bool", "voice",
        lambda s: s.voice.auto_speak),
  Field("voice.max_reply_tokens", "Spoken reply length", "int", "voice", lambda s: s.voice.max_reply_tokens,
        minimum=32, maximum=256, step=16, help="Shorter replies start speaking sooner."),
  # --- Listening -----------------------------------------------------------------
  Field("voice.stt.model", "Speech recognition model", "choice", "listening", lambda s: s.voice.whisper_model,
        options=[("tiny", "Tiny — fastest"), ("base", "Base — balanced"), ("small", "Small — more accurate"),
                 ("medium", "Medium — most accurate, slow")]),
  Field("voice.language", "Language you speak", "choice", "listening", lambda s: s.voice.language,
        options=[("", "Auto-detect (Hindi + English)"), ("hi", "Hindi"), ("en", "English")]),
  Field("voice.behavior.silence_timeout", "Pause before Ultron answers (seconds)", "float", "listening",
        lambda s: s.voice.silence_seconds, minimum=0.5, maximum=2.5, step=0.1),
  Field("voice.behavior.interrupt_on_speech", "Stop talking when I speak", "bool", "listening",
        lambda s: s.voice.interrupt_on_speech),
  # --- AI model ------------------------------------------------------------------
  Field("ollama.model", "Model", "choice", "ai", lambda s: s.ollama.model, editable=True,
        help="Models installed in Ollama. Bigger models answer better but slower."),
  Field("ollama.host", "Ollama address", "text", "ai", lambda s: s.ollama.host),
  Field("context.history_messages", "Chat memory (messages)", "int", "ai", lambda s: s.context.history_messages,
        minimum=4, maximum=60, step=2, help="How many recent messages the model sees."),
  Field("memory.recall_mode", "Memory search", "choice", "ai", lambda s: s.memory.recall_mode,
        options=[("keyword", "Keyword — fast"), ("semantic", "Semantic — smarter (needs memory extras)")]),
  # --- Daily briefing --------------------------------------------------------------
  Field("briefing.enabled", "Show the daily briefing", "bool", "briefing", lambda s: s.briefing.enabled),
  Field("briefing.time", "Time", "time", "briefing", lambda s: s.briefing.time),
  Field("briefing.until", "Skip if Ultron starts after", "time", "briefing", lambda s: s.briefing.until),
  Field("briefing.speak", "Speak it aloud", "bool", "briefing", lambda s: s.briefing.speak),
  # --- Tasks & reminders -------------------------------------------------------------
  Field("tasks.remind_at_due", "Remind me when a timed task is due", "bool", "tasks",
        lambda s: s.tasks.remind_at_due),
  Field("tasks.roll_over", "Move unfinished tasks to today", "bool", "tasks", lambda s: s.tasks.roll_over),
  Field("notifications.enabled", "Pop-up notifications", "bool", "tasks", lambda s: s.notifications.enabled),
  Field("notifications.windows_toast", "Use Windows notifications (Done / Snooze)", "bool", "tasks",
        lambda s: s.notifications.windows_toast),
  Field("notifications.snooze_minutes", "Snooze for (minutes)", "int", "tasks",
        lambda s: s.notifications.snooze_minutes, minimum=1, maximum=120),
  # --- Desktop control -----------------------------------------------------------------
  Field("desktop.enabled", "Let Ultron open apps and websites", "bool", "control", lambda s: s.desktop.enabled),
  Field("desktop.allow_input", "Let Ultron type and click", "bool", "control", lambda s: s.desktop.allow_input),
  # --- Developer -----------------------------------------------------------------------
  # --- Skills (applied at once) ---------------------------------------------------
  Field("skills.enabled", "Use installed skills", "bool", "skills", lambda s: s.skills.enabled, restart=False),
  Field("skills.auto_use", "Pick a matching skill automatically", "bool", "skills", lambda s: s.skills.auto_use,
        help='Off: skills run only when asked, like "/pdf merge a.pdf b.pdf".', restart=False),
  Field("skills.max_chars", "Skill instructions sent to the AI", "int", "skills", lambda s: s.skills.max_chars,
        minimum=1000, maximum=40000, step=1000, help="Characters. More is more complete but slower.",
        restart=False),
  Field("skills.context_window", "AI context size with a skill", "int", "skills",
        lambda s: s.skills.context_window, minimum=2048, maximum=131072, step=2048,
        help="Tokens. 8192 fits most skills; bigger needs more memory.", restart=False),
  Field("skills.script_timeout", "Script time limit", "int", "skills", lambda s: s.skills.script_timeout,
        minimum=5, maximum=3600, step=5, help="Seconds an approved script may run.", restart=False),
  Field("voice.warmup", "Pre-load voice models at start", "bool", "developer", lambda s: s.voice.warmup),
  Field("memory.background_encoding", "Save memories in the background", "bool", "developer",
        lambda s: s.memory.background_encoding),
  Field("context.log_latency", "Log response timings", "bool", "developer", lambda s: s.context.log_latency),
]


def fields_for(category: str) -> list[Field]:
  return [f for f in FIELDS if f.category == category]


def field_by_path(path: str) -> Field:
  for f in FIELDS:
    if f.path == path:
      return f
  raise KeyError(path)
