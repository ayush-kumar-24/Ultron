"""Voice view — push-to-talk microphone and live status."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


class VoiceView(QWidget):
  listen_pressed = Signal()
  listen_released = Signal()
  stop_speaking_requested = Signal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self._build_ui()

  def _build_ui(self) -> None:
    root = QVBoxLayout(self)
    root.setContentsMargins(24, 24, 24, 24)
    root.setSpacing(16)

    title = QLabel("Voice")
    title.setObjectName("voiceTitle")
    root.addWidget(title)

    self._status = QLabel("Idle")
    self._status.setObjectName("voiceStatus")
    self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(self._status)

    self._hint = QLabel("Hold the microphone button, speak, then release.")
    self._hint.setObjectName("voiceHint")
    self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._hint.setWordWrap(True)
    root.addWidget(self._hint)

    mic_row = QHBoxLayout()
    mic_row.addStretch(1)
    self._mic_button = QPushButton("Hold to talk")
    self._mic_button.setObjectName("voiceMicButton")
    self._mic_button.setMinimumSize(180, 180)
    self._mic_button.setCheckable(True)
    self._mic_button.pressed.connect(self._on_pressed)
    self._mic_button.released.connect(self._on_released)
    mic_row.addWidget(self._mic_button)
    mic_row.addStretch(1)
    root.addLayout(mic_row)

    actions = QHBoxLayout()
    actions.addStretch(1)
    self._stop_button = QPushButton("Stop speaking")
    self._stop_button.clicked.connect(self.stop_speaking_requested.emit)
    self._stop_button.setEnabled(False)
    actions.addWidget(self._stop_button)
    actions.addStretch(1)
    root.addLayout(actions)

    self._error = QLabel()
    self._error.setObjectName("errorBanner")
    self._error.setWordWrap(True)
    self._error.hide()
    root.addWidget(self._error)

    self._transcript = QTextEdit()
    self._transcript.setReadOnly(True)
    self._transcript.setPlaceholderText("Transcript and replies will appear here.")
    self._transcript.setMinimumHeight(160)
    root.addWidget(self._transcript, stretch=1)

  def _on_pressed(self) -> None:
    self._mic_button.setChecked(True)
    self.listen_pressed.emit()

  def _on_released(self) -> None:
    self._mic_button.setChecked(False)
    self.listen_released.emit()

  def set_status(self, status: str) -> None:
    labels = {
      "idle": "Idle",
      "listening": "Listening…",
      "processing": "Processing…",
      "speaking": "Speaking…",
      "error": "Error",
    }
    self._status.setText(labels.get(status, status.title()))
    self._status.setProperty("voiceState", status)
    self._status.style().unpolish(self._status)
    self._status.style().polish(self._status)

    listening = status == "listening"
    processing = status == "processing"
    speaking = status == "speaking"
    self._mic_button.setEnabled(not processing and not speaking)
    self._stop_button.setEnabled(speaking)
    if listening:
      self._mic_button.setText("Listening…")
    elif processing:
      self._mic_button.setText("Processing…")
    else:
      self._mic_button.setText("Hold to talk")

  def set_available(self, available: bool, detail: str = "") -> None:
    self._mic_button.setEnabled(available)
    if available:
      self._hint.setText("Hold the microphone button, speak, then release.")
      self.hide_error()
    else:
      message = detail or (
        "Voice is unavailable. Install voice extras and check the microphone."
      )
      self._hint.setText(message)
      self.show_error(message)

  def show_error(self, message: str) -> None:
    self._error.setText(message)
    self._error.show()

  def hide_error(self) -> None:
    self._error.hide()
    self._error.clear()

  def append_transcript(self, text: str) -> None:
    if text.strip():
      self._transcript.append(f"You: {text.strip()}")

  def append_reply(self, text: str) -> None:
    if text.strip():
      self._transcript.append(f"Maira: {text.strip()}")
