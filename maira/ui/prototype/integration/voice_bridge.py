"""Bridge: Chat mic → dictation, and the 〰 button → hands-free voice conversation.

Dictation types what you say into the input box. Voice conversation listens,
answers out loud, and listens again until you stop it (Esc or 〰).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.voice import Voice
from maira.modules.voice.service import (
  TOPIC_DICTATION,
  TOPIC_ERROR,
  TOPIC_REPLY,
  TOPIC_STATUS,
  TOPIC_TRANSCRIPT,
)
from maira.shared.utils.async_bridge import run_in_thread
from maira.ui.prototype.screens.chat import ChatScreen


_CONVERSATION_STATES = {
  "listening": "Listening…",
  "transcribing": "Samajh rahi hoon…",
  "processing": "Samajh rahi hoon…",
  "thinking": "Soch rahi hoon…",
  "speaking": "Bol rahi hoon…",
  "interrupted": "Listening…",
}


class ProtoVoiceBridge(QObject):
  _status = Signal(str)
  _dictation = Signal(str)
  _error = Signal(str)
  _transcript = Signal(str)
  _reply = Signal(str)

  def __init__(self, voice: Voice, event_bus: EventBus, view: ChatScreen) -> None:
    super().__init__()
    self._voice = voice
    self._view = view
    self._dictating = False

    view.set_voice_backend(True)
    view.set_auto_conversation(False)
    view.dictate_start.connect(self.start_dictation)
    view.dictate_stop.connect(self.stop_dictation)
    view.voice_cancel.connect(self.cancel_dictation)
    view.voice_toggled.connect(self._on_voice_toggled)

    event_bus.subscribe(TOPIC_STATUS, lambda p: self._status.emit(str(p.get("status", "idle"))))
    event_bus.subscribe(TOPIC_DICTATION, lambda p: self._dictation.emit(str(p.get("text", ""))))
    event_bus.subscribe(TOPIC_ERROR, lambda p: self._error.emit(str(p.get("message", ""))))
    event_bus.subscribe(TOPIC_TRANSCRIPT, lambda p: self._transcript.emit(str(p.get("text", ""))))
    event_bus.subscribe(TOPIC_REPLY, lambda p: self._reply.emit(str(p.get("text", ""))))

    queued = Qt.ConnectionType.QueuedConnection
    self._status.connect(self._on_status, queued)
    self._dictation.connect(self._on_dictation, queued)
    self._error.connect(self._on_error, queued)
    self._transcript.connect(self._on_transcript, queued)
    self._reply.connect(self._on_reply, queued)

    if not voice.is_available():
      view.set_voice_unavailable(
        'Mic extras missing. Run: pip install -e ".[voice]"'
      )

  @Slot()
  def start_dictation(self) -> None:
    self._view.hide_error()
    try:
      start = getattr(self._voice, "start_dictation", None)
      if callable(start):
        start()
      else:
        self._voice.start_listening()
      self._dictating = True
      self._view.set_dictating(True)
    except Exception as exc:  # noqa: BLE001
      self._dictating = False
      self._view.set_dictating(False)
      self._view.show_error(str(exc))

  @Slot()
  def stop_dictation(self) -> None:
    if not self._dictating:
      return
    self._view.set_dictating(True)  # keep active until transcript lands
    self._view.set_placeholder_listening(True)
    try:
      stop = getattr(self._voice, "stop_dictation", None)
      if callable(stop):
        run_in_thread(self, stop)
      else:
        run_in_thread(self, self._voice.stop_listening)
    except Exception as exc:  # noqa: BLE001
      self._dictating = False
      self._view.set_dictating(False)
      self._view.show_error(str(exc))

  @Slot()
  def cancel_dictation(self) -> None:
    self._dictating = False
    try:
      cancel = getattr(self._voice, "cancel_dictation", None)
      if callable(cancel):
        cancel()
      else:
        self._voice.stop_speaking()
    except Exception:  # noqa: BLE001
      pass
    self._view.set_dictating(False)

  # --- voice conversation ---------------------------------------------------------

  @Slot(bool)
  def _on_voice_toggled(self, enabled: bool) -> None:
    try:
      if enabled:
        self._voice.start_conversation()
        if not getattr(self._voice, "in_conversation", True):
          # Voice extras missing / no microphone: the reason arrives as a voice error.
          self._view.set_voice_mode(False)
      else:
        self._voice.stop_conversation()
    except Exception as exc:  # noqa: BLE001
      self._view.set_voice_mode(False)
      self._view.show_error(str(exc))

  @Slot(str)
  def _on_transcript(self, text: str) -> None:
    if self._view.voice_mode:
      self._view.voice_stage.set_transcript(text.strip())

  @Slot(str)
  def _on_reply(self, text: str) -> None:
    if self._view.voice_mode:
      self._view.voice_stage.set_reply(text.strip())

  def _on_conversation_status(self, status: str) -> None:
    label = _CONVERSATION_STATES.get(status)
    if label:
      self._view.set_voice_state(label)
    elif status == "idle" and not getattr(self._voice, "in_conversation", True):
      # The loop ended on its own (e.g. microphone lost): leave voice mode.
      self._view.set_voice_mode(False)

  # --- dictation --------------------------------------------------------------------

  @Slot(str)
  def _on_status(self, status: str) -> None:
    if self._view.voice_mode:
      self._on_conversation_status(status)
      return
    if not self._dictating and status != "listening":
      return
    if status == "listening":
      self._dictating = True
      self._view.set_dictating(True)
    elif status == "transcribing":
      self._view.set_placeholder_listening(True)
      self._view.input.set_placeholder("Transcribing...")
    elif status in ("idle", "error"):
      if status == "idle":
        # Dictation text may arrive just after idle; UI reset also happens in _on_dictation.
        pass

  @Slot(str)
  def _on_dictation(self, text: str) -> None:
    self._dictating = False
    self._view.set_dictating(False)
    if text.strip():
      self._view.insert_dictation(text.strip())
    self._view.input.focus_input()

  @Slot(str)
  def _on_error(self, message: str) -> None:
    if self._view.voice_mode:
      # Keep the conversation going; show what went wrong on the voice screen.
      if message:
        self._view.voice_stage.hint.setText(message)
      return
    self._dictating = False
    self._view.set_dictating(False)
    if message:
      self._view.show_error(message)
