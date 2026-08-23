"""Streaming text widget — renders token-by-token LLM output with light batching."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel


class StreamingLabel(QLabel):
  """Batches tokens for ~30 FPS UI updates without artificial sleep delays."""

  def __init__(self, parent=None, *, flush_interval_ms: int = 33) -> None:
    super().__init__(parent)
    self.setObjectName("assistantBubble")
    self.setWordWrap(True)
    self.setTextInteractionFlags(
      self.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
    )
    self._pending: list[str] = []
    self._flush_timer = QTimer(self)
    self._flush_timer.setInterval(max(16, flush_interval_ms))
    self._flush_timer.timeout.connect(self._flush_pending)
    self.clear_content()

  def append_token(self, token: str) -> None:
    if not token:
      return
    self._pending.append(token)
    if not self._flush_timer.isActive():
      self._flush_timer.start()

  def _flush_pending(self) -> None:
    if not self._pending:
      self._flush_timer.stop()
      return
    chunk = "".join(self._pending)
    self._pending.clear()
    self.setText(self.text() + chunk)

  def clear_content(self) -> None:
    self._flush_timer.stop()
    self._pending.clear()
    self.setText("")

  def set_complete(self) -> None:
    self._flush_pending()
    self._flush_timer.stop()
