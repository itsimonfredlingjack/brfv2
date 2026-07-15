"""PDF text extraction with word-level bounding boxes (PyMuPDF)."""

from __future__ import annotations

import fitz  # PyMuPDF

from .schemas import PageData, Word


def extract_pdf(data: bytes) -> list[PageData]:
    """Extract every page's words in reading order.

    Coordinates are PDF points with top-left origin (fitz convention).
    Raises ValueError for files PyMuPDF cannot open as a PDF.
    """
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # fitz raises generic RuntimeError/EmptyFileError
        raise ValueError(f"Kunde inte läsa PDF: {exc}") from exc

    pages: list[PageData] = []
    try:
        for i, page in enumerate(doc):
            raw = page.get_text("words")  # (x0,y0,x1,y1, text, block, line, word_no)
            raw.sort(key=lambda w: (w[5], w[6], w[7]))
            words = [
                Word(text=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3], block=w[5], line=w[6])
                for w in raw
                if w[4].strip()
            ]
            pages.append(
                PageData(
                    number=i + 1,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    rotation=int(page.rotation),
                    words=words,
                )
            )
    finally:
        doc.close()
    return pages
