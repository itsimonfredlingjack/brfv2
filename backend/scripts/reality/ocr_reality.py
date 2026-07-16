"""OCR reality measurement over a local corpus of REAL BRF PDFs — fully
offline, no document content in the output JSON.

Scanned PDFs (no text layer): tesseract word boxes at 250+150 dpi, confidence
stats, ink-coverage of boxes (do boxes sit on dark pixels?), dual-DPI
self-consistency quote-match through the app's find_spans, blank-page
detection, and overlay PNGs for human review (gitignored out/).

Born-digital PDFs: (a) calibration — OCR coordinate drift and word match vs
the embedded-text truth on a REAL layout; (b) end-to-end highlight fidelity —
auto-extracted real passages located in the OCR word stream via find_spans,
then OCR-derived line rects compared against embedded-truth rects. This is the
measured basis for the scanned-ingestion go/no-go.

Usage: uv run python -m scripts.reality.ocr_reality [--folder DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz  # noqa: E402

from app.normalize import find_spans  # noqa: E402
from scripts.ocr_spike import TesseractAdapter, calibrate_page, rasterize  # noqa: E402

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_FOLDER = BACKEND.parent / "DONT_PUSH_brf_stuff"
DEFAULT_OUT = BACKEND / "out" / "reality"

adapter = TesseractAdapter(lang="swe")


def classify(pdf: Path) -> tuple[str, int]:
    doc = fitz.open(str(pdf))
    chars = sum(len(pg.get_text().strip()) for pg in doc)
    n = len(doc)
    doc.close()
    return ("digital" if chars > 100 * n else "scan"), n


def ocr_doc(pdf_path: Path, dpi: int) -> list[list]:
    doc = fitz.open(str(pdf_path))
    n = len(doc)

    def one(i: int):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / f"p{i}.png"
            rasterize(doc[i], dpi, png)
            try:
                return adapter.ocr_page(png, dpi)
            except Exception as exc:
                print(f"  OCR FAIL {pdf_path.name} p{i+1}@{dpi}: {exc}", flush=True)
                return []

    with ThreadPoolExecutor(max_workers=4) as ex:
        pages = list(ex.map(one, range(n)))
    doc.close()
    return pages


def ink_metrics(pdf_path: Path, pages_words: list[list], dpi: int = 250) -> dict:
    doc = fitz.open(str(pdf_path))
    scale = dpi / 72.0
    box_fracs: list[float] = []
    on_ink = 0
    total = 0
    for i, words in enumerate(pages_words):
        if not words or np is None:
            continue
        pix = doc[i].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width]
        dark = arr < 140
        page_dark = float(dark.mean())
        for w in words:
            x0, y0 = max(0, int(w.x0 * scale)), max(0, int(w.y0 * scale))
            x1, y1 = min(pix.width, int(w.x1 * scale)), min(pix.height, int(w.y1 * scale))
            if x1 <= x0 or y1 <= y0:
                continue
            frac = float(dark[y0:y1, x0:x1].mean())
            box_fracs.append(frac)
            total += 1
            if frac > max(0.04, 2 * page_dark):
                on_ink += 1
    doc.close()
    return {
        "boxes": total,
        "in_box_dark_mean": round(statistics.fmean(box_fracs), 4) if box_fracs else None,
        "on_ink_rate": round(on_ink / total, 4) if total else None,
    }


def overlays(pdf_path: Path, pages_words: list[list], out_dir: Path, dpi: int = 150) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    for i, words in enumerate(pages_words):
        page = doc[i]
        shape = page.new_shape()
        for w in words:
            shape.draw_rect(fitz.Rect(w.x0, w.y0, w.x1, w.y1))
        shape.finish(color=(1, 0, 0), width=0.4)
        shape.commit()
        page.get_pixmap(dpi=dpi).save(str(out_dir / f"page-{i+1}-overlay.png"))
    doc.close()


def self_consistency(pages250: list[list], pages150: list[list], min_conf: float = 85.0) -> dict:
    """High-confidence 8-word windows from the 250dpi read, searched in the
    150dpi stream via find_spans — a correctness proxy when no ground truth
    exists. Biased toward easy regions (high conf); report alongside the
    born-digital calibration, never alone."""
    stream150 = [w.text for pg in pages150 for w in pg]
    samples = found = 0
    win = 8
    for pg in pages250:
        i = 0
        while i + win <= len(pg):
            window = pg[i : i + win]
            if all(w.conf >= min_conf for w in window):
                samples += 1
                if find_spans(stream150, " ".join(w.text for w in window)):
                    found += 1
                i += 25
            else:
                i += 5
    return {"windows": samples, "found": found, "rate": round(found / samples, 4) if samples else None}


def conf_stats(pages_words: list[list]) -> dict:
    confs = sorted(w.conf for pg in pages_words for w in pg if w.conf >= 0)
    if not confs:
        return {"mean": None, "p10": None, "n": 0}
    return {
        "mean": round(statistics.fmean(confs), 1),
        "p10": round(confs[int(0.10 * (len(confs) - 1))], 1),
        "n": len(confs),
    }


def extract_passages(doc: fitz.Document, per_page: int = 3, max_n: int = 30) -> list[tuple[int, str]]:
    """Real 6–16-word sentences from embedded text whose truth rects resolve
    via search_for. Long digit-bearing tokens are skipped (PII hygiene)."""
    out: list[tuple[int, str]] = []
    for pno in range(len(doc)):
        n_page = 0
        for cand in doc[pno].get_text().split(". "):
            if "-\n" in cand or n_page >= per_page:
                continue
            flat = " ".join(cand.split())
            words = flat.split()
            if not (6 <= len(words) <= 16):
                continue
            if any(any(ch.isdigit() for ch in w) and len(w) > 8 for w in words):
                continue
            if doc[pno].search_for(flat):
                out.append((pno, flat))
                n_page += 1
    return out[:max_n]


def line_rects(words: list, span: tuple[int, int]) -> list[fitz.Rect]:
    sel = words[span[0] : span[1] + 1]
    if not sel:
        return []
    heights = sorted(w.y1 - w.y0 for w in sel)
    med_h = heights[len(heights) // 2]
    lines: list[list] = [[sel[0]]]
    for w in sel[1:]:
        prev = lines[-1][-1]
        if abs(((w.y0 + w.y1) / 2) - ((prev.y0 + prev.y1) / 2)) > 0.6 * med_h:
            lines.append([w])
        else:
            lines[-1].append(w)
    rects = []
    for ln in lines:
        r = fitz.Rect(ln[0].x0, ln[0].y0, ln[0].x1, ln[0].y1)
        for w in ln[1:]:
            r |= fitz.Rect(w.x0, w.y0, w.x1, w.y1)
        rects.append(r)
    return rects


def rect_overlap(truth: list[fitz.Rect], ocr: list[fitz.Rect]) -> tuple[float, float]:
    def best_frac(rs: list[fitz.Rect], others: list[fitz.Rect]) -> float:
        fracs = []
        for r in rs:
            area = r.get_area()
            if area <= 0:
                continue
            inter = max((fitz.Rect(r) & o).get_area() for o in others) if others else 0.0
            fracs.append(inter / area)
        return statistics.fmean(fracs) if fracs else 0.0

    return best_frac(truth, ocr), best_frac(ocr, truth)


def highlight_fidelity(pdf_path: Path, pages_words: list[list], passages: list[tuple[int, str]]) -> dict:
    doc = fitz.open(str(pdf_path))
    per = []
    for pno, passage in passages:
        truth = doc[pno].search_for(passage)
        words = pages_words[pno]
        span_list = find_spans([w.text for w in words], passage)
        row = {"page": pno + 1, "n_words": len(passage.split()), "found": bool(span_list)}
        if span_list and truth:
            cov, prec = rect_overlap(truth, line_rects(words, span_list[0]))
            row.update(coverage=round(cov, 3), precision=round(prec, 3), landed=cov >= 0.7 and prec >= 0.4)
        per.append(row)
    doc.close()
    found = sum(1 for r in per if r["found"])
    landed = sum(1 for r in per if r.get("landed"))
    return {
        "passages": len(per),
        "found_by_find_spans": found,
        "landed_correctly": landed,
        "found_rate": round(found / len(per), 3) if per else None,
        "landed_rate": round(landed / len(per), 3) if per else None,
        "detail": per,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if adapter.availability():
        raise SystemExit(adapter.availability())

    report: dict = {"scans": {}, "digital": {}}
    for i, pdf in enumerate(sorted(args.folder.glob("*.pdf"))):
        kind, n_pages = classify(pdf)
        slug = f"doc{i+1:02d}-{kind}"  # deliberately anonymous — filenames may name a BRF
        print(f"== {slug} ({n_pages} pages) ==", flush=True)
        if kind == "scan":
            p250 = ocr_doc(pdf, 250)
            p150 = ocr_doc(pdf, 150)
            report["scans"][slug] = {
                "pages": n_pages,
                "ocr_words_total_250": sum(len(p) for p in p250),
                "pages_with_no_words_250": [j + 1 for j, p in enumerate(p250) if not p],
                "conf_250": conf_stats(p250),
                "ink_250": ink_metrics(pdf, p250, 250),
                "self_consistency_250_vs_150": self_consistency(p250, p150),
            }
            overlays(pdf, p250, args.out / "overlays" / slug)
        else:
            doc = fitz.open(str(pdf))
            passages = extract_passages(doc)
            dig: dict = {"pages": n_pages, "passages_used": len(passages)}
            for dpi in (250, 150):
                pages_words = ocr_doc(pdf, dpi)
                cals = [calibrate_page(doc[j], pages_words[j]) for j in range(len(doc))]
                drifts = [c["drift_pct_mean"] for c in cals if c["drift_pct_mean"] is not None]
                p95s = [c["drift_pct_p95"] for c in cals if c["drift_pct_p95"] is not None]
                dig[f"dpi{dpi}"] = {
                    "word_match_rate_mean": round(statistics.fmean(c["match_rate"] for c in cals), 3),
                    "drift_pct_mean": round(statistics.fmean(drifts), 3) if drifts else None,
                    "drift_pct_p95_max": round(max(p95s), 3) if p95s else None,
                    "highlight_fidelity": highlight_fidelity(pdf, pages_words, passages),
                    "conf": conf_stats(pages_words),
                }
                if dpi == 250:
                    overlays(pdf, pages_words, args.out / "overlays" / slug)
            doc.close()
            report["digital"][slug] = dig

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "ocr_measure.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"DONE → {out_json}", flush=True)


if __name__ == "__main__":
    main()
