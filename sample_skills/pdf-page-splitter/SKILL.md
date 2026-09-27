---
name: pdf-page-splitter
description: Split a PDF into a chosen page range, a specific list of pages, or one file per page. Use this whenever the user wants specific pages pulled out of a PDF, wants a PDF split apart, or wants to extract certain pages into a new file.
license: MIT
---

# PDF Page Splitter

Splits a PDF with PyMuPDF (`fitz`), which Ultron already ships with — no extra download needed. One script: `scripts/split_pdf.py`.

## Usage

```
python scripts/split_pdf.py <input.pdf> <output.pdf> --pages <spec>
python scripts/split_pdf.py <input.pdf> <output_dir> --each
```

`<spec>` is a comma-separated list of page numbers and ranges, 1-indexed and inclusive:

- `--pages 5` — just page 5
- `--pages 2-5` — pages 2 through 5
- `--pages 1,3,7-9` — pages 1, 3, 7, 8 and 9, in that order (a page can repeat)

`--each` instead splits every page into its own file: `page_001.pdf`, `page_002.pdf`, … in `<output_dir>`.

Always give the **full path** to the user's PDF (e.g. `C:\Users\Ayush\Downloads\report.pdf`), never
just its file name — the script does not know the user's current folder. If `<output.pdf>` /
`<output_dir>` is just a bare name with no folder in it, the result is written next to the input file.

Before running, confirm with the user exactly which pages they want (ask if they only said "some
pages" or "the middle part"). The script prints the PDF's total page count first, so if a page is
out of range you'll see the error and can ask again with a valid number.

## Example

"split pages 3 to 7 out of report.pdf into their own file" →

```run
python scripts/split_pdf.py "C:\Users\Ayush\Downloads\report.pdf" "C:\Users\Ayush\Downloads\report_pages_3-7.pdf" --pages 3-7
```
