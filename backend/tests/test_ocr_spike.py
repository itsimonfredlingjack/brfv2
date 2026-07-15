"""OCR rig tests — run only where a tesseract binary with 'swe' exists."""

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ocr_spike import TesseractAdapter, run
from scripts.seed import render_pdf
from scripts.seed_content import DOCUMENTS


def tesseract_with_swe() -> bool:
    if shutil.which("tesseract") is None:
        return False
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "swe" in langs.split()


pytestmark = pytest.mark.skipif(not tesseract_with_swe(), reason="tesseract+swe not installed")


@pytest.mark.ocr
def test_calibration_on_digital_pdf(tmp_path):
    pdf = tmp_path / "digital.pdf"
    pdf.write_bytes(render_pdf(DOCUMENTS[3]))  # Snöröjningsavtal, 2 pages
    passages = tmp_path / "passages.txt"
    passages.write_text("Jourperioden löper från den 15 november till den 15 april\n", "utf-8")

    metrics = run(
        pdf, adapter_name="tesseract", dpi=250, calibrate=True,
        passages_file=passages, out_dir=tmp_path / "out", lang="swe",
    )

    cal = metrics["calibration_summary"]
    assert cal["match_rate_mean"] >= 0.85, "OCR should re-find ≥85% of rendered words"
    assert cal["drift_pct_mean"] <= 1.0, "mean drift must be ≪ 5% of page height"
    assert metrics["quote_match"]["rate"] == 1.0
    overlays = list((tmp_path / "out").glob("page-*-overlay.png"))
    assert len(overlays) == 2
    assert (tmp_path / "out" / "metrics.json").exists()


@pytest.mark.ocr
def test_adapter_reports_availability():
    assert TesseractAdapter(lang="swe").availability() is None
    assert TesseractAdapter(lang="xx_nope").availability() is not None
