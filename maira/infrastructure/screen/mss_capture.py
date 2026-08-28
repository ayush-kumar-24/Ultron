"""mss-backed screen capture (optional dependency).

mss grabs raw BGRA; Pillow encodes it to PNG. Both are lazy-loaded so the app
starts fine on a machine where neither is installed.
"""

from __future__ import annotations

import io

from loguru import logger

from maira.core.interfaces.screen import (
  Display,
  ScreenCapture,
  ScreenRegion,
  ScreenShot,
)

_mss = None
_load_error: str | None = None

INSTALL_HINT = 'Install with: pip install -e ".[screen]"'


def _ensure():
  global _mss, _load_error
  if _mss is not None:
    return _mss
  if _load_error is not None:
    raise RuntimeError(_load_error)
  try:
    import mss

    _mss = mss
    return _mss
  except Exception as exc:  # noqa: BLE001
    _load_error = f"mss unavailable ({exc}). {INSTALL_HINT}"
    raise RuntimeError(_load_error) from exc


def _ensure_pillow():
  try:
    from PIL import Image

    return Image
  except Exception as exc:  # noqa: BLE001
    raise RuntimeError(f"Pillow unavailable ({exc}). {INSTALL_HINT}") from exc


def is_available() -> tuple[bool, str]:
  try:
    _ensure()
    _ensure_pillow()
    return True, "ready"
  except RuntimeError as exc:
    return False, str(exc)


class MssScreenCapture(ScreenCapture):
  """Captures the desktop with mss. One frame per call — never a stream."""

  def is_available(self) -> tuple[bool, str]:
    return is_available()

  def displays(self) -> list[Display]:
    try:
      mss = _ensure()
    except RuntimeError as exc:
      logger.warning("Screen capture unavailable: {}", exc)
      return []
    out: list[Display] = []
    with mss.mss() as sct:
      # monitors[0] is the virtual desktop (all screens); 1..n are the real ones.
      for index, mon in enumerate(sct.monitors[1:], start=1):
        out.append(
          Display(
            index=index,
            region=ScreenRegion(
              left=int(mon["left"]),
              top=int(mon["top"]),
              width=int(mon["width"]),
              height=int(mon["height"]),
            ),
            primary=index == 1,
          )
        )
    return out

  def capture(
    self,
    *,
    display: int | None = None,
    region: ScreenRegion | None = None,
  ) -> ScreenShot:
    mss = _ensure()
    Image = _ensure_pillow()

    if region is not None and not region.is_valid():
      raise ValueError("Capture region must have positive width and height")

    with mss.mss() as sct:
      monitors = sct.monitors
      if region is not None:
        index = display if display is not None else 0
        box = {
          "left": region.left,
          "top": region.top,
          "width": region.width,
          "height": region.height,
        }
      else:
        # Default to the primary display, not the whole virtual desktop:
        # a merged multi-monitor frame OCRs badly.
        index = display if display is not None else (1 if len(monitors) > 1 else 0)
        if index < 0 or index >= len(monitors):
          raise ValueError(f"No such display: {index}")
        box = monitors[index]

      raw = sct.grab(box)
      img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=1)
    return ScreenShot(
      png=buf.getvalue(),
      width=img.width,
      height=img.height,
      region=region
      or ScreenRegion(
        left=int(box["left"]),
        top=int(box["top"]),
        width=int(box["width"]),
        height=int(box["height"]),
      ),
      display=index,
    )
