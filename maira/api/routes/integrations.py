"""Integrations - what Ultron can reach on this machine, reported honestly.

Every row reflects a real service. Nothing is listed as connectable unless the
connect call can actually do it; anything that needs a secret is set up in the
desktop app, never typed into a web page.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from maira.api.deps import get_container, get_settings

router = APIRouter(tags=["integrations"])


def _service_state(key: str) -> tuple[bool, str]:
  service = get_container().try_resolve(key)
  if service is None:
    return False, "Not installed"
  try:
    result = service.is_available()
  except Exception as exc:  # noqa: BLE001
    return False, str(exc)
  if isinstance(result, tuple):
    return bool(result[0]), str(result[1])
  return bool(result), "ready" if result else "Not available on this machine"


def _persist(path: str, value) -> None:
  """Remember a toggle across restarts. Runtime state is already changed if this fails."""
  try:
    from maira.app.user_config import UserConfig  # noqa: PLC0415

    UserConfig().set(path, value)
  except Exception as exc:  # noqa: BLE001
    logger.warning("Could not save {}: {}", path, exc)


def _ollama() -> dict:
  settings = get_settings()
  llm = get_container().try_resolve("llm")
  model = getattr(llm, "model", None) or settings.ollama.model
  try:
    ok = bool(llm.is_available()) if llm is not None else False
  except Exception:  # noqa: BLE001
    ok = False
  return {
    "id": "ollama",
    "name": "Ollama (local model)",
    "icon": "cpu",
    "status": "connected" if ok else "disconnected",
    "detail": f"{model} at {settings.ollama.host}" if ok else f"Not reachable at {settings.ollama.host}. Start Ollama.",
    "error": not ok,
    "toggle": False,
  }


def _toggle(integration_id: str, name: str, icon: str, key: str, on_detail: str) -> dict:
  ok, reason = _service_state(key)
  return {
    "id": integration_id,
    "name": name,
    "icon": icon,
    "status": "connected" if ok else "available",
    "detail": on_detail if ok else reason,
    "error": False,
    "toggle": True,
  }


def _voice() -> dict:
  # Resolving "voice" loads speech models, so only ask a voice service that already exists.
  container = get_container()
  ok, reason = False, "Starts the first time you use voice"
  if container.is_resolved("voice"):
    voice = container.resolve("voice")
    check = getattr(voice, "can_listen", None)
    ok, reason = check() if callable(check) else (bool(voice.is_available()), "Voice is not available")
  return {
    "id": "voice",
    "name": "Voice",
    "icon": "mic",
    "status": "connected" if ok else "available",
    "detail": "Microphone and speech recognition ready" if ok else reason,
    "error": False,
    "toggle": False,
  }


def _gmail() -> dict:
  address = ""
  has_password = False
  try:
    from maira.app.secrets import get_secret  # noqa: PLC0415
    from maira.app.user_config import UserConfig  # noqa: PLC0415

    agent = getattr(get_settings(), "agent", None)
    address = str(UserConfig().get("agent.email_address") or getattr(agent, "email_address", "") or "")
    has_password = bool(get_secret("gmail_app_password"))
  except Exception as exc:  # noqa: BLE001
    logger.debug("Gmail status unavailable: {}", exc)
  ok = bool(address and has_password)
  return {
    "id": "gmail",
    "name": "Gmail",
    "icon": "mail",
    "status": "connected" if ok else "available",
    "detail": f"Sending as {address}" if ok else "Add your address and app password in the desktop app: Settings",
    "error": False,
    "toggle": False,
  }


def _skills() -> dict:
  skills = get_container().try_resolve("skills")
  store = getattr(skills, "store", None)
  try:
    count = len(store.skills(enabled_only=True)) if store is not None else 0
  except Exception:  # noqa: BLE001
    count = 0
  enabled = bool(getattr(skills, "enabled", False))
  return {
    "id": "skills",
    "name": "Skills",
    "icon": "layers",
    "status": "connected" if enabled and count else "available",
    "detail": f"{count} skill(s) installed" if count else 'None yet. In chat: "install skill owner/repo"',
    "error": False,
    "toggle": False,
  }


def _all() -> list[dict]:
  return [
    _ollama(),
    _toggle("local", "This computer", "monitor", "desktop", "Open apps and sites, type and click"),
    _toggle("screen", "Screen reading", "eye", "vision", "Reads the screen once, only when asked"),
    _voice(),
    _gmail(),
    _skills(),
  ]


@router.get("/integrations")
def list_integrations() -> list[dict]:
  return _all()


def _set(integration_id: str, enabled: bool) -> dict:
  container = get_container()
  if integration_id == "local":
    service, path = container.try_resolve("desktop"), "desktop.enabled"
  elif integration_id == "screen":
    service, path = container.try_resolve("vision"), "vision.enabled"
  elif integration_id == "ollama":
    llm = container.try_resolve("llm")
    if enabled and llm is not None and llm.is_available(force=True):
      return _ollama()
    raise HTTPException(
      status_code=409,
      detail="Ollama is not running. Start it on this computer, then try again."
      if enabled
      else "Ollama runs outside Ultron. Quit it from its own tray icon.",
    )
  elif integration_id in {"gmail", "voice", "skills"}:
    raise HTTPException(
      status_code=409,
      detail={
        "gmail": "Gmail needs an app password, which is only entered in the desktop app's Settings.",
        "voice": "Voice is set up from the desktop app. Install the voice extra if it is missing.",
        "skills": 'Skills are installed from chat: "install skill owner/repo".',
      }[integration_id],
    )
  else:
    raise HTTPException(status_code=404, detail="Integration not found")

  if service is None or not hasattr(service, "set_enabled"):
    raise HTTPException(status_code=409, detail="That is not available on this machine")
  service.set_enabled(enabled)
  _persist(path, enabled)
  result = next(item for item in _all() if item["id"] == integration_id)
  if enabled and result["status"] != "connected":
    # Turned on, but a dependency is missing: say why instead of pretending.
    raise HTTPException(status_code=409, detail=result["detail"])
  return result


@router.post("/integrations/{integration_id}/connect")
def connect(integration_id: str) -> dict:
  return _set(integration_id, True)


@router.post("/integrations/{integration_id}/disconnect")
def disconnect(integration_id: str) -> dict:
  return _set(integration_id, False)
