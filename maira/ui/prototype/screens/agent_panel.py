"""Settings → Agent & actions: allowed folders, Gmail app password, contacts, model check."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
  QFileDialog,
  QFrame,
  QHBoxLayout,
  QLabel,
  QLineEdit,
  QListWidget,
  QPushButton,
  QVBoxLayout,
  QWidget,
)

from maira.app.user_config import UserConfig
from maira.modules.agent.actions import Contacts
from maira.modules.agent.files import default_folders
from maira.ui.prototype.theme import tokens as t

APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"
PASSWORD_KEY = "gmail_app_password"


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
  card = QFrame()
  card.setObjectName("Card")
  layout = QVBoxLayout(card)
  layout.setContentsMargins(20, 16, 20, 16)
  layout.setSpacing(10)
  heading = QLabel(title)
  heading.setObjectName("Secondary")
  layout.addWidget(heading)
  return card, layout


def _muted(text: str = "") -> QLabel:
  label = QLabel(text)
  label.setObjectName("Muted")
  label.setWordWrap(True)
  return label


def _button(text: str, handler) -> QPushButton:
  button = QPushButton(text)
  button.setObjectName("GhostButton")
  button.clicked.connect(handler)
  return button


class AgentPanel(QWidget):
  def __init__(
    self,
    config: UserConfig,
    *,
    get_secret: Callable[[str], str],
    set_secret: Callable[[str, str], None],
    installed_models: Callable[[], list[str] | None] | None = None,
    contacts_path: Path | None = None,
    pick_folder: Callable[[], str] | None = None,
    parent=None,
  ) -> None:
    super().__init__(parent)
    self.config = config
    self._get_secret = get_secret
    self._set_secret = set_secret
    self._installed_models = installed_models
    self._contacts_path = contacts_path
    self._pick_folder = pick_folder or self._ask_for_folder

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(12)

    # Model check
    model_card, model = _card("AI model for tasks")
    self.model_state = _muted("")
    model.addWidget(self.model_state)
    model.addWidget(_button("Check again", self.refresh_model), alignment=Qt.AlignmentFlag.AlignLeft)
    root.addWidget(model_card)

    # Folders
    folder_card, folders = _card("Folders the agent may read and change")
    self.folders = QListWidget()
    self.folders.setMaximumHeight(150)
    folders.addWidget(self.folders)
    row = QHBoxLayout()
    row.addWidget(_button("Add folder…", self.add_folder))
    row.addWidget(_button("Remove", self.remove_folder))
    row.addStretch(1)
    folders.addLayout(row)
    self.folders_hint = _muted("")
    folders.addWidget(self.folders_hint)
    root.addWidget(folder_card)

    # Gmail
    mail_card, mail = _card("Gmail app password")
    mail.addWidget(_muted(
      "Not your normal password: Google makes a separate 16-letter one for apps. Create it at "
      f"{APP_PASSWORD_URL} (needs 2-Step Verification). It is stored in Windows Credential Manager."
    ))
    row = QHBoxLayout()
    self.password = QLineEdit()
    self.password.setEchoMode(QLineEdit.EchoMode.Password)
    self.password.setPlaceholderText("xxxx xxxx xxxx xxxx")
    row.addWidget(self.password, stretch=1)
    row.addWidget(_button("Save", self.save_password))
    row.addWidget(_button("Remove", self.clear_password))
    row.addWidget(_button("Get one", lambda: QDesktopServices.openUrl(QUrl(APP_PASSWORD_URL))))
    mail.addLayout(row)
    self.password_state = _muted("")
    mail.addWidget(self.password_state)
    root.addWidget(mail_card)

    # Contacts
    contacts_card, contacts = _card("Contacts")
    self.contacts_state = _muted("")
    contacts.addWidget(self.contacts_state)
    contacts.addWidget(_button("Open contacts file", self.open_contacts), alignment=Qt.AlignmentFlag.AlignLeft)
    root.addWidget(contacts_card)

    self.refresh()

  def _ask_for_folder(self) -> str:
    return QFileDialog.getExistingDirectory(self, "Allow a folder", str(Path.home()))

  # --- state -----------------------------------------------------------------------------------

  def _chosen(self) -> list[str]:
    value = self.config.get("agent.folders") or []
    if isinstance(value, str):
      value = value.split(";")
    return [str(v) for v in value if str(v).strip()]

  def refresh(self) -> None:
    self.folders.clear()
    chosen = self._chosen()
    for folder in chosen or [str(p) for p in default_folders()]:
      self.folders.addItem(folder)
    self.folders_hint.setText(
      "Using the default folders. Add one to choose your own list." if not chosen
      else "Only these folders. Everything else on the PC stays out of reach."
    )
    has_password = bool(self._get_secret(PASSWORD_KEY))
    self.password_state.setText("● App password saved" if has_password else "● Not set — email is off")
    self.password_state.setStyleSheet(f"color: {t.STATUS_READY if has_password else t.STATUS_WARN};")
    count = len(Contacts(self._contacts_path).all()) if self._contacts_path else 0
    self.contacts_state.setText(
      f"{count} saved. Add more by asking, e.g. \"save contact Mom phone +91 98765 43210\"."
    )
    self.refresh_model()

  def refresh_model(self) -> None:
    model = str(self.config.get("agent.model") or "qwen3.5:4b")
    installed = self._installed_models() if self._installed_models else None
    if installed is None:
      text, color = "● Ollama is not running — start it to use the agent.", t.STATUS_WARN
    elif any(name == model or name.split(":")[0] == model or name == f"{model}:latest" for name in installed):
      text, color = f"● {model} is installed and ready.", t.STATUS_READY
    else:
      text, color = f"● {model} is not installed. In PowerShell run:  ollama pull {model}", t.STATUS_WARN
    self.model_state.setText(text)
    self.model_state.setStyleSheet(f"color: {color};")

  # --- actions ------------------------------------------------------------------------------------

  def _save_folders(self, folders: list[str]) -> None:
    self.config.set("agent.folders", folders)
    self.config.save()
    self.refresh()

  def add_folder(self) -> None:
    folder = self._pick_folder()
    if not folder:
      return
    chosen = self._chosen() or [str(p) for p in default_folders()]
    if folder not in chosen:
      self._save_folders([*chosen, folder])

  def remove_folder(self) -> None:
    item = self.folders.currentItem()
    if item is None:
      return
    chosen = self._chosen() or [str(p) for p in default_folders()]
    remaining = [f for f in chosen if f != item.text()]
    if not remaining:
      self.folders_hint.setText("Keep at least one folder (or turn the agent off).")
      return
    self._save_folders(remaining)

  def save_password(self) -> None:
    value = self.password.text().replace(" ", "").strip()
    if len(value) < 12:
      self.password_state.setText("That doesn't look like an app password (16 letters).")
      return
    self._set_secret(PASSWORD_KEY, value)
    self.password.clear()
    self.refresh()

  def clear_password(self) -> None:
    self._set_secret(PASSWORD_KEY, "")
    self.refresh()

  def open_contacts(self) -> None:
    if self._contacts_path is None:
      return
    if not self._contacts_path.exists():
      self._contacts_path.parent.mkdir(parents=True, exist_ok=True)
      self._contacts_path.write_text("{}\n", encoding="utf-8")
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._contacts_path)))
