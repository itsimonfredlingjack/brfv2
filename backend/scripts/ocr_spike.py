"""OCR spike measurement rig (SPEC §5) — builds the measurement, NOT the decision.

Given a (typically scanned) PDF, the rig:
  1. rasterizes each page,
  2. runs candidate OCR adapters (tesseract via CLI TSV; more adapters slot in
     behind the same interface),
  3. writes per-page overlay PNGs with the extracted word boxes drawn in,
  4. computes metrics into metrics.json:
       - calibration mode (digital PDFs): coordinate drift vs PyMuPDF truth
       - quote-match rate: expected passages findable through the same §2
         normalization pipeline the citation verifier uses.

The go/no-go call needs real BRF scans and is deliberately out of scope.

Usage:
    uv run python -m scripts.ocr_spike PDF [--adapter tesseract] [--dpi 250]
        [--calibrate] [--passages FILE] [--out out/ocr_spike] [--lang swe]
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.normalize import find_spans, normalize_text  # noqa: E402


@dataclass
class OCRWord:
    text: str
    x0: float  # PDF points, top-left origin
    y0: float
    x1: float
    y1: float
    conf: float


class TesseractAdapter:
    """Word boxes via the tesseract CLI's TSV output — no Python deps."""

    name = "tesseract"

    def __init__(self, lang: str = "swe") -> None:
        self.lang = lang

    def availability(self) -> str | None:
        if shutil.which("tesseract") is None:
            return (
                "tesseract-binären saknas "
                "(Fedora: sudo dnf install tesseract tesseract-langpack-swe)"
            )
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
        if self.lang not in langs.split():
            return (
                f"språkpaketet '{self.lang}' saknas "
                f"(Fedora: sudo dnf install tesseract-langpack-{self.lang})"
            )
        return None

    def ocr_page(self, png_path: Path, dpi: int) -> list[OCRWord]:
        proc = subprocess.run(
            ["tesseract", str(png_path), "stdout", "-l", self.lang, "--dpi", str(dpi), "tsv"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tesseract fel: {proc.stderr[:300]}")
        words: list[OCRWord] = []
        scale = 72.0 / dpi  # raster px → PDF points
        lines = proc.stdout.splitlines()
        header = lines[0].split("\t")
        idx = {k: i for i, k in enumerate(header)}
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) != len(header) or f[idx["level"]] != "5":
                continue
            text = f[idx["text"]].strip()
            if not text:
                continue
            left, top = float(f[idx["left"]]), float(f[idx["top"]])
            w, h = float(f[idx["width"]]), float(f[idx["height"]])
            words.append(
                OCRWord(
                    text=text,
                    x0=left * scale,
                    y0=top * scale,
                    x1=(left + w) * scale,
                    y1=(top + h) * scale,
                    conf=float(f[idx["conf"]]),
                )
            )
        return words


ADAPTERS = {"tesseract": TesseractAdapter}


def rasterize(page: fitz.Page, dpi: int, out_png: Path) -> None:
    pix = page.get_pixmap(dpi=dpi)
    pix.save(str(out_png))


def overlay_png(page: fitz.Page, words: list[OCRWord], dpi: int, out_png: Path) -> None:
    """Draw OCR word boxes on the rasterized page."""
    pix = page.get_pixmap(dpi=dpi)
    doc = fitz.open()
    p = doc.new_page(width=page.rect.width, height=page.rect.height)
    p.insert_image(page.rect, pixmap=pix)
    for w in words:
        p.draw_rect(fitz.Rect(w.x0, w.y0, w.x1, w.y1), color=(1, 0, 0), width=0.4)
    p.get_pixmap(dpi=dpi).save(str(out_png))
    doc.close()


def calibrate_page(page: fitz.Page, ocr_words: list[OCRWord]) -> dict:
    """Digital PDFs only: match OCR words to the embedded-text truth and
    measure coordinate drift (as % of page height)."""
    truth = [
        (normalize_text(w[4]), (w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
        for w in page.get_text("words")
        if w[4].strip()
    ]
    page_h = page.rect.height
    drifts: list[float] = []
    matched = 0
    used: set[int] = set()
    for ow in ocr_words:
        key = normalize_text(ow.text)
        if not key:
            continue
        cx, cy = (ow.x0 + ow.x1) / 2, (ow.y0 + ow.y1) / 2
        best_i, best_d = None, None
        for i, (t, tx, ty) in enumerate(truth):
            if i in used or t != key:
                continue
            d = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            used.add(best_i)
            matched += 1
            drifts.append(100.0 * best_d / page_h)
    n_truth = len(truth)
    return {
        "truth_words": n_truth,
        "ocr_words": len(ocr_words),
        "matched": matched,
        "match_rate": matched / n_truth if n_truth else 0.0,
        "drift_pct_mean": round(statistics.fmean(drifts), 3) if drifts else None,
        "drift_pct_p95": round(sorted(drifts)[int(0.95 * (len(drifts) - 1))], 3) if drifts else None,
    }


def quote_match_rate(all_words: list[str], passages: list[str]) -> dict:
    results = {}
    for p in passages:
        p = p.strip()
        if p:
            results[p[:80]] = bool(find_spans(all_words, p))
    found = sum(results.values())
    return {"passages": len(results), "found": found, "rate": found / len(results) if results else None, "detail": results}


def run(pdf_path: Path, adapter_name: str, dpi: int, calibrate: bool, passages_file: Path | None, out_dir: Path, lang: str) -> dict:
    adapter = ADAPTERS[adapter_name](lang=lang)
    unavailable = adapter.availability()
    if unavailable:
        raise SystemExit(f"Adapter '{adapter_name}' otillgänglig: {unavailable}")

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    per_page = []
    all_ocr_words: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        for page in doc:
            png = Path(td) / f"p{page.number + 1}.png"
            rasterize(page, dpi, png)
            words = adapter.ocr_page(png, dpi)
            all_ocr_words.extend(w.text for w in words)
            overlay_png(page, words, dpi, out_dir / f"page-{page.number + 1}-overlay.png")
            info: dict = {"page": page.number + 1, "ocr_words": len(words)}
            if calibrate:
                info["calibration"] = calibrate_page(page, words)
            per_page.append(info)

    metrics: dict = {
        "pdf": pdf_path.name,
        "adapter": adapter.name,
        "lang": lang,
        "dpi": dpi,
        "pages": per_page,
    }
    if calibrate:
        cals = [p["calibration"] for p in per_page if p.get("calibration")]
        if cals:
            metrics["calibration_summary"] = {
                "match_rate_mean": round(statistics.fmean(c["match_rate"] for c in cals), 3),
                "drift_pct_mean": round(
                    statistics.fmean(c["drift_pct_mean"] for c in cals if c["drift_pct_mean"] is not None), 3
                ),
            }
    if passages_file:
        passages = passages_file.read_text("utf-8").splitlines()
        metrics["quote_match"] = quote_match_rate(all_ocr_words, passages)

    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    doc.close()
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--adapter", choices=sorted(ADAPTERS), default="tesseract")
    ap.add_argument("--dpi", type=int, default=250)
    ap.add_argument("--calibrate", action="store_true", help="digital PDF: drift vs embedded-text truth")
    ap.add_argument("--passages", type=Path, default=None, help="file with one expected passage per line")
    ap.add_argument("--out", type=Path, default=Path("out/ocr_spike"))
    ap.add_argument("--lang", default="swe")
    args = ap.parse_args()

    out_dir = args.out / args.pdf.stem.replace(" ", "_")
    metrics = run(args.pdf, args.adapter, args.dpi, args.calibrate, args.passages, out_dir, args.lang)
    print(json.dumps({k: v for k, v in metrics.items() if k != "pages"}, ensure_ascii=False, indent=2))
    print(f"Overlays + metrics.json → {out_dir}")


if __name__ == "__main__":
    main()
