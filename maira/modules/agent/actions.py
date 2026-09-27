"""Tools that act outside files: open things, play music, contacts, email, WhatsApp."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import smtplib
import time
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import quote

from maira.core.interfaces.desktop import DesktopController, DesktopStep
from maira.modules.agent.files import FileAccess
from maira.modules.agent.tools import Tool, ToolError, list_arg, text_arg

MAX_ATTACH_BYTES = 24 * 1024 * 1024  # Gmail's limit is 25 MB
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


# --- contacts -------------------------------------------------------------------------------


class Contacts:
  """data/contacts.json: {"mom": {"name": "Mom", "email": "...", "phone": "+91..."}}."""

  def __init__(self, path: Path) -> None:
    self.path = path

  def _load(self) -> dict[str, dict[str, str]]:
    try:
      data = json.loads(self.path.read_text(encoding="utf-8"))
      return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
      return {}

  def find(self, name: str) -> dict[str, str] | None:
    key = name.strip().lower()
    data = self._load()
    if key in data:
      return data[key]
    matches = [v for k, v in data.items() if key and (key in k or k in key)]
    return matches[0] if len(matches) == 1 else None

  def all(self) -> list[dict[str, str]]:
    return list(self._load().values())

  def save(self, name: str, email: str = "", phone: str = "") -> dict[str, str]:
    data = self._load()
    entry = dict(data.get(name.strip().lower(), {"name": name.strip()}))
    if email:
      entry["email"] = email
    if phone:
      entry["phone"] = phone
    data[name.strip().lower()] = entry
    self.path.parent.mkdir(parents=True, exist_ok=True)
    self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def normalize_phone(raw: str, default_country: str = "91") -> str:
  digits = re.sub(r"\D", "", raw)
  if raw.strip().startswith("+") or len(digits) > 10:
    return digits.lstrip("0")
  if len(digits) == 10:
    return default_country + digits
  raise ToolError(f'"{raw}" is not a full phone number; include the country code, e.g. +91 98765 43210.')


# --- the tools ---------------------------------------------------------------------------------


class ActionTools:
  def __init__(
    self,
    files: FileAccess,
    contacts: Contacts,
    *,
    desktop: DesktopController | None = None,
    email_address: Callable[[], str] = lambda: "",
    email_password: Callable[[], str] = lambda: "",
    smtp_factory: Callable[[], Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
  ) -> None:
    self.files = files
    self.contacts = contacts
    self.desktop = desktop
    self.email_address = email_address
    self.email_password = email_password
    self.smtp_factory = smtp_factory or (lambda: smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60))
    self.sleep = sleep

  # open / play

  def _desktop(self) -> DesktopController:
    if self.desktop is None:
      raise ToolError("Desktop control is turned off (Settings → Desktop control).")
    return self.desktop

  def open_item(self, args: dict[str, Any]) -> str:
    target = text_arg(args, "target")
    if not target:
      raise ToolError("Say what to open.")
    if re.match(r"^(https?://|www\.)", target, re.I):
      result = self._desktop().open_url(target if "://" in target else "https://" + target)
    elif re.search(r"[\\/]|\.[a-z0-9]{2,4}$", target, re.I):
      result = self._desktop().open_path(str(self.files.resolve(target, must_exist=True)))
    else:
      result = self._desktop().open_app(target)
    if not result.ok:
      raise ToolError(result.message)
    return result.message

  def play_music(self, args: dict[str, Any]) -> str:
    query = text_arg(args, "query")
    if not query:
      raise ToolError("Say which song to play.")
    from maira.modules.desktop_controller.youtube import resolve_youtube_play_url  # noqa: PLC0415

    url = resolve_youtube_play_url(query)
    result = self._desktop().open_url(url)
    if not result.ok:
      raise ToolError(result.message)
    return f"Playing on YouTube: {query}"

  # contacts

  def find_contact(self, args: dict[str, Any]) -> str:
    name = text_arg(args, "name")
    entry = self.contacts.find(name) if name else None
    if entry is None:
      known = ", ".join(c.get("name", "") for c in self.contacts.all()) or "none saved yet"
      return f'No contact "{name}". Saved contacts: {known}. Ask the user for the email or number.'
    return json.dumps(entry, ensure_ascii=False)

  def confirm_save_contact(self, args: dict[str, Any]) -> str:
    details = ", ".join(x for x in (text_arg(args, "email"), text_arg(args, "phone")) if x)
    return f'Save contact "{text_arg(args, "name")}" ({details})'

  def check_save_contact(self, args: dict[str, Any]) -> None:
    if not text_arg(args, "name") or not (text_arg(args, "email") or text_arg(args, "phone")):
      raise ToolError("A contact needs a name and an email or phone number.")
    if text_arg(args, "email") and not _EMAIL.match(text_arg(args, "email")):
      raise ToolError(f'"{text_arg(args, "email")}" is not an email address.')
    if text_arg(args, "phone"):
      normalize_phone(text_arg(args, "phone"))

  def save_contact(self, args: dict[str, Any]) -> str:
    self.check_save_contact(args)
    entry = self.contacts.save(text_arg(args, "name"), text_arg(args, "email"), text_arg(args, "phone"))
    return f"Saved contact: {json.dumps(entry, ensure_ascii=False)}"

  # email

  def _recipients(self, args: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in list_arg(args, "to"):
      if _EMAIL.match(item):
        result.append(item)
        continue
      entry = self.contacts.find(item)
      if entry and entry.get("email"):
        result.append(entry["email"])
      else:
        raise ToolError(f'No email address for "{item}". Ask the user, then save_contact.')
    if not result:
      raise ToolError("Say who to send it to.")
    return result

  def _attachments(self, args: dict[str, Any]) -> list[Path]:
    paths = [self.files.resolve(p, must_exist=True) for p in list_arg(args, "attachments")]
    for path in paths:
      if path.is_dir():
        raise ToolError(f"{path} is a folder; attach files (or zip it first).")
    if sum(p.stat().st_size for p in paths) > MAX_ATTACH_BYTES:
      raise ToolError("Attachments are over Gmail's 25 MB limit.")
    return paths

  def check_email(self, args: dict[str, Any]) -> None:
    if not self.email_address() or not self.email_password():
      raise ToolError(
        "Email is not set up. The user needs to add their Gmail address and an app password in "
        "Settings → Agent (create one at https://myaccount.google.com/apppasswords)."
      )
    self._recipients(args)
    self._attachments(args)

  def confirm_email(self, args: dict[str, Any]) -> str:
    to = ", ".join(self._recipients(args))
    files = self._attachments(args)
    body = text_arg(args, "body")
    lines = [f"Send an email from {self.email_address()} to {to}", f'Subject: {text_arg(args, "subject") or "(none)"}']
    if files:
      lines.append("Attached: " + ", ".join(p.name for p in files))
    lines.append("Message: " + (body[:300] + ("…" if len(body) > 300 else "")))
    return "\n".join(lines)

  def send_email(self, args: dict[str, Any]) -> str:
    self.check_email(args)
    to = self._recipients(args)
    message = EmailMessage()
    message["From"] = self.email_address()
    message["To"] = ", ".join(to)
    message["Subject"] = text_arg(args, "subject")
    message.set_content(text_arg(args, "body"))
    for path in self._attachments(args):
      kind, _ = mimetypes.guess_type(path.name)
      main, sub = (kind or "application/octet-stream").split("/", 1)
      message.add_attachment(path.read_bytes(), maintype=main, subtype=sub, filename=path.name)
    try:
      with self.smtp_factory() as smtp:
        smtp.login(self.email_address(), self.email_password())
        smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
      raise ToolError("Gmail refused the login: check the app password in Settings → Agent.") from exc
    except (smtplib.SMTPException, OSError) as exc:
      raise ToolError(f"Could not send the email: {exc}") from exc
    return f"Email sent to {', '.join(to)}"

  # WhatsApp

  def _phone(self, args: dict[str, Any]) -> str:
    to = text_arg(args, "to")
    if not to:
      raise ToolError("Say who to message.")
    if re.search(r"\d{6,}", re.sub(r"[\s\-()]", "", to)):
      return normalize_phone(to)
    entry = self.contacts.find(to)
    if entry and entry.get("phone"):
      return normalize_phone(entry["phone"])
    raise ToolError(f'No phone number for "{to}". Ask the user, then save_contact.')

  def check_whatsapp(self, args: dict[str, Any]) -> None:
    self._phone(args)
    self._desktop()
    if not text_arg(args, "message"):
      raise ToolError("Say what message to send.")

  def confirm_whatsapp(self, args: dict[str, Any]) -> str:
    message = text_arg(args, "message")
    return f"Send a WhatsApp message to {text_arg(args, 'to')} (+{self._phone(args)}):\n{message[:300]}"

  def send_whatsapp(self, args: dict[str, Any]) -> str:
    self.check_whatsapp(args)
    phone, text = self._phone(args), text_arg(args, "message")
    desktop = self._desktop()
    app = os.name == "nt" and _whatsapp_app_installed()
    url = (f"whatsapp://send?phone={phone}&text={quote(text)}" if app
           else f"https://web.whatsapp.com/send?phone={phone}&text={quote(text)}")
    opened = desktop.run_steps([DesktopStep("open_url", {"url": url})])
    if not opened.ok:
      raise ToolError(opened.message)
    self.sleep(6 if app else 15)  # WhatsApp Web needs longer to load the chat
    sent = desktop.run_steps([DesktopStep("focus", {"title": "WhatsApp"}), DesktopStep("press", {"key": "enter"})])
    if not sent.ok:
      return f"Opened WhatsApp with the message ready for +{phone}, but could not press Send ({sent.message}). The user should press Enter."
    return f"WhatsApp message sent to +{phone}"

  def tools(self) -> list[Tool]:
    return [
      Tool("open", "Open a file (with its usual app), a website, or an app by name.",
           {"target": {"type": "string", "description": "File path, URL, or app name like notepad"}},
           self.open_item, required=("target",)),
      Tool("play_music", "Play a song or video on YouTube.",
           {"query": {"type": "string", "description": "Song name and artist"}}, self.play_music, required=("query",)),
      Tool("find_contact", "Look up a saved contact's email and phone by name.",
           {"name": {"type": "string"}}, self.find_contact, required=("name",)),
      Tool("save_contact", "Save a contact's email and/or phone (with country code).",
           {"name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}},
           self.save_contact, required=("name",), confirm=self.confirm_save_contact, check=self.check_save_contact),
      Tool("send_email", "Send an email from the user's Gmail, optionally with files attached.",
           {"to": {"type": "array", "items": {"type": "string"}, "description": "Email addresses or contact names"},
            "subject": {"type": "string"}, "body": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "string"}, "description": "File paths"}},
           self.send_email, required=("to", "subject", "body"), confirm=self.confirm_email, check=self.check_email),
      Tool("send_whatsapp", "Send a WhatsApp text message (text only, no files).",
           {"to": {"type": "string", "description": "Phone number with country code, or a contact name"},
            "message": {"type": "string"}},
           self.send_whatsapp, required=("to", "message"), confirm=self.confirm_whatsapp, check=self.check_whatsapp),
    ]


def _whatsapp_app_installed() -> bool:
  try:
    import winreg  # noqa: PLC0415

    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"):
      return True
  except OSError:
    return False
