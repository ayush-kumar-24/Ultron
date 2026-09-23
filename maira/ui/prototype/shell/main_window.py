"""Prototype main window — premium shell; optional Container for live backend."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from maira.app.container import Container
from maira.ui.prototype.components.primitives import ToastHost
from maira.ui.prototype.mock.store import MockStore
from maira.ui.prototype.onboarding.flow import OnboardingFlow
from maira.ui.prototype.overlays.palette import CommandPalette, SearchOverlay
from maira.ui.prototype.screens.activity import ActivityScreen
from maira.ui.prototype.screens.automations import AutomationsScreen
from maira.ui.prototype.screens.chat import ChatScreen
from maira.ui.prototype.screens.home import HomeScreen
from maira.ui.prototype.screens.memory import MemoryScreen
from maira.ui.prototype.screens.notes import NotesScreen
from maira.ui.prototype.screens.settings import SettingsScreen
from maira.ui.prototype.screens.tasks import TasksScreen
from maira.ui.prototype.shell.sidebar import Sidebar


class PrototypeWindow(QMainWindow):
  def __init__(
    self,
    store: MockStore | None = None,
    container: Container | None = None,
    *,
    skip_onboarding: bool = False,
  ) -> None:
    super().__init__()
    self.store = store or MockStore()
    self._container = container
    self.setWindowTitle("Ultron")
    self.resize(1280, 800)
    self.setMinimumSize(1100, 700)

    self.root = QWidget()
    self.root.setObjectName("ProtoRoot")
    self.setCentralWidget(self.root)
    self.root_layout = QHBoxLayout(self.root)
    self.root_layout.setContentsMargins(0, 0, 0, 0)
    self.root_layout.setSpacing(0)

    self.shell = QWidget()
    shell_layout = QHBoxLayout(self.shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)

    self.sidebar = Sidebar()
    self.sidebar.navigate.connect(self.navigate)
    shell_layout.addWidget(self.sidebar)

    self.workspace = QWidget()
    self.workspace.setObjectName("Workspace")
    workspace_layout = QHBoxLayout(self.workspace)
    workspace_layout.setContentsMargins(0, 0, 0, 0)

    self.stack = QStackedWidget()
    self.screens = {
      "home": HomeScreen(self.store),
      "chat": ChatScreen(self.store),
      "memory": MemoryScreen(self.store),
      "tasks": TasksScreen(self.store),
      "notes": NotesScreen(self.store),
      "activity": ActivityScreen(self.store),
      "automations": AutomationsScreen(self.store),
      "settings": SettingsScreen(self.store),
    }
    for key in ("home", "chat", "memory", "tasks", "notes", "activity", "automations", "settings"):
      self.stack.addWidget(self.screens[key])
    workspace_layout.addWidget(self.stack)
    shell_layout.addWidget(self.workspace, stretch=1)

    self.onboarding = OnboardingFlow(self.store)
    self.onboarding.finished.connect(self._finish_onboarding)

    self.root_stack = QStackedWidget()
    self.root_stack.addWidget(self.shell)
    self.root_stack.addWidget(self.onboarding)
    self.root_layout.addWidget(self.root_stack)

    self.palette = CommandPalette(self.store, self.root)
    self.search = SearchOverlay(self.store, self.root)
    self.toast = ToastHost(self.root)

    self.screens["home"].command.connect(self._home_command)
    self.screens["home"].quick_action.connect(self._quick_action)
    self.screens["home"].voice.connect(self.open_voice)
    self.palette.activated.connect(self._run_command)
    self.search.result_chosen.connect(self._search_result)
    self.store.toast.connect(self.toast.show_toast)
    self.store.changed.connect(self._on_store)

    self._bridges: list = []
    self._voice_ptt_active = False
    self._close_handler: Callable[[], bool] | None = None
    if container is not None:
      self._wire_backend(container)

    self._wire_shortcuts()
    self.installEventFilter(self)
    if skip_onboarding or container is not None:
      self.store.profile["onboarded"] = True
    self._apply_onboarding_gate()
    self.navigate("chat")

  def _wire_backend(self, container: Container) -> None:
    from maira.ui.prototype.integration.automation_bridge import ProtoAutomationBridge
    from maira.ui.prototype.integration.chat_bridge import ProtoChatBridge
    from maira.ui.prototype.integration.memory_bridge import ProtoMemoryBridge
    from maira.ui.prototype.integration.planner_bridge import ProtoPlannerBridge
    from maira.ui.prototype.integration.voice_bridge import ProtoVoiceBridge

    brain = container.resolve("brain")
    event_bus = container.resolve("event_bus")
    llm = container.resolve("llm")
    planner = container.resolve("planner")
    memory = container.resolve("memory")
    voice = container.resolve("voice")
    automation = container.resolve("automation")
    settings = container.resolve("settings")

    # Prefer real profile name from settings if present
    self.store.profile["name"] = getattr(settings.app, "name", None) or "Ayush"
    if self.store.profile["name"] == "Ultron":
      self.store.profile["name"] = "Ayush"
    self.sidebar.set_profile_initial(self.store.greeting_name())

    chat = self.screens["chat"]
    self._bridges.append(
      ProtoChatBridge(brain, event_bus, chat, model_name=settings.ollama.model)
    )
    self._bridges.append(ProtoPlannerBridge(planner, self.screens["tasks"], self.screens["notes"], event_bus))
    self._bridges.append(ProtoMemoryBridge(memory, self.screens["memory"]))
    self._bridges.append(ProtoVoiceBridge(voice, event_bus, chat))

    runner = container.resolve("automation_runner")
    auto_bridge = ProtoAutomationBridge(
      automation,
      event_bus,
      self.screens["automations"],
      runner,
      toast=self.store.toast.emit,
    )
    self._bridges.append(auto_bridge)
    event_bus.subscribe(
      "automation.notify",
      lambda p: self.store.toast.emit(str(p.get("message", "Automation"))),
    )
    runner.start()

    if not llm.is_available():
      chat.show_ollama_error()

    # System status reflects real readiness
    self.store.set_status_offline(not llm.is_available())
    for item in self.store.status:
      if item["id"] == "voice":
        item["state"] = "Ready" if voice.is_available() else "Offline"
      if item["id"] == "memory":
        item["state"] = "Ready"
      if item["id"] == "automation":
        item["state"] = "Ready"
    try:
      from maira.modules.voice.diagnostics import collect_diagnostics

      diag = collect_diagnostics(container)
      self.store.settings.setdefault("developer", {})["diag_snapshot"] = "\n".join(diag.as_lines())
    except Exception:  # noqa: BLE001
      pass
    self.store.changed.emit("status")

  def set_close_handler(self, handler: Callable[[], bool] | None) -> None:
    """Handler returns True to hide the window instead of closing (tray mode)."""
    self._close_handler = handler

  def closeEvent(self, event) -> None:  # noqa: N802
    # Never veto a Windows sign-out / shutdown: let the window close normally.
    saving_session = QApplication.instance() is not None and QApplication.instance().isSavingSession()
    if not saving_session and self._close_handler is not None and self._close_handler():
      chat = self.screens["chat"]
      if chat.dictating or chat.voice_mode:
        chat.set_voice_mode(False)
      event.ignore()
      self.hide()
      return
    super().closeEvent(event)

  def bring_to_front(self) -> None:
    if self.isMinimized():
      self.showNormal()
    else:
      self.show()
    self.raise_()
    self.activateWindow()

  def resizeEvent(self, event) -> None:  # noqa: N802
    super().resizeEvent(event)
    for overlay in (self.palette, self.search, self.toast):
      overlay.setGeometry(self.root.rect())

  def _wire_shortcuts(self) -> None:
    QShortcut(QKeySequence("Ctrl+K"), self, self.open_palette)
    QShortcut(QKeySequence("Ctrl+Space"), self, self._focus_command)
    QShortcut(QKeySequence("Ctrl+Shift+M"), self, lambda: self.navigate("memory"))
    QShortcut(QKeySequence("Ctrl+Shift+T"), self, lambda: self.navigate("tasks"))
    # Ctrl+Shift+V hold-to-dictate; Alt+V toggles mic dictation.
    QShortcut(QKeySequence("Alt+V"), self, self.open_voice)
    QShortcut(QKeySequence("Ctrl+F"), self, self.open_search)
    QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._escape)

  def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
    if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
      key_event = event  # type: ignore[assignment]
      mods = key_event.modifiers()
      is_ptt = (
        key_event.key() == Qt.Key.Key_V
        and bool(mods & Qt.KeyboardModifier.ControlModifier)
        and bool(mods & Qt.KeyboardModifier.ShiftModifier)
      )
      if is_ptt and self._container is not None:
        if event.type() == QEvent.Type.KeyPress and not key_event.isAutoRepeat():
          self._ptt_press()
          return True
        if event.type() == QEvent.Type.KeyRelease and not key_event.isAutoRepeat():
          self._ptt_release()
          return True
    return super().eventFilter(obj, event)

  def _ptt_press(self) -> None:
    if self._container is None or self._voice_ptt_active:
      return
    self.navigate("chat")
    try:
      voice = self._container.resolve("voice")
      start = getattr(voice, "start_dictation", None)
      if callable(start):
        start()
      else:
        voice.start_listening()
      self._voice_ptt_active = True
      self.screens["chat"].set_dictating(True)
    except Exception:  # noqa: BLE001
      self._voice_ptt_active = False

  def _ptt_release(self) -> None:
    if self._container is None or not self._voice_ptt_active:
      return
    self._voice_ptt_active = False
    try:
      from maira.shared.utils.async_bridge import run_in_thread

      voice = self._container.resolve("voice")
      self.screens["chat"].input.set_placeholder("Transcribing...")
      stop = getattr(voice, "stop_dictation", None)
      run_in_thread(self, stop if callable(stop) else voice.stop_listening)
    except Exception:  # noqa: BLE001
      self.screens["chat"].set_dictating(False)

  def _apply_onboarding_gate(self) -> None:
    if self.store.profile.get("onboarded"):
      self.root_stack.setCurrentWidget(self.shell)
    else:
      self.root_stack.setCurrentWidget(self.onboarding)

  def _finish_onboarding(self) -> None:
    self.root_stack.setCurrentWidget(self.shell)
    self.sidebar.set_profile_initial(self.store.greeting_name())
    self.navigate("chat")
    self.store.toast.emit(f"Welcome, {self.store.greeting_name()}")

  def _on_store(self, key: str) -> None:
    if key == "profile":
      self.sidebar.set_profile_initial(self.store.greeting_name())

  def navigate(self, key: str) -> None:
    if key not in self.screens:
      return
    chat = self.screens["chat"]
    if key != "chat" and (chat.voice_mode or chat.dictating):
      chat.set_voice_mode(False)
    index = list(self.screens.keys()).index(key)
    self.stack.setCurrentIndex(index)
    self.sidebar.set_active(key)

  def open_palette(self) -> None:
    if self.root_stack.currentWidget() is self.onboarding:
      return
    self.search.hide()
    self.palette.setGeometry(self.root.rect())
    self.palette.open()

  def open_search(self) -> None:
    if self.root_stack.currentWidget() is self.onboarding:
      return
    self.palette.hide()
    self.search.setGeometry(self.root.rect())
    self.search.open()

  def open_voice(self) -> None:
    if self.root_stack.currentWidget() is self.onboarding:
      return
    self.navigate("chat")
    self.screens["chat"].toggle_dictation()

  def _escape(self) -> None:
    chat = self.screens["chat"]
    if chat.dictating or chat.voice_mode:
      chat.set_voice_mode(False)
    elif self.palette.isVisible():
      self.palette.close_overlay()
    elif self.search.isVisible():
      self.search.close_overlay()

  def _focus_command(self) -> None:
    self.navigate("chat")
    if self.screens["chat"].dictating or self.screens["chat"].voice_mode:
      self.screens["chat"].set_voice_mode(False)
    self.screens["chat"].input.focus_input()

  def _home_command(self, display: str, prompt: str = "") -> None:
    self.navigate("chat")
    chat = self.screens["chat"]
    if chat._live:  # noqa: SLF001
      chat.send_requested.emit(display, prompt or display)
    else:
      chat._mock_send(display)  # noqa: SLF001

  def _quick_action(self, action_id: str) -> None:
    mapping = {
      "workspace": ("automations", "Opening Morning Workspace (mock)"),
      "plan": ("tasks", "Planning your day (mock)"),
      "search": (None, None),
      "pending": ("tasks", "Here's what's pending"),
    }
    if action_id == "search":
      self.open_search()
      return
    target, toast = mapping.get(action_id, ("chat", "Done"))
    if target:
      self.navigate(target)
    if toast:
      self.store.toast.emit(toast)

  def _run_command(self, cmd_id: str) -> None:
    routes = {
      "workspace": "automations",
      "plan": "tasks",
      "memory": "memory",
      "task": "tasks",
      "note": "notes",
      "settings": "settings",
      "status": "settings",
    }
    if cmd_id == "voice":
      self.open_voice()
      return
    if cmd_id == "search":
      self.open_search()
      return
    if cmd_id == "error_demo":
      self.navigate("chat")
      self.screens["chat"].show_ollama_error()
      return
    if cmd_id == "task":
      self.navigate("tasks")
      self.screens["tasks"]._add()  # noqa: SLF001
      return
    if cmd_id == "note":
      self.navigate("notes")
      self.screens["notes"]._add()  # noqa: SLF001
      return
    if cmd_id == "status":
      self.navigate("settings")
      self.screens["settings"].show_category("status")
      return
    if cmd_id in routes:
      self.navigate(routes[cmd_id])

  def _search_result(self, category: str, _text: str) -> None:
    route = {
      "Conversations": "chat",
      "Memory": "memory",
      "Notes": "notes",
      "Tasks": "tasks",
      "Files": "chat",
    }.get(category, "chat")
    self.navigate(route)
    self.store.toast.emit(f"Opened {category}")
