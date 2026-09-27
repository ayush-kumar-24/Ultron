"""MainWindow widget — sidebar, content area, and status bar."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QWidget

from maira.app.container import Container
from maira.ui.controllers.chat_controller import ChatController
from maira.ui.controllers.memory_controller import MemoryController
from maira.ui.controllers.planner_controller import PlannerController
from maira.ui.controllers.voice_controller import VoiceController
from maira.ui.views.chat import ChatView
from maira.ui.views.memory import MemoryView
from maira.ui.views.planner import PlannerView
from maira.ui.views.voice import VoiceView


class PlaceholderView(QWidget):
  def __init__(self, title: str, parent=None) -> None:
    super().__init__(parent)
    layout = QHBoxLayout(self)
    label = QLabel(f"{title} — coming soon")
    label.setStyleSheet("color: #6c7086; font-size: 15px;")
    layout.addWidget(label)


class MainWindow(QMainWindow):
  def __init__(self, container: Container, parent=None) -> None:
    super().__init__(parent)
    self._container = container
    self.setWindowTitle("Ultron")
    self.resize(1100, 720)
    self._build_ui()
    self._wire_services()

  def _build_ui(self) -> None:
    central = QWidget()
    self.setCentralWidget(central)
    layout = QHBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    self._nav = QListWidget()
    self._nav.setFixedWidth(180)
    for label in ("Chat", "Planner", "Memory", "Voice", "Settings"):
      self._nav.addItem(label)

    self._stack = QStackedWidget()
    self._chat_view = ChatView()
    self._planner_view = PlannerView()
    self._memory_view = MemoryView()
    self._voice_view = VoiceView()
    self._stack.addWidget(self._chat_view)
    self._stack.addWidget(self._planner_view)
    self._stack.addWidget(self._memory_view)
    self._stack.addWidget(self._voice_view)
    self._stack.addWidget(PlaceholderView("Settings"))

    self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
    self._nav.setCurrentRow(0)

    layout.addWidget(self._nav)
    layout.addWidget(self._stack, stretch=1)

  def _wire_services(self) -> None:
    brain = self._container.resolve("brain")
    llm = self._container.resolve("llm")
    event_bus = self._container.resolve("event_bus")
    planner = self._container.resolve("planner")
    memory = self._container.resolve("memory")
    voice = self._container.resolve("voice")

    settings = self._container.resolve("settings")
    self._chat_controller = ChatController(
      brain,
      event_bus,
      self._chat_view,
      show_context_debug=settings.context.show_debug,
      model_name=settings.ollama.model,
    )
    self._planner_controller = PlannerController(planner, self._planner_view, memory=memory)
    self._memory_controller = MemoryController(memory, self._memory_view)
    self._voice_controller = VoiceController(voice, event_bus, self._voice_view)

    if not llm.is_available():
      self._chat_view.show_error("Ultron can't reach the local AI model.")
