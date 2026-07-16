"""Scanned-PDF ingestion via tesseract OCR.

Produces the SAME `PageData`/`Word` structures `extract.extract_pdf` produces
from a text layer (`schemas.py`), so everything downstream — chunker,
indexer, citations, highlights — runs unmodified with zero branching on
source. Subprocess + TSV pattern follows `scripts/ocr_spike.py:65`, but keeps
tesseract's `block_num`/`par_num`/`line_num` structure columns (the spike
discards them after computing plain word boxes) because
`citations._rects_for_span` groups word boxes into per-line rects by exactly
the `(Word.block, Word.line)` key (`citations.py:122-135`).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

from .schemas import PageData, Word

# Reality report §2 condition 1: garbage tail from letterhead graphics and
# table rules OCRs at very low confidence; ~60 is the measured gate.
OCR_MIN_CONF = 60.0

# tesseract's line_num is scoped to (block_num, par_num) and resets to 1 at
# the start of every paragraph. Multiplying par_num by a stride comfortably
# larger than any realistic per-paragraph line count and adding line_num
# gives a value that is unique per visual line within a block, and stable
# (no dependency on scan order) -- exactly the (block, line) grouping key
# citations._rects_for_span relies on.
_PAR_LINE_STRIDE = 10_000


def tesseract_available(lang: str = "swe") -> bool:
    """True if the `tesseract` binary is on PATH and has `lang` installed."""
    if shutil.which("tesseract") is None:
        return False
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return lang in langs.split()


def parse_tesseract_tsv(tsv: str, dpi: int, *, min_conf: float = OCR_MIN_CONF) -> list[Word]:
    """Parse tesseract `tsv` output into `Word` rows. PURE (no subprocess).

    Keeps level==5 (word) rows with non-blank text and conf >= min_conf,
    scales raster px -> PDF pt (72/dpi), and maps tesseract's block_num
    directly to Word.block. Word.line combines par_num and line_num (see
    _PAR_LINE_STRIDE) so words on one visual line share (block, line) and
    different visual lines never collide, even across a paragraph break
    where tesseract's own line_num resets to 1.
    """
    lines = tsv.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    idx = {k: i for i, k in enumerate(header)}
    scale = 72.0 / dpi

    words: list[Word] = []
    for raw in lines[1:]:
        f = raw.split("\t")
        if len(f) != len(header) or f[idx["level"]] != "5":
            continue
        text = f[idx["text"]].strip()
        if not text:
            continue
        conf = float(f[idx["conf"]])
        if conf < min_conf:
            continue
        left, top = float(f[idx["left"]]), float(f[idx["top"]])
        w, h = float(f[idx["width"]]), float(f[idx["height"]])
        par_num = int(f[idx["par_num"]])
        line_num = int(f[idx["line_num"]])
        words.append(
            Word(
                text=text,
                x0=left * scale,
                y0=top * scale,
                x1=(left + w) * scale,
                y1=(top + h) * scale,
                block=int(f[idx["block_num"]]),
                line=par_num * _PAR_LINE_STRIDE + line_num,
            )
        )
    return words


def ocr_pdf(data: bytes, *, dpi: int = 250, lang: str = "swe", min_conf: float = OCR_MIN_CONF) -> list[PageData]:
    """Rasterize + OCR every page of a scanned PDF into `PageData`.

    A page with no surviving words yields `words=[]` — never an exception:
    blank duplex backsides and drawing-only pages must skip, not fail
    (reality report §2 condition 2). A tesseract subprocess failure (bad
    exit code — an environment problem, not a content problem) still raises,
    matching `scripts/ocr_spike.py`'s behavior.
    """
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # fitz raises generic RuntimeError/EmptyFileError
        raise ValueError(f"Kunde inte läsa PDF: {exc}") from exc

    pages: list[PageData] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            for i, page in enumerate(doc):
                png_path = tmp_dir / f"p{i + 1}.png"
                pix = page.get_pixmap(dpi=dpi)
                pix.save(str(png_path))
                proc = subprocess.run(
                    ["tesseract", str(png_path), "stdout", "-l", lang, "--dpi", str(dpi), "tsv"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"tesseract fel: {proc.stderr[:300]}")
                words = parse_tesseract_tsv(proc.stdout, dpi, min_conf=min_conf)
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
