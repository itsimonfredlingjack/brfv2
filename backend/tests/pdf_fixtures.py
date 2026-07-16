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


def build_image_only_pdf(pages: list[list[tuple[str, float, float]]], page_size=A4, render_scale=4.0) -> bytes:
    """Build a PDF with NO text layer — a synthetic stand-in for a scanned
    document. Each page's text is rendered (via build_pdf's own text-drawing
    machinery) then rasterized to a pixmap and inserted as an image on a
    fresh page, exactly like a scan: `extract_pdf` must find zero words on
    every page. `render_scale` oversamples the source render (4.0 ~= 288
    ppi) so a downstream OCR rasterization at typical dpi (~250) has enough
    pixel detail to read back accurately, matching real scan resolution."""
    text_doc = fitz.open(stream=build_pdf(pages, page_size=page_size), filetype="pdf")
    out_doc = fitz.open()
    for page in text_doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale))
        img_page = out_doc.new_page(width=page_size[0], height=page_size[1])
        img_page.insert_image(img_page.rect, pixmap=pix)
    data = out_doc.tobytes()
    out_doc.close()
    text_doc.close()
    return data
