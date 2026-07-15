"""Deterministic in-memory PDF builders for tests."""

from __future__ import annotations

import fitz  # PyMuPDF

A4 = (595.0, 842.0)


def build_pdf(pages: list[list[tuple[str, float, float]]], page_size=A4) -> bytes:
    """Build a PDF. Each page is a list of (text, x, y) lines; y is the
    baseline in top-left-origin points. Returns PDF bytes."""
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=page_size[0], height=page_size[1])
        for text, x, y in lines:
            page.insert_text(fitz.Point(x, y), text, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


def build_paragraph_pdf(paragraphs: list[list[str]], page_size=A4, start_y=72.0, leading=14.0, gap=22.0) -> bytes:
    """One page; each paragraph is a list of pre-wrapped lines. Paragraphs are
    separated by extra vertical gap so PyMuPDF sees them as separate blocks."""
    lines: list[tuple[str, float, float]] = []
    y = start_y
    for para in paragraphs:
        for line in para:
            lines.append((line, 72.0, y))
            y += leading
        y += gap
    return build_pdf([lines], page_size=page_size)
