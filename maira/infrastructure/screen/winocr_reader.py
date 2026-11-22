"""Windows OCR via winocr (optional dependency).

Uses Windows.Media.Ocr through winocr: fully local, no model download, no network.
Falls back cleanly on non-Windows machines so tests and Linux dev still run.
"""

from __future__ import annotations

import asyncio
import io

from loguru import logger

from maira.core.interfaces.screen import ScreenReader, ScreenShot, ScreenText

_winocr = None
_load_error: str | None = None

INSTALL_HINT = 'Install with: pip install -e ".[screen]"  (Windows only)'


def _ensure():
  global _winocr, _load_error
  if _winocr is not None:
    return _winocr
  if _load_error is not None:
    raise RuntimeError(_load_error)
  try:
    import winocr

    _winocr = winocr
    return _winocr
  except Exception as exc:  # noqa: BLE001
    _load_error = f"winocr unavailable ({exc}). {INSTALL_HINT}"
    raise RuntimeError(_load_error) from exc


def is_available() -> tuple[bool, str]:
  try:
    _ensure()
    return True, "ready"
  except RuntimeError as exc:
    return False, str(exc)


def _field(obj, name: str):
  """winocr returns a dict on some versions and a WinRT object on others."""
  if isinstance(obj, dict):
    return obj.get(name)
  return getattr(obj, name, None)


def _text_from_result(result) -> str:
  return (_field(result, "text") or "").strip()


def _lines_from_result(result) -> tuple[str, ...]:
  lines = _field(result, "lines") or []
  out: list[str] = []
  for line in lines:
    text = (_field(line, "text") or "").strip()
    if text:
      out.append(text)
  return tuple(out)


class WinOcrScreenReader(ScreenReader):
  """Recognises text in a captured frame using the OS OCR engine."""

  def __init__(self, *, lang: str = "en") -> None:
    self._lang = lang

  def is_available(self) -> tuple[bool, str]:
    return is_available()

  def read(self, shot: ScreenShot) -> ScreenText:
    winocr = _ensure()
    if shot.is_empty():
      return ScreenText(text="", region=shot.region, display=shot.display, engine="winocr")

    try:
      from PIL import Image
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(f"Pillow unavailable ({exc}). {INSTALL_HINT}") from exc

    img = Image.open(io.BytesIO(shot.png))
    result = _recognize(winocr, img, self._lang)
    lines = _lines_from_result(result)
    # Prefer line breaks: the flat `text` field joins everything with spaces,
    # which destroys the layout Ultron needs to read an error or a dialog.
    text = "\n".join(lines) if lines else _text_from_result(result)
    logger.debug("winocr read {} chars / {} lines", len(text), len(lines))
    return ScreenText(
      text=text,
      lines=lines,
      region=shot.region,
      display=shot.display,
      engine="winocr",
    )


def _recognize(winocr, img, lang: str):
  """Call winocr from sync code.

  `recognize_pil` hands back a WinRT IAsyncOperation rather than a coroutine, so it
  cannot go through asyncio.run. `recognize_pil_sync` is the supported sync entry
  point; the awaitable path is kept only as a fallback for older winocr builds.
  """
  sync = getattr(winocr, "recognize_pil_sync", None)
  if sync is not None:
    return sync(img, lang)

  pending = winocr.recognize_pil(img, lang)
  to_coroutine = getattr(winocr, "to_coroutine", None)
  if to_coroutine is not None:
    pending = to_coroutine(pending)
  try:
    asyncio.get_running_loop()
  except RuntimeError:
    return asyncio.run(pending)
  # Called from inside a loop (e.g. a Qt/asyncio bridge): use a private one.
  loop = asyncio.new_event_loop()
  try:
    return loop.run_until_complete(pending)
  finally:
    loop.close()
