"""Split a PDF into a page range, a list of pages, or one file per page.

Uses PyMuPDF (import name: fitz), which Ultron already ships with — no extra
download needed the first time this runs.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
  import pymupdf as fitz
except ImportError:  # older PyMuPDF: only the deprecated import name exists
  import fitz


def parse_pages(spec: str, total: int) -> list[int]:
  """"2-5,8,1" (1-indexed, inclusive) -> 0-indexed page numbers, in the order given."""
  pages: list[int] = []
  for part in spec.split(","):
    part = part.strip()
    if not part:
      continue
    if "-" in part:
      start_text, end_text = part.split("-", 1)
      start, end = int(start_text), int(end_text)
      if start > end:
        start, end = end, start
      pages.extend(range(start, end + 1))
    else:
      pages.append(int(part))
  for page in pages:
    if page < 1 or page > total:
      raise ValueError(f"Page {page} is out of range (this PDF has {total} page(s)).")
  return [page - 1 for page in pages]


def resolve_output(output: str, input_path: str) -> str:
  """A bare output name (no folder) lands next to the input file, not in the working folder."""
  if os.path.dirname(output):
    return output
  return os.path.join(os.path.dirname(os.path.abspath(input_path)), output)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("input", help="Path to the source PDF")
  parser.add_argument("output", help="Output PDF file (with --pages) or folder (with --each)")
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--pages", help='Pages to keep, e.g. "2-5" or "1,3,7-9" (1-indexed)')
  group.add_argument("--each", action="store_true", help="Split into one file per page")
  args = parser.parse_args()

  if not os.path.isfile(args.input):
    print(f"Input file not found: {args.input}")
    return 1

  source = fitz.open(args.input)
  total = source.page_count
  print(f"'{args.input}' has {total} page(s).")

  if args.each:
    out_dir = args.output
    os.makedirs(out_dir, exist_ok=True)
    width = len(str(total))
    for index in range(total):
      writer = fitz.open()
      writer.insert_pdf(source, from_page=index, to_page=index)
      writer.save(os.path.join(out_dir, f"page_{index + 1:0{width}}.pdf"))
      writer.close()
    print(f"Wrote {total} single-page file(s) to {out_dir}")
    return 0

  try:
    indices = parse_pages(args.pages, total)
  except ValueError as exc:
    print(str(exc))
    return 1

  writer = fitz.open()
  for index in indices:
    writer.insert_pdf(source, from_page=index, to_page=index)
  output = resolve_output(args.output, args.input)
  os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
  writer.save(output)
  writer.close()
  shown = ",".join(str(index + 1) for index in indices)
  print(f"Wrote {len(indices)} page(s) [{shown}] to {output}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
