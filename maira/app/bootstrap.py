"""Application bootstrap sequence."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading

from typing import TYPE_CHECKING

from loguru import logger

from maira.app.container import Container
from maira.app.restart import restart_app
from maira.app.lifecycle import Lifecycle
from maira.app.settings import Settings, load_settings
from maira.app.single_instance import SingleInstanceGuard
from maira.core.bus.event_bus import EventBus
from maira.infrastructure.embeddings.sentence_transformers.encoder import (
  SentenceTransformerEncoder,
)
from maira.infrastructure.llm.ollama.client import OllamaClient
from maira.infrastructure.logging.loguru_setup import setup_logging
from maira.infrastructure.notifications.toast_process import ToastProcessNotifier
from maira.infrastructure.os.autostart import BACKGROUND_FLAG, AutostartManager
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
from maira.infrastructure.persistence.sqlite.repositories.intelligence import (
  AgentExecutionRepository,
  ResearchRepository,
  WorkSessionRepository,
)
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.infrastructure.speech.kokoro.engine import KokoroEngine
from maira.infrastructure.speech.windows.sapi import WindowsSpeech
from maira.infrastructure.speech.whisper.engine import WhisperEngine
from maira.infrastructure.vector.chromadb.collections import ChromaVectorStore
from maira.modules.automation.executor import AutomationExecutor
from maira.modules.automation.parser import LOCAL_TZ
from maira.modules.automation.runner import AutomationRunner
from maira.modules.automation.scheduler import AutomationScheduler
from maira.modules.automation.service import AutomationService
from maira.modules.brain.conversation import ConversationSession
from maira.modules.brain.service import BrainService
from maira.modules.desktop_controller.service import DesktopControllerService
from maira.modules.vision.service import VisionService
from maira.modules.memory.policy import MemoryPolicy
from maira.modules.memory.service import MemoryService
from maira.modules.memory.worker import MemoryWorker
from maira.modules.notifications.service import NotificationService
from maira.modules.orchestration.orchestrator import Orchestrator
from maira.modules.orchestration.registry import AgentRegistry
from maira.modules.orchestration.wiring import register_agents, subscribe_activity
from maira.modules.research.service import ResearchService
from maira.modules.planner.briefing import Briefing, BriefingService
from maira.modules.agent.service import AgentService
from maira.modules.skills.service import SkillService
from maira.modules.skills.store import SkillStore
from maira.modules.planner.briefing.runner import BriefingRunner
from maira.modules.planner.briefing.schedule import BriefingSchedule, parse_clock
from maira.modules.planner.reminders import LinkedPlanner
from maira.modules.planner.service import PlannerService
from maira.modules.voice.service import VoiceService
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.stt.registry import create_stt, ensure_default_stt_providers
from maira.modules.voice.tts import TextToSpeech
from maira.modules.voice.tts.registry import create_tts, ensure_default_tts_providers
from maira.shared.utils.paths import data_dir, database_path, project_root
from maira.ui.application import create_qt_application
from maira.ui.prototype.shell.main_window import PrototypeWindow as MainWindow
if TYPE_CHECKING:
  from PySide6.QtWidgets import QApplication

from maira.ui.system_tray import (
  NotificationActionRelay,
  TrayBalloonNotifier,
  TrayController,
  app_icon,
  export_icon_files,
)


@dataclass
class Runtime:
  """Wired services, with no Qt and no HTTP. Both entry points build on this."""

  container: Container
  lifecycle: Lifecycle
  settings: Settings


@dataclass
class AppContext:
  qt_app: "QApplication"
  container: Container
  lifecycle: Lifecycle
  window: MainWindow
  tray: TrayController | None = None


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


class _AnnouncingExecutor:
  """Wraps the executor so a run by the window's timer is recorded like any other."""

  def __init__(self, inner: AutomationExecutor, announce) -> None:
    self._inner = inner
    self._announce = announce

  def run(self, job):
    result = self._inner.run(job)
    try:
      self._announce(job, result)
    except Exception:  # noqa: BLE001 - the job itself already ran
      logger.exception("Could not record automation run")
    return result

  def __getattr__(self, name: str):
    return getattr(self._inner, name)


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
  research_repository = ResearchRepository(storage)
  execution_repository = AgentExecutionRepository(storage)
  # Anything still "running" belongs to a process that has exited.
  research_repository.fail_interrupted()
  execution_repository.fail_interrupted()
  container.register_instance("research_repository", research_repository)
  container.register_instance("agent_execution_repository", execution_repository)
  container.register_instance("work_session_repository", WorkSessionRepository(storage))
  registry = AgentRegistry(execution_repository, bus=event_bus)
  register_agents(registry, container, settings)
  container.register_instance("agent_registry", registry)

  def announce_job(job, result) -> None:
    """One automation ran (window or headless): history, a notification, and a live event."""
    created = notification_repository.create(
      type="automation",
      title="Automation ran" if result.ok else "Automation failed",
      body=f"{job.title} - {result.message}",
    )
    automation_run_repository.record(
      job.id, status="done" if result.ok else "failed", output=result.message
    )
    registry.record("automation", job.title, ok=result.ok, error=None if result.ok else result.message)
    event_bus.publish(
      "automation", {"id": job.id, "name": job.title, "ok": result.ok, "message": result.message}
    )
    event_bus.publish(
      "notification", {"id": created.id, "type": created.type, "title": created.title, "body": created.body}
    )
  automation = AutomationService(automation_repository)
  container.register_instance("automation", automation)
  # Every task change (chat, voice, Tasks screen) keeps its reminder in sync.
  container.register_instance(
    "planner",
    LinkedPlanner(
      PlannerService(task_repository, note_repository),
      automation,
      remind_at_due=settings.tasks.remind_at_due,
      roll_over_enabled=settings.tasks.roll_over,
    ),
  )
  container.register_instance(
    "briefing",
    BriefingService(container.resolve("planner"), automation, name=settings.briefing.name),
  )
  skill_store = SkillStore(data_dir() / "skills")
  container.register_instance(
    "skills",
    SkillService(
      skill_store,
      enabled=settings.skills.enabled,
      auto_use=settings.skills.auto_use,
      max_chars=settings.skills.max_chars,
      context_window=settings.skills.context_window,
      script_timeout=settings.skills.script_timeout,
    ),
  )
  container.register_instance(
    "notifications",
    NotificationService(
      automation,
      event_bus=event_bus,
      snooze_minutes=settings.notifications.snooze_minutes,
      local_tz=LOCAL_TZ,
    ),
  )
  desktop = DesktopControllerService(
    enabled=settings.desktop.enabled,
    allow_input=settings.desktop.allow_input,
  )
  container.register_instance("desktop", desktop)
  container.register_instance("vision", _build_vision_service(settings, event_bus))
  memory = _build_memory_service(settings, memory_repository)
  container.register_instance("memory", memory)
  subscribe_activity(registry, event_bus, memory)

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
      planner=container.resolve("planner"),
      briefing=container.resolve("briefing"),
      skills=container.resolve("skills"),
      agent=container.resolve("agent"),
      context_window=settings.skills.context_window,
      vision=container.resolve("vision"),
    )

  container.register("brain", brain_factory)
  container.register(
    "research",
    lambda: ResearchService(
      research_repository,
      container.resolve("llm"),
      knowledge=container.resolve("knowledge_repository"),
      memory=container.resolve("memory"),
      conversations=conversation_repository,
      bus=event_bus,
    ),
  )
  container.register(
    "orchestrator",
    lambda: Orchestrator(
      registry,
      container.resolve("llm"),
      knowledge=container.resolve("knowledge_repository"),
      memory=container.resolve("memory"),
      conversations=conversation_repository,
    ),
  )
  container.register("agent", lambda: _build_agent(container, settings))

  def automation_runtime_factory() -> "AutomationRunner":
    # QObject-based: imported here so headless never touches Qt.
    from maira.modules.automation.runner import AutomationRunner

    automation = container.resolve("automation")
    brain = container.resolve("brain")
    desktop = container.resolve("desktop")

    def notify(message: str) -> None:
      container.resolve("event_bus").publish("automation.notify", {"message": message})

    def remind(job, message: str) -> None:
      if settings.notifications.enabled:
        container.resolve("notifications").remind(job, message)
      notify(f"Reminder: {message}")
      created = notification_repository.create(type="reminder", title="Reminder", body=message)
      event_bus.publish(
        "notification", {"id": created.id, "type": "reminder", "title": created.title, "body": message}
      )

    executor = AutomationExecutor(
      automation, brain=brain, desktop=desktop, on_notify=notify, on_reminder=remind
    )
    runner = AutomationRunner(automation, _AnnouncingExecutor(executor, announce_job), interval_ms=5_000)
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

    scheduler = _Scheduler(container.resolve("automation"), executor, on_job_ran=announce_job)
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
      device=settings.voice.tts_device,
      language=settings.voice.tts_language,
      reference_audio=settings.voice.tts_reference_audio,
      speaker=settings.voice.tts_speaker,
      exaggeration=settings.voice.tts_exaggeration,
    )
    available, reason = tts_provider.is_available()
    if available and hasattr(tts_provider, "_engine"):
      engine = tts_provider._engine  # noqa: SLF001
      logger.info("Voice: {}", tts_provider.get_provider_name())
      if hasattr(engine, "close"):
        lifecycle.on_shutdown(engine.close)
      tts = TextToSpeech(engine, audio)
    else:
      if settings.voice.tts_provider != "kokoro":
        logger.warning("Voice '{}' unavailable ({}); using Kokoro", settings.voice.tts_provider, reason)
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
      announcement_fallback=WindowsSpeech(),
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


