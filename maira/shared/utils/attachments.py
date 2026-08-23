"""Read local files so chat can include them in the LLM prompt."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

# ponytail: whole-file inject; chunk/RAG if people attach books
MAX_BYTES = 80_000
MAX_FILES = 5
MAX_PDF_PAGES = 8
MIN_PDF_CHARS = 40
FILE_MARKER = "\n--- file:"
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class AttachmentError(Exception):
  pass


def read_text_file(path: Path, *, max_bytes: int = MAX_BYTES) -> str:
  target = path.expanduser().resolve()
  if not target.is_file():
    raise AttachmentError(f"{path.name} is not a file")
  raw = target.read_bytes()
  if b"\x00" in raw[:8192]:
    raise AttachmentError(f"{path.name} is not a text file")
  truncated = len(raw) > max_bytes
  if truncated:
    raw = raw[:max_bytes]
  text = raw.decode("utf-8", errors="replace").replace("\x00", "")
  if truncated:
    text += f"\n\n[truncated to {max_bytes} bytes]"
  return text


def can_attach(path: Path) -> None:
  """Cheap pre-check so the file picker does not OCR on click."""
  suffix = path.suffix.lower()
  if suffix in PDF_SUFFIXES or suffix in IMAGE_SUFFIXES:
    if path.stat().st_size == 0:
      raise AttachmentError(f"{path.name} is empty")
    return
  read_text_file(path)


def read_attachment(path: Path, *, max_bytes: int = MAX_BYTES) -> str:
  suffix = path.suffix.lower()
  if suffix in PDF_SUFFIXES:
    return _read_pdf(path, max_bytes=max_bytes)
  if suffix in IMAGE_SUFFIXES:
    return _read_image(path)
  return read_text_file(path, max_bytes=max_bytes)


def compose_message(user_text: str, paths: Sequence[Path]) -> tuple[str, str, list[str]]:
  """Return (display, prompt, errors). Prompt is what the LLM sees."""
  cleaned = user_text.strip()
  errors: list[str] = []
  bodies: list[tuple[str, str]] = []
  for path in paths[:MAX_FILES]:
    try:
      bodies.append((path.name, read_attachment(path)))
    except (OSError, AttachmentError) as exc:
      errors.append(str(exc))

  if not cleaned and not bodies:
    return "", "", errors

  if not bodies:
    return cleaned, cleaned, errors

  names = ", ".join(name for name, _ in bodies)
  lead = cleaned or "Please review the attached file(s)."
  display = f"{lead}\n\nAttached: {names}"
  chunks = [display]
  for name, body in bodies:
    chunks.append(f"--- file: {name} ---\n{body}\n--- end file ---")
  return display, "\n\n".join(chunks), errors


def visible_text(content: str) -> str:
  """Hide file bodies in the chat bubble; keep the short attached-names line."""
  if FILE_MARKER not in content:
    return content
  return content.split(FILE_MARKER, 1)[0].strip()


def _truncate(text: str, max_bytes: int) -> str:
  encoded = text.encode("utf-8")
  if len(encoded) <= max_bytes:
    return text
  return encoded[:max_bytes].decode("utf-8", errors="ignore") + f"\n\n[truncated to {max_bytes} bytes]"


def _read_pdf(path: Path, *, max_bytes: int) -> str:
  try:
    import fitz
  except ImportError as exc:
    raise AttachmentError("PDF attach needs pymupdf. Run: pip install pymupdf") from exc

  doc = fitz.open(path)
  try:
    page_count = min(doc.page_count, MAX_PDF_PAGES)
    extracted = "\n".join(doc[i].get_text() or "" for i in range(page_count)).strip()
    if len(extracted) >= MIN_PDF_CHARS:
      if doc.page_count > MAX_PDF_PAGES:
        extracted += f"\n\n[truncated to {MAX_PDF_PAGES} pages]"
      return _truncate(extracted, max_bytes)

    from PIL import Image

    parts: list[str] = []
    for i in range(page_count):
      pix = doc[i].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
      image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
      text = _ocr_image(image).strip()
      if text:
        parts.append(f"[page {i + 1}]\n{text}")
    if not parts:
      raise AttachmentError(f"No text found in {path.name}")
    joined = "\n\n".join(parts)
    if doc.page_count > MAX_PDF_PAGES:
      joined += f"\n\n[truncated to {MAX_PDF_PAGES} pages]"
    return _truncate(joined, max_bytes)
  finally:
    doc.close()


def _read_image(path: Path) -> str:
  try:
    from PIL import Image
  except ImportError as exc:
    raise AttachmentError("Image attach needs Pillow. Run: pip install Pillow") from exc
  with Image.open(path) as image:
    text = _ocr_image(_fit_image(image.convert("RGB"))).strip()
  if not text:
    raise AttachmentError(f"No text found in {path.name}")
  return text


def _fit_image(image, max_side: int = 2000):
  width, height = image.size
  scale = min(1.0, max_side / max(width, height))
  if scale < 1:
    image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
  return image


def _ocr_image(image) -> str:
  try:
    from winocr import recognize_pil_sync
  except ImportError as exc:
    raise AttachmentError("Image/PDF scan attach needs winocr. Run: pip install winocr") from exc

  last_error = "Windows OCR failed"
  for lang in ("en-US", "en", "hi-IN"):
    try:
      text = _ocr_text(recognize_pil_sync(image, lang))
      if text:
        return text
    except Exception as exc:  # noqa: BLE001
      last_error = str(exc)
  raise AttachmentError(f"No text found in image ({last_error})")


def _ocr_text(result: object) -> str:
  if isinstance(result, dict):
    raw = str(result.get("text") or "")
  else:
    raw = str(getattr(result, "text", "") or "")
  return raw.replace("\ufffd", "").strip()
