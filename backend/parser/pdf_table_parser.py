"""
pdf_table_parser.py
────────────────────
Reformats table-like blocks from pre-extracted PDF text so that Gemini
sees cleaner, more structured input.

Since the crawler already extracted PDF text via PyMuPDF, this module
does NOT re-open any PDF file. Instead it detects tab/whitespace-aligned
columns in the raw text and converts them to pipe-delimited markdown tables.
"""

import re
from typing import Optional


# Minimum columns to consider a line as a table row
_MIN_COLS = 2
# Minimum consecutive table-like lines to emit as a block
_MIN_ROWS = 2


def _is_table_row(line: str) -> bool:
    """Return True if the line looks like a table row (multiple tab/multi-space segments)."""
    # Two or more tab separators
    if line.count("\t") >= _MIN_COLS - 1:
        return True
    # Two or more segments separated by 3+ spaces
    parts = re.split(r" {3,}", line.strip())
    return len(parts) >= _MIN_COLS


def _normalise_row(line: str) -> list[str]:
    """Split a line into cells, stripping whitespace."""
    if "\t" in line:
        cells = line.split("\t")
    else:
        cells = re.split(r" {2,}", line.strip())
    return [c.strip() for c in cells if c.strip()]


def extract_tables_text(raw_text: str) -> Optional[str]:
    """
    Detect and reformat table-like sections in PDF-extracted text.

    Args:
        raw_text: Plain text already extracted from a PDF by the crawler.

    Returns:
        A string containing markdown-formatted tables, or an empty string
        if no table-like blocks were detected.
    """
    if not raw_text:
        return ""

    lines = raw_text.splitlines()
    blocks: list[str] = []
    current_block: list[list[str]] = []

    def flush_block():
        nonlocal current_block
        if len(current_block) >= _MIN_ROWS:
            # Determine column count from the widest row
            n_cols = max(len(r) for r in current_block)
            # Pad all rows to the same width
            padded = [r + [""] * (n_cols - len(r)) for r in current_block]
            # Build markdown table
            table_lines = []
            # Header row = first row
            header = padded[0]
            table_lines.append("| " + " | ".join(header) + " |")
            table_lines.append("| " + " | ".join(["---"] * n_cols) + " |")
            for row in padded[1:]:
                table_lines.append("| " + " | ".join(row) + " |")
            blocks.append("\n".join(table_lines))
        current_block = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_block()
            continue

        if _is_table_row(stripped):
            current_block.append(_normalise_row(stripped))
        else:
            flush_block()

    flush_block()

    return "\n\n".join(blocks)