def _build_agent(container: Container, settings: Settings) -> AgentService:
  """The action agent. Folders and the Gmail address are re-read from Settings for every task."""
  from maira.app.secrets import get_secret  # noqa: PLC0415
  from maira.app.user_config import UserConfig  # noqa: PLC0415
  from maira.modules.agent.actions import ActionTools, Contacts  # noqa: PLC0415
  from maira.modules.agent.files import FileAccess, default_folders  # noqa: PLC0415

  def files() -> FileAccess:
    chosen = UserConfig().get("agent.folders") or list(settings.agent.folders)
    if isinstance(chosen, str):
      chosen = chosen.split(";")
    folders = [Path(f) for f in chosen if str(f).strip()] or default_folders()
    return FileAccess(folders, data_dir())

  def tools():
    access = files()
    desktop = container.resolve("desktop") if settings.desktop.enabled else None
    actions = ActionTools(
      access,
      Contacts(data_dir() / "contacts.json"),
      desktop=desktop,
      email_address=lambda: str(UserConfig().get("agent.email_address") or settings.agent.email_address),
      email_password=lambda: get_secret("gmail_app_password"),
    )
    return access.tools() + actions.tools()

  llm: OllamaClient = container.resolve("llm")
  options = {"num_ctx": settings.skills.context_window, "temperature": 0.2}
  return AgentService(
    lambda model, messages, schemas: llm.chat_tools(messages, schemas, model=model, options=options),
    tools,
    folders=lambda: files().describe_roots(),
    model=settings.agent.model,
    enabled=settings.agent.enabled,
    auto_detect=settings.agent.auto_detect,
    max_steps=settings.agent.max_steps,
    user_name=lambda: settings.briefing.name,
  )


