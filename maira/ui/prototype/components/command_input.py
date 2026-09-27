"""Command input — home and chat variants."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
  QComboBox,
  QFileDialog,
  QFrame,
  QHBoxLayout,
  QLabel,
  QPushButton,
  QSizePolicy,
  QTextEdit,
  QVBoxLayout,
  QWidget,
)

from maira.shared.utils.attachments import MAX_FILES, AttachmentError, can_attach, compose_message
from maira.ui.prototype.components.icon_button import IconButton
from maira.ui.prototype.theme import tokens as t

_FILE_FILTER = (
  "Documents (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.txt *.md *.py *.json "
  "*.yaml *.yml *.csv *.log *.toml *.xml *.html *.css *.js *.ts *.sql);;All files (*.*)"
)


class _FileChip(QFrame):
  removed = Signal(str)

  def __init__(self, path: Path, parent=None) -> None:
    super().__init__(parent)
    self.path = path
    self.setObjectName("FileChip")
    layout = QHBoxLayout(self)
    layout.setContentsMargins(8, 2, 4, 2)
    layout.setSpacing(4)
    name = QLabel(path.name)
    name.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 12px; border: none;")
    close = QPushButton("×")
    close.setFlat(True)
    close.setFixedSize(18, 18)
    close.setCursor(Qt.CursorShape.PointingHandCursor)
    close.setStyleSheet(f"color: {t.TEXT_MUTED}; border: none; font-size: 14px;")
    close.clicked.connect(lambda: self.removed.emit(str(self.path)))
    layout.addWidget(name)
    layout.addWidget(close)
    self.setStyleSheet(
      f"""
      QFrame#FileChip {{
        background: {t.BG_HOVER};
        border: 1px solid {t.BORDER};
        border-radius: 8px;
      }}
      """
    )


class _CommandEditor(QTextEdit):
  submit = Signal()

  def keyPressEvent(self, event) -> None:  # noqa: N802
    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
      if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
        super().keyPressEvent(event)
      else:
        self.submit.emit()
      return
    super().keyPressEvent(event)


class CommandInput(QWidget):
  submitted = Signal(str, str)
  voice_clicked = Signal()
  talk_clicked = Signal()
  attach_clicked = Signal()
  notice = Signal(str)

  def __init__(self, compact: bool = False, parent=None) -> None:
    super().__init__(parent)
    self._compact = compact
    self._focused = False
    self._attachments: list[Path] = []
    self._base_height = t.COMMAND_CHAT_HEIGHT if compact else t.COMMAND_HEIGHT
    self.setObjectName("CommandInput")
    self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    self.setAcceptDrops(True)
    self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.setMinimumHeight(self._base_height)
    self.setMaximumHeight(self._base_height + 20)
    self.setMaximumWidth(t.COMMAND_WIDTH if not compact else 16777215)

    root = QVBoxLayout(self)
    root.setContentsMargins(18, 14, 14, 12)
    root.setSpacing(8)

    self._chips = QWidget()
    self._chips_layout = QHBoxLayout(self._chips)
    self._chips_layout.setContentsMargins(0, 0, 0, 0)
    self._chips_layout.setSpacing(6)
    self._chips_layout.addStretch(1)
    self._chips.hide()
    root.addWidget(self._chips)

    self.editor = _CommandEditor()
    self.editor.setPlaceholderText("What would you like to do?")
    self.editor.setFrameStyle(0)
    self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.editor.setStyleSheet(
      f"""
      QTextEdit {{
        background: transparent;
        border: none;
        color: {t.TEXT_PRIMARY};
        font-size: 14px;
        padding: 0;
      }}
      """
    )
    self.editor.submit.connect(self._submit)
    self.editor.focusInEvent = self._wrap_focus(self.editor.focusInEvent, True)  # type: ignore[method-assign]
    self.editor.focusOutEvent = self._wrap_focus(self.editor.focusOutEvent, False)  # type: ignore[method-assign]
    root.addWidget(self.editor, stretch=1)

    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(6)

    self.mode = QComboBox()
    self.mode.addItems(["Auto", "Chat", "Plan", "Search"])
    self.mode.setFixedWidth(86)
    self.mode.setStyleSheet(
      f"""
      QComboBox {{
        background: transparent;
        border: 1px solid {t.BORDER};
        border-radius: 8px;
        color: {t.TEXT_SECONDARY};
        padding: 4px 8px;
        font-size: 12px;
      }}
      QComboBox:hover {{ border: 1px solid {t.BORDER_HOVER}; color: {t.TEXT_PRIMARY}; }}
      QComboBox::drop-down {{ border: none; width: 16px; }}
      QComboBox QAbstractItemView {{
        background: {t.BG_ELEVATED};
        border: 1px solid {t.BORDER_HOVER};
        selection-background-color: rgba(255,255,255,0.08);
        color: {t.TEXT_PRIMARY};
      }}
      """
    )
    toolbar.addWidget(self.mode)
    toolbar.addStretch(1)

    self.attach_btn = IconButton("attach", "Attach a file", size=32)
    self.talk_btn = IconButton("wave", "Voice conversation — talk with Ultron (Ctrl+Shift+Space)", size=32)
    self.mic_btn = IconButton("mic", "Dictate — speak to type", size=32)
    self.talk_btn.clicked.connect(self.talk_clicked.emit)
    self.send_btn = IconButton("send", "Send", size=32)
    self.attach_btn.clicked.connect(self.pick_files)
    self.mic_btn.clicked.connect(self.voice_clicked.emit)
    self.send_btn.clicked.connect(self._submit)
    toolbar.addWidget(self.attach_btn)
    toolbar.addWidget(self.talk_btn)
    toolbar.addWidget(self.mic_btn)
    toolbar.addWidget(self.send_btn)
    root.addLayout(toolbar)

  def _wrap_focus(self, original, focused: bool):
    def handler(event):
      self._focused = focused
      self.update()
      return original(event)

    return handler

  def text(self) -> str:
    return self.editor.toPlainText().strip()

  def clear(self) -> None:
    self.editor.clear()

  def set_placeholder(self, text: str) -> None:
    self.editor.setPlaceholderText(text)

  def set_text(self, text: str) -> None:
    self.editor.setPlainText(text)
    cursor = self.editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    self.editor.setTextCursor(cursor)

  def append_text(self, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
      return
    existing = self.editor.toPlainText()
    if existing and not existing.endswith((" ", "\n")):
      cleaned = " " + cleaned
    self.set_text(existing + cleaned)

  def focus_input(self) -> None:
    self.editor.setFocus()

  def pick_files(self) -> None:
    self.attach_clicked.emit()
    selected, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", _FILE_FILTER)
    for item in selected:
      self.add_path(Path(item))

  def add_path(self, path: Path) -> None:
    resolved = path.expanduser()
    if not resolved.is_file():
      self.notice.emit(f"{resolved.name} is not a file")
      return
    if any(existing.resolve() == resolved.resolve() for existing in self._attachments):
      return
    if len(self._attachments) >= MAX_FILES:
      self.notice.emit(f"You can attach up to {MAX_FILES} files")
      return
    try:
      can_attach(resolved)
    except (OSError, AttachmentError) as exc:
      self.notice.emit(str(exc))
      return
    self._attachments.append(resolved)
    self._refresh_chips()

  def _remove_path(self, path_str: str) -> None:
    target = Path(path_str)
    self._attachments = [item for item in self._attachments if item != target]
    self._refresh_chips()

  def _refresh_chips(self) -> None:
    while self._chips_layout.count() > 1:
      item = self._chips_layout.takeAt(0)
      widget = item.widget()
      if widget is not None:
        widget.deleteLater()
    for path in self._attachments:
      chip = _FileChip(path)
      chip.removed.connect(self._remove_path)
      self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)
    extra = 32 if self._attachments else 0
    self._chips.setVisible(bool(self._attachments))
    self.setMinimumHeight(self._base_height + extra)
    self.setMaximumHeight(self._base_height + 20 + extra)

  def dragEnterEvent(self, event) -> None:  # noqa: N802
    if event.mimeData().hasUrls():
      event.acceptProposedAction()
    else:
      super().dragEnterEvent(event)

  def dropEvent(self, event) -> None:  # noqa: N802
    for url in event.mimeData().urls():
      local = url.toLocalFile()
      if local:
        self.add_path(Path(local))
    event.acceptProposedAction()

  def _submit(self) -> None:
    display, prompt, errors = compose_message(self.text(), self._attachments)
    for message in errors:
      self.notice.emit(message)
    if not prompt:
      return
    self.submitted.emit(display, prompt)
    self.clear()
    self._attachments.clear()
    self._refresh_chips()

  def paintEvent(self, event) -> None:  # noqa: N802
    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = self.rect().adjusted(1, 1, -1, -1)
    radius = float(t.RADIUS_LG if self._compact else t.RADIUS_XL)

    # Soft outer glow when focused
    if self._focused:
      glow = QColor(255, 255, 255)
      glow.setAlphaF(0.05)
      painter.setPen(Qt.PenStyle.NoPen)
      painter.setBrush(glow)
      painter.drawRoundedRect(self.rect(), radius + 2, radius + 2)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    fill = QColor(t.BG_SURFACE)
    fill.setAlphaF(0.92)
    painter.fillPath(path, fill)

    border = QColor(255, 255, 255)
    border.setAlphaF(0.18 if self._focused else 0.07)
    painter.setPen(border)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.end()
