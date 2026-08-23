"""PyAutoGUI-backed keyboard/mouse simulation (optional dependency)."""

from __future__ import annotations

from loguru import logger

_pyautogui = None
_load_error: str | None = None


def _ensure():
  global _pyautogui, _load_error
  if _pyautogui is not None:
    return _pyautogui
  if _load_error is not None:
    raise RuntimeError(_load_error)
  try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _pyautogui = pyautogui
    return _pyautogui
  except Exception as exc:  # noqa: BLE001
    _load_error = (
      f"pyautogui unavailable ({exc}). Install with: pip install -e \".[desktop]\""
    )
    raise RuntimeError(_load_error) from exc


def is_available() -> tuple[bool, str]:
  try:
    _ensure()
    return True, "ready"
  except RuntimeError as exc:
    return False, str(exc)


def type_text(text: str, *, interval: float = 0.02) -> None:
  gui = _ensure()
  # write() is more reliable for unicode on some layouts; typewrite for ascii-ish.
  try:
    gui.write(text, interval=max(0.0, interval))
  except Exception:
    gui.typewrite(text, interval=max(0.0, interval))


def hotkey(*keys: str) -> None:
  gui = _ensure()
  normalized = [k.strip().lower() for k in keys if k and k.strip()]
  if not normalized:
    raise ValueError("No hotkey keys")
  gui.hotkey(*normalized)


def press(key: str) -> None:
  gui = _ensure()
  gui.press(key.strip().lower())


def click(
  x: int | None = None,
  y: int | None = None,
  *,
  button: str = "left",
  clicks: int = 1,
) -> None:
  gui = _ensure()
  if x is None or y is None:
    gui.click(button=button, clicks=clicks)
  else:
    gui.click(int(x), int(y), button=button, clicks=clicks)


def move_to(x: int, y: int, *, duration: float = 0.15) -> None:
  gui = _ensure()
  gui.moveTo(int(x), int(y), duration=max(0.0, duration))


def screenshot_size() -> tuple[int, int]:
  gui = _ensure()
  size = gui.size()
  return int(size.width), int(size.height)