def _setup_background(
  qt_app: QApplication,
  container: Container,
  settings: Settings,
  window: MainWindow,
  lifecycle: Lifecycle,
) -> TrayController | None:
  """Tray icon, close-to-tray, Start with Windows, and OS reminder pop-ups."""
  icon = app_icon()
  qt_app.setWindowIcon(icon)
  window.setWindowIcon(icon)

  tray: TrayController | None = None
  if TrayController.is_supported():
    autostart: AutostartManager = container.resolve("autostart")
    autostart.refresh()
    tray = TrayController(icon, app_name=settings.app_name, autostart=autostart)
    tray.open_requested.connect(window.bring_to_front)
    tray.quit_requested.connect(qt_app.quit)
    tray.show()
    logger.info("Tray icon ready")
    lifecycle.on_shutdown(tray.hide)
    if settings.background.close_to_tray:

      def hide_to_tray() -> bool:
        tray.show_background_hint_once()
        return True

      window.set_close_handler(hide_to_tray)
      qt_app.setQuitOnLastWindowClosed(False)
  else:
    logger.warning("System tray unavailable; Ultron will quit when the window closes")

  notifications: NotificationService = container.resolve("notifications")
  notifications.set_open_handler(window.bring_to_front)
  if not settings.notifications.enabled:
    return tray

  event_bus: EventBus = container.resolve("event_bus")

  def on_action(notification_id: str, action: str) -> None:
    message = notifications.handle_action(notification_id, action)
    if message:
      event_bus.publish("automation.notify", {"message": message})

  relay = NotificationActionRelay(on_action, parent=qt_app)
  # Rejected toasts are reported on a background thread; retry on the main thread.
  failure_relay = NotificationActionRelay(
    lambda notification_id, backend: notifications.retry_without(notification_id, backend),
    parent=qt_app,
  )
  if settings.notifications.windows_toast and os.name == "nt":
    icons = export_icon_files(data_dir() / "assets")
    # Toasts run in a helper process: pywinrt and Qt crash in one process.
    toast_notifier = ToastProcessNotifier(
      relay.post,
      app_name=settings.app_name,
      icon_path=icons.ico if icons else None,
      image_path=icons.png if icons else None,
      on_failed=lambda notification_id: failure_relay.post(notification_id, "windows-toast"),
    )
    lifecycle.on_shutdown(toast_notifier.close)
    notifications.add_notifier(toast_notifier)
  if tray is not None:
    notifications.add_notifier(TrayBalloonNotifier(tray))

    def send_test() -> None:
      backend = notifications.send_test()
      if backend is None:
        tray.show_message("Ultron", "Couldn't show a Windows notification — see data/logs/maira.log")

    tray.test_notification_requested.connect(send_test)
  if not notifications.has_backend():
    logger.warning("No OS notification backend; reminders show inside the app only")
  return tray


