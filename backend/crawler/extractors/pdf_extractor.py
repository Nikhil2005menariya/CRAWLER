import io
from typing import Iterable

import fitz
import pdfplumber


def extract_pdf(content: bytes) -> str:
    text_chunks = []
    text_chunks.extend(_extract_text(content))
    text_chunks.extend(_extract_tables(content))
    return "\n".join(chunk for chunk in text_chunks if chunk)


def _extract_text(content: bytes) -> Iterable[str]:
    with fitz.open(stream=content, filetype="pdf") as document:
        for page in document:
            text = page.get_text("text")
            if text:
                yield text.strip()


def _extract_tables(content: bytes) -> Iterable[str]:
    with pdfplumber.open(io.BytesIO(content)) as document:
        for page in document.pages:
            for table in page.extract_tables() or []:
                if not table:
                    continue
                yield _table_to_text(table)


def _table_to_text(table: list[list[str | None]]) -> str:
    rows = []
    for row in table:
        cleaned = [(cell or "").strip() for cell in row]
        rows.append("\t".join(cleaned))
    return "\n".join(rows)
