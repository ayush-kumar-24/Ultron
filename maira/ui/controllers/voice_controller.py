"""Voice controller — push-to-talk UI wired to VoiceService."""

from PySide6.QtCore import QObject, Qt, Signal, Slot

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.voice import Voice
from maira.modules.voice.service import (
  TOPIC_ERROR,
  TOPIC_REPLY,
  TOPIC_STATUS,
  TOPIC_TRANSCRIPT,
)
from maira.shared.utils.async_bridge import run_in_thread
from maira.ui.views.voice import VoiceView


class VoiceController(QObject):
  _status = Signal(str)
  _transcript = Signal(str)
  _reply = Signal(str)
  _error = Signal(str)

  def __init__(self, voice: Voice, event_bus: EventBus, view: VoiceView) -> None:
    super().__init__()
    self._voice = voice
    self._view = view
    self._busy = False

    event_bus.subscribe(TOPIC_STATUS, self._on_status_event)
    event_bus.subscribe(TOPIC_TRANSCRIPT, self._on_transcript_event)
    event_bus.subscribe(TOPIC_REPLY, self._on_reply_event)
    event_bus.subscribe(TOPIC_ERROR, self._on_error_event)

    queued = Qt.ConnectionType.QueuedConnection
    self._status.connect(self._handle_status, queued)
    self._transcript.connect(self._handle_transcript, queued)
    self._reply.connect(self._handle_reply, queued)
    self._error.connect(self._handle_error, queued)

    view.listen_pressed.connect(self.start_listening)
    view.listen_released.connect(self.stop_listening)
    view.stop_speaking_requested.connect(self.stop_speaking)

    available = voice.is_available()
    view.set_available(
      available,
      detail=(
        ""
        if available
        else 'Kokoro TTS / mic unavailable. Install PC voice stack: pip install -e ".[voice]"'
      ),
    )
    view.set_status(voice.status().value)

  def _on_status_event(self, payload: dict) -> None:
    self._status.emit(str(payload.get("status", "idle")))

  def _on_transcript_event(self, payload: dict) -> None:
    self._transcript.emit(str(payload.get("text", "")))

  def _on_reply_event(self, payload: dict) -> None:
    self._reply.emit(str(payload.get("text", "")))

  def _on_error_event(self, payload: dict) -> None:
    self._error.emit(str(payload.get("message", "Unknown error")))

  @Slot()
  def start_listening(self) -> None:
    if self._busy:
      return
    self._view.hide_error()
    try:
      self._voice.start_listening()
    except Exception as exc:  # noqa: BLE001
      self._view.show_error(str(exc))

  @Slot()
  def stop_listening(self) -> None:
    if self._busy:
      return
    if self._voice.status().value != "listening":
      return
    self._busy = True
    thread = run_in_thread(self, self._voice.stop_listening)
    worker = thread._maira_worker  # type: ignore[attr-defined]
    worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)

  @Slot()
  def stop_speaking(self) -> None:
    self._voice.stop_speaking()

  @Slot(str)
  def _on_worker_finished(self, error: str) -> None:
    self._busy = False
    if error:
      self._view.show_error(error)
    status = self._voice.status().value
    if status == "error":
      self._view.set_status("error")
    else:
      self._view.set_status(status if status != "error" else "idle")

  @Slot(str)
  def _handle_status(self, status: str) -> None:
    self._view.set_status(status)

  @Slot(str)
  def _handle_transcript(self, text: str) -> None:
    self._view.append_transcript(text)

  @Slot(str)
  def _handle_reply(self, text: str) -> None:
    self._view.append_reply(text)

  @Slot(str)
  def _handle_error(self, message: str) -> None:
    self._view.show_error(message)
    self._view.set_status("error")