def _setup_briefing(
  container: Container,
  settings: Settings,
  lifecycle: Lifecycle,
  tray: TrayController | None,
) -> None:
  """Show the daily briefing once a day in chat, as a notification, and aloud."""
  from datetime import time  # noqa: PLC0415

  briefing: BriefingService = container.resolve("briefing")
  schedule = BriefingSchedule(
    data_dir() / "briefing_state.json",
    at=parse_clock(settings.briefing.time, time(8, 0)),
    until=parse_clock(settings.briefing.until, time(12, 0)),
  )
  notifications: NotificationService = container.resolve("notifications")

  def deliver(item: Briefing) -> None:
    brain = container.resolve("brain")
    # Off the UI thread: the brain waits if a chat reply is still streaming.
    threading.Thread(target=brain.announce, args=(item.text,), name="ultron-briefing", daemon=True).start()
    notifications.announce("Aaj ka plan", item.summary)
    if settings.briefing.speak:
      container.resolve("voice").announce(item.speech)

  if settings.briefing.speak:
    # "plan my day" in chat or the Home button: speak the short version too.
    container.resolve("event_bus").subscribe(
      "briefing.requested",
      lambda payload: container.resolve("voice").announce(str(payload.get("speech", ""))),
    )
  if tray is not None:
    # Tray → "Today's plan": show and speak it now, any time of day.
    tray.briefing_requested.connect(lambda: deliver(briefing.build()))
  if not settings.briefing.enabled:
    return
  runner = BriefingRunner(briefing, schedule, deliver)
  runner.start()
  lifecycle.on_shutdown(runner.stop)
  container.register_instance("briefing_runner", runner)


