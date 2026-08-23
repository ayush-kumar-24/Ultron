"""Unit tests for chat file attachments."""

from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from maira.shared.utils import attachments as att
from maira.shared.utils.attachments import (
  compose_message,
  read_attachment,
  read_text_file,
  visible_text,
)


def test_read_text_file(tmp_path: Path) -> None:
  path = tmp_path / "notes.md"
  path.write_text("hello maira", encoding="utf-8")
  assert read_text_file(path) == "hello maira"


def test_rejects_binary(tmp_path: Path) -> None:
  path = tmp_path / "blob.bin"
  path.write_bytes(b"\x00\x01\x02\x03" * 20)
  try:
    read_text_file(path)
  except Exception as exc:
    assert "not a text file" in str(exc)
  else:
    raise AssertionError("binary file should fail")


def test_compose_and_visible(tmp_path: Path) -> None:
  path = tmp_path / "notes.md"
  path.write_text("secret contents", encoding="utf-8")
  display, prompt, errors = compose_message("summarize this", [path])
  assert not errors
  assert display == "summarize this\n\nAttached: notes.md"
  assert "secret contents" in prompt
  assert visible_text(prompt) == display
  assert "secret contents" not in visible_text(prompt)


def test_compose_files_only(tmp_path: Path) -> None:
  path = tmp_path / "a.py"
  path.write_text("print(1)", encoding="utf-8")
  display, prompt, errors = compose_message("", [path])
  assert not errors
  assert "Attached: a.py" in display
  assert "print(1)" in prompt


def test_truncates_large_file(tmp_path: Path) -> None:
  path = tmp_path / "big.txt"
  path.write_text("x" * 1000, encoding="utf-8")
  text = read_text_file(path, max_bytes=50)
  assert text.endswith("[truncated to 50 bytes]")
  assert len(text) < 1000


def test_reads_digital_pdf(tmp_path: Path) -> None:
  path = tmp_path / "note.pdf"
  doc = fitz.open()
  page = doc.new_page()
  page.insert_text((72, 72), "Invoice total is 42")
  doc.save(path)
  doc.close()
  assert "Invoice total is 42" in read_attachment(path)


def test_ocr_image(tmp_path: Path, monkeypatch) -> None:
  path = tmp_path / "shot.png"
  image = Image.new("RGB", (200, 60), "white")
  ImageDraw.Draw(image).text((10, 20), "hello", fill="black")
  image.save(path)
  monkeypatch.setattr(att, "_ocr_image", lambda _img: "hello from screenshot")
  assert read_attachment(path) == "hello from screenshot"


def test_ocr_scanned_pdf(tmp_path: Path, monkeypatch) -> None:
  path = tmp_path / "scan.pdf"
  doc = fitz.open()
  doc.new_page()
  doc.save(path)
  doc.close()
  monkeypatch.setattr(att, "_ocr_image", lambda _img: "scanned line")
  assert "scanned line" in read_attachment(path)
