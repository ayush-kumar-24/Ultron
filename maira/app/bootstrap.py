"""Application bootstrap sequence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from typing import TYPE_CHECKING

from loguru import logger

from maira.app.container import Container
from maira.app.lifecycle import Lifecycle
from maira.app.settings import Settings, load_settings
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.embeddings.sentence_transformers.encoder import (
  SentenceTransformerEncoder,
)
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.logging.loguru_setup import setup_logging
from maira.infrastructure.persistence.sqlite.connection import SqliteStorage
from maira.infrastructure.persistence.sqlite.migrations import apply_migrations
from maira.infrastructure.persistence.sqlite.repositories import (
  AutomationRunRepository,
  GoalRepository,
  KnowledgeRepository,
  ProjectRepository,
  CalendarEventRepository,
  NotificationRepository,
  AutomationRepository,
  ConversationRepository,
  MemoryRepository,
  NoteRepository,
  TaskRepository,
)
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.kokoro.engine import KokoroEngine
from maira.infrastructure.speech.whisper.engine import WhisperEngine
from maira.infrastructure.vector.chromadb.collections import ChromaVectorStore
from maira.modules.automation.executor import AutomationExecutor
from maira.modules.automation.scheduler import AutomationScheduler
from maira.modules.automation.service import AutomationService
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.service import BrainService
from maira.modules.desktop_controller.service import DesktopControllerService
from maira.modules.vision.service import VisionService
from maira.modules.memory.policy import MemoryPolicy
from maira.modules.memory.service import MemoryService
from maira.modules.memory.worker import MemoryWorker
from maira.modules.planner.service import PlannerService
from maira.modules.voice.service import VoiceService
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.stt.registry import create_stt, ensure_default_stt_providers
from maira.modules.voice.tts import TextToSpeech
from maira.modules.voice.tts.registry import create_tts, ensure_default_tts_providers
from maira.shared.utils.paths import database_path, project_root

if TYPE_CHECKING:  # Qt types are only needed for annotations here.
  from PySide6.QtWidgets import QApplication

  from maira.ui.presence.runtime import PresenceRuntime
  from maira.ui.prototype.shell.main_window import PrototypeWindow as MainWindow


@dataclass
class Runtime:
  container: Container
  lifecycle: Lifecycle
  settings: Settings


@dataclass
class AppContext:
  qt_app: "QApplication"
  container: Container
  lifecycle: Lifecycle
  window: "MainWindow"
  presence: "PresenceRuntime | None"


def _resolve_chroma_path(settings: Settings) -> Path:
  configured = Path(settings.memory.chroma_path)
  if configured.is_absolute():
    return configured
  return project_root() / configured


def _build_memory_service(settings: Settings, memory_repository: MemoryRepository) -> MemoryService:
  encoder = None
  vector_store = None
  try:
    encoder = SentenceTransformerEncoder(settings.memory.embedding_model)
    vector_store = ChromaVectorStore(_resolve_chroma_path(settings))
    if encoder.is_available() and vector_store.is_available():
      logger.info("Semantic memory enabled ({})", settings.memory.embedding_model)
    else:
      logger.warning("Semantic memory libraries present but unavailable; using keyword search")
      encoder = None
      vector_store = None
  except Exception as exc:  # noqa: BLE001
    logger.warning("Semantic memory disabled (install memory extras): {}", exc)
    encoder = None
    vector_store = None

  return MemoryService(memory_repository, encoder=encoder, vector_store=vector_store)


def _build_vision_service(settings: Settings, event_bus) -> VisionService:
  """Screen capture + OCR. Adapters load lazily, so missing deps are not fatal."""
  from maira.infrastructure.screen.mss_capture import MssScreenCapture
  from maira.infrastructure.screen.winocr_reader import WinOcrScreenReader

  return VisionService(
    MssScreenCapture(),
    WinOcrScreenReader(lang=settings.vision.ocr_lang),
    enabled=settings.vision.enabled,
    bus=event_bus,
    max_text_chars=settings.vision.max_text_chars,
  )


def _register_services(container: Container, settings: Settings, lifecycle: Lifecycle) -> None:
  event_bus = EventBus()
  container.register_instance("event_bus", event_bus)
  container.register_instance("settings", settings)

  storage = SqliteStorage(database_path())
  apply_migrations(storage)
  conversation_repository = ConversationRepository(storage)
  task_repository = TaskRepository(storage)
  note_repository = NoteRepository(storage)
  memory_repository = MemoryRepository(storage)
  automation_repository = AutomationRepository(storage)
  container.register_instance("storage", storage)
  container.register_instance("conversation_repository", conversation_repository)
  container.register_instance("task_repository", task_repository)
  container.register_instance("note_repository", note_repository)
  container.register_instance("memory_repository", memory_repository)
  container.register_instance("automation_repository", automation_repository)
  calendar_repository = CalendarEventRepository(storage)
  notification_repository = NotificationRepository(storage)
  automation_run_repository = AutomationRunRepository(storage)
  container.register_instance("calendar_repository", calendar_repository)
  container.register_instance("notification_repository", notification_repository)
  container.register_instance("automation_run_repository", automation_run_repository)
  container.register_instance("project_repository", ProjectRepository(storage))
  container.register_instance("goal_repository", GoalRepository(storage))
  container.register_instance("knowledge_repository", KnowledgeRepository(storage))
  container.register_instance("planner", PlannerService(task_repository, note_repository))
  automation = AutomationService(automation_repository)
  container.register_instance("automation", automation)
  desktop = DesktopControllerService(
    enabled=settings.desktop.enabled,
    allow_input=settings.desktop.allow_input,
  )
  container.register_instance("desktop", desktop)
  container.register_instance("vision", _build_vision_service(settings, event_bus))
  memory = _build_memory_service(settings, memory_repository)
  container.register_instance("memory", memory)

  memory_worker = MemoryWorker(
    memory if settings.memory.background_encoding else None,
    MemoryPolicy(),
  )
  if settings.memory.background_encoding:
    memory_worker.start()
    lifecycle.on_shutdown(memory_worker.stop)
  container.register_instance("memory_worker", memory_worker)

  lifecycle.on_shutdown(storage.close)

  def llm_factory() -> OllamaClient:
    client = OllamaClient(
      host=settings.ollama.host,
      model=settings.ollama.model,
      timeout_seconds=settings.ollama.timeout_seconds,
      keep_alive=settings.ollama.keep_alive,
    )
    lifecycle.on_shutdown(client.close)
    return client

  container.register("llm", llm_factory)

  def brain_factory() -> BrainService:
    return BrainService(
      llm=container.resolve("llm"),
      event_bus=container.resolve("event_bus"),
      repository=container.resolve("conversation_repository"),
      session=ConversationSession(),
      memory=container.resolve("memory"),
      max_memories=settings.context.max_memories,
      max_context_chars=settings.context.max_context_chars,
      history_messages=settings.context.history_messages,
      log_latency=settings.context.log_latency,
      memory_worker=container.resolve("memory_worker"),
      recall_mode=settings.memory.recall_mode,
      automation=container.resolve("automation"),
      desktop=container.resolve("desktop"),
      vision=container.resolve("vision"),
    )

  container.register("brain", brain_factory)

  def automation_runtime_factory() -> "AutomationRunner":
    # QObject-based: imported here so headless never touches Qt.
    from maira.modules.automation.runner import AutomationRunner

    automation = container.resolve("automation")
    brain = container.resolve("brain")
    desktop = container.resolve("desktop")

    def notify(message: str) -> None:
      container.resolve("event_bus").publish("automation.notify", {"message": message})

    executor = AutomationExecutor(
      automation, brain=brain, desktop=desktop, on_notify=notify
    )
    runner = AutomationRunner(automation, executor, interval_ms=5_000)
    lifecycle.on_shutdown(runner.stop)
    return runner

  container.register("automation_runner", automation_runtime_factory)

  def automation_scheduler_factory() -> AutomationScheduler:
    """Headless automations: no Qt loop, so a daemon thread polls due jobs."""
    from maira.modules.automation.scheduler import AutomationScheduler as _Scheduler

    def notify(message: str) -> None:
      event_bus.publish("automation.notify", {"message": message})

    executor = AutomationExecutor(
      container.resolve("automation"),
      brain=container.resolve("brain"),
      desktop=container.resolve("desktop"),
      on_notify=notify,
    )

    def announce(job, result) -> None:
      notification_repository.create(
        type="automation",
        title="Automation ran" if result.ok else "Automation failed",
        body=f"{job.title} — {result.message}",
      )
      automation_run_repository.record(
        job.id,
        status="done" if result.ok else "failed",
        output=result.message,
      )
      event_bus.publish(
        "automation",
        {"id": job.id, "name": job.title, "ok": result.ok, "message": result.message},
      )

    scheduler = _Scheduler(container.resolve("automation"), executor, on_job_ran=announce)
    lifecycle.on_shutdown(scheduler.stop)
    return scheduler

  container.register("automation_scheduler", automation_scheduler_factory)

  def voice_factory() -> VoiceService:
    ensure_default_stt_providers()
    ensure_default_tts_providers()
    audio = AudioStream(sample_rate=settings.voice.sample_rate)

    stt_language = settings.voice.language.strip() or None

    stt_provider = create_stt(
      settings.voice.stt_provider,
      model_size=settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
      language=stt_language,
      max_model_download_gb=settings.voice.max_model_download_gb,
      beam_size=settings.voice.whisper_beam_size,
    )
    if stt_provider.is_available()[0]:
      stt = SpeechToText.from_provider(stt_provider)
    else:
      whisper = WhisperEngine(
        model_size=settings.voice.whisper_model,
        device=settings.voice.whisper_device,
        compute_type=settings.voice.whisper_compute_type,
        beam_size=settings.voice.whisper_beam_size,
      )
      stt = SpeechToText(whisper, language=stt_language)

    tts_provider = create_tts(
      settings.voice.tts_provider,
      voice=settings.voice.tts_voice,
      lang_code=settings.voice.tts_lang,
      allow_fallback=settings.voice.allow_tts_fallback,
      max_model_download_gb=settings.voice.max_model_download_gb,
    )
    if tts_provider.is_available()[0] and hasattr(tts_provider, "_engine"):
      tts = TextToSpeech(tts_provider._engine, audio)  # noqa: SLF001
    else:
      tts_engine = KokoroEngine(
        voice=settings.voice.tts_voice,
        sample_rate=24000,
        lang_code=settings.voice.tts_lang,
        allow_fallback=settings.voice.allow_tts_fallback,
      )
      tts = TextToSpeech(tts_engine, audio)

    voice = VoiceService(
      brain=container.resolve("brain"),
      event_bus=container.resolve("event_bus"),
      audio=audio,
      stt=stt,
      tts=tts,
      silence_seconds=settings.voice.silence_seconds,
      max_reply_tokens=settings.voice.max_reply_tokens,
      chunk_min_chars=settings.voice.chunk_min_chars,
      chunk_max_chars=settings.voice.chunk_max_chars,
      interrupt_on_speech=settings.voice.interrupt_on_speech,
      auto_speak=settings.voice.auto_speak,
    )
    lifecycle.on_shutdown(voice.shutdown)

    if settings.voice.warmup:
      threading.Thread(
        target=voice.warm_up_models,
        name="maira-voice-warmup",
        daemon=True,
      ).start()

    return voice

  container.register("voice", voice_factory)


def build_runtime() -> Runtime:
  """Wire services. No Qt, no HTTP — both entry points call this."""
  setup_logging()
  settings = load_settings()
  container = Container()
  lifecycle = Lifecycle()
  _register_services(container, settings, lifecycle)
  return Runtime(container=container, lifecycle=lifecycle, settings=settings)


def start_api(runtime: Runtime, *, blocking: bool = False) -> None:
  """Serve the HTTP API on the shared container. Daemon thread, or block for headless."""
  if not runtime.settings.api.enabled:
    logger.info("HTTP API disabled")
    return
  from maira.api.overlay import OverlayStore
  from maira.api.server import create_app, serve_api, start_api_thread
  from maira.shared.utils.paths import data_dir

  if runtime.container.try_resolve("overlay") is None:
    runtime.container.register_instance("overlay", OverlayStore(data_dir() / "user_profile.json"))

  # Headless has no QTimer, so the thread-backed scheduler runs due automations.
  if blocking:
    runtime.container.resolve("automation_scheduler").start()

  app = create_app(runtime.container)
  if blocking:
    serve_api(app, runtime.settings, runtime.lifecycle)
    return
  start_api_thread(app, runtime.settings, runtime.lifecycle)


def run_headless() -> None:
  """Boot the container and serve the API without Qt."""
  runtime = build_runtime()
  logger.info("Starting Ultron API (headless)")
  if not runtime.settings.api.enabled:
    logger.error("api.enabled is false — nothing to serve")
    raise SystemExit(1)
  start_api(runtime, blocking=True)


def bootstrap() -> AppContext:
  # Qt is imported here, not at module scope, so `--headless` runs on machines
  # (and containers) where Qt's system libraries are not installed.
  from maira.ui.application import create_qt_application
  from maira.ui.presence.runtime import PresenceRuntime
  from maira.ui.prototype.shell.main_window import PrototypeWindow as MainWindow

  runtime = build_runtime()
  logger.info("Starting Maira")
  start_api(runtime, blocking=False)

  qt_app = create_qt_application(runtime.settings)
  window = MainWindow(container=runtime.container, skip_onboarding=True)

  presence: "PresenceRuntime | None" = None
  if runtime.settings.presence.enabled:
    presence = PresenceRuntime(
      window,
      runtime.container.resolve("event_bus"),
      runtime.settings.presence,
      qt_app,
    )
    presence.start()
    runtime.lifecycle.on_shutdown(presence.shutdown)
  else:
    window.show()

  runtime.lifecycle.on_shutdown(lambda: logger.info("Maira shutdown complete"))

  return AppContext(
    qt_app=qt_app,
    container=runtime.container,
    lifecycle=runtime.lifecycle,
    window=window,
    presence=presence,
  )