def _setup_task_links(qt_app: QApplication, container: Container, lifecycle: Lifecycle) -> None:
  """Reminder "Done" completes its task; unfinished tasks move to today."""
  from PySide6.QtCore import QTimer  # noqa: PLC0415

  planner: LinkedPlanner = container.resolve("planner")
  event_bus: EventBus = container.resolve("event_bus")

  def on_reminder_done(payload) -> None:
    task = planner.complete_from_job((payload or {}).get("job_id"))
    if task is not None:
      event_bus.publish("planner.changed", {"reason": "reminder"})
      event_bus.publish("automation.notify", {"message": f'Task done: "{task.title}"'})

  event_bus.subscribe("notification.done", on_reminder_done)

  def roll_over() -> None:
    try:
      if planner.roll_over():
        event_bus.publish("planner.changed", {"reason": "roll_over"})
    except Exception:  # noqa: BLE001
      logger.exception("Moving unfinished tasks failed")

  roll_over()  # before the first briefing
  timer = QTimer(qt_app)
  timer.setInterval(10 * 60 * 1000)  # catches midnight within 10 minutes
  timer.timeout.connect(roll_over)
  timer.start()
  lifecycle.on_shutdown(timer.stop)


def _wire(settings: Settings, container: Container, lifecycle: Lifecycle) -> Runtime:
  _register_services(container, settings, lifecycle)
  container.register_instance("lifecycle", lifecycle)
  return Runtime(container=container, lifecycle=lifecycle, settings=settings)


def build_runtime() -> Runtime:
  """Wire services. No Qt, no HTTP - the headless entry point and tests call this."""
  setup_logging()
  return _wire(load_settings(), Container(), Lifecycle())


def start_api(runtime: Runtime, *, blocking: bool = False) -> None:
  """Serve the HTTP API on the shared container. Daemon thread, or block for headless."""
  if not runtime.settings.api.enabled:
    logger.info("HTTP API disabled")
    return
  try:
    from maira.api.overlay import OverlayStore  # noqa: PLC0415
    from maira.api.server import create_app, serve_api, start_api_thread  # noqa: PLC0415
  except ImportError as exc:
    # fastapi/uvicorn are an optional extra: the desktop app must still start without them.
    logger.warning('HTTP API unavailable ({}). Install with: pip install -e ".[api]"', exc)
    if blocking:
      raise SystemExit(1) from exc
    return

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
  """Boot the container and serve the API without a window."""
  runtime = build_runtime()
  logger.info("Starting Ultron API (headless)")
  if not runtime.settings.api.enabled:
    logger.error("api.enabled is false - nothing to serve")
    raise SystemExit(1)
  start_api(runtime, blocking=True)


def bootstrap(argv: list[str] | None = None) -> AppContext | None:
  """Build the app. Returns None when another instance is already running."""
  args = list(sys.argv[1:] if argv is None else argv)
  background = BACKGROUND_FLAG in args

  setup_logging()
  logger.info("Starting Ultron{}", " in background" if background else "")

  settings = load_settings()
  qt_app = create_qt_application(settings)

  guard = SingleInstanceGuard()
  if not guard.try_acquire():
    return None

  container = Container()
  lifecycle = Lifecycle()
  lifecycle.on_shutdown(guard.release)

  runtime = _wire(settings, container, lifecycle)
  container.register_instance("restart", lambda: restart_app(qt_app, guard))
  autostart = AutostartManager(settings.app_name)
  container.register_instance("autostart", autostart)

  # The web UI talks to the same live services as this window.
  start_api(runtime, blocking=False)

  window = MainWindow(container=container, skip_onboarding=True)
  tray = _setup_background(qt_app, container, settings, window, lifecycle)
  guard.activation_requested.connect(window.bring_to_front)
  guard.replace_requested.connect(qt_app.quit)
  _setup_task_links(qt_app, container, lifecycle)
  _setup_briefing(container, settings, lifecycle, tray)

  start_hidden = tray is not None and (background or settings.background.start_minimized)
  if not start_hidden:
    window.show()

  lifecycle.on_shutdown(lambda: logger.info("Ultron shutdown complete"))

  return AppContext(
    qt_app=qt_app, container=container, lifecycle=lifecycle, window=window, tray=tray
  )
