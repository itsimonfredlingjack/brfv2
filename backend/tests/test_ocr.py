"""Unit tests for the OCR ingestion module (backend/app/ocr.py).

parse_tesseract_tsv is a PURE function (no tesseract binary needed): these
tests feed it fixed TSV fixture strings shaped exactly like real tesseract
`tsv` output (see backend/scripts/ocr_spike.py:65 for the subprocess
invocation this parses the output of).

Real-tesseract-dependent tests (ocr_pdf, tesseract_available end to end) live
in tests/test_ocr_ingestion.py behind the `ocr` marker + skipif, matching
tests/test_ocr_spike.py's pattern.
"""

from __future__ import annotations

import pytest

from app.ocr import OCR_MIN_CONF, parse_tesseract_tsv

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def test_min_conf_default_matches_measured_gate():
    assert OCR_MIN_CONF == 60.0


def test_conf_gate_drops_low_confidence_rows():
    tsv = "\n".join(
        [
            HEADER,
            "5\t1\t1\t1\t1\t1\t100\t50\t80\t20\t85.0\tBra",
            "5\t1\t1\t1\t1\t2\t190\t50\t80\t20\t42.0\tSkräp",
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert [w.text for w in words] == ["Bra"]


def test_conf_gate_is_inclusive_at_the_threshold():
    tsv = "\n".join(
        [
            HEADER,
            f"5\t1\t1\t1\t1\t1\t100\t50\t80\t20\t{OCR_MIN_CONF}\tGräns",
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert [w.text for w in words] == ["Gräns"]


def test_blank_page_yields_no_words():
    # Real tesseract output for a blank/drawing-only page: page- and
    # block-level aggregate rows (level 1/2) but no level-5 word rows.
    tsv = "\n".join(
        [
            HEADER,
            "1\t1\t0\t0\t0\t0\t0\t0\t1000\t1400\t-1\t",
            "2\t1\t1\t0\t0\t0\t0\t0\t1000\t1400\t-1\t",
        ]
    )
    assert parse_tesseract_tsv(tsv, dpi=250) == []


def test_empty_tsv_yields_no_words():
    assert parse_tesseract_tsv("", dpi=250) == []


def test_px_to_pt_scaling_at_250_dpi():
    tsv = "\n".join([HEADER, "5\t1\t1\t1\t1\t1\t100\t50\t80\t20\t95.0\tOrd"])
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert len(words) == 1
    w = words[0]
    scale = 72.0 / 250
    assert w.x0 == pytest.approx(100 * scale)
    assert w.y0 == pytest.approx(50 * scale)
    assert w.x1 == pytest.approx((100 + 80) * scale)
    assert w.y1 == pytest.approx((50 + 20) * scale)


def test_block_num_maps_directly_to_word_block():
    tsv = "\n".join(
        [
            HEADER,
            "5\t1\t3\t1\t1\t1\t100\t50\t80\t20\t95.0\tOrd",
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert words[0].block == 3


def test_block_line_grouping_puts_same_visual_line_words_together_and_separates_paragraphs():
    # Two paragraphs in the same block. tesseract's line_num RESETS at the
    # start of each paragraph, so paragraph 2's line 1 has the same raw
    # line_num as paragraph 1's line 1 even though they are different
    # visual lines. (block, line) must disambiguate them.
    tsv = "\n".join(
        [
            HEADER,
            "5\t1\t1\t1\t1\t1\t100\t50\t80\t20\t95.0\tFörsta",  # block1 par1 line1
            "5\t1\t1\t1\t1\t2\t190\t50\t80\t20\t95.0\trad",  # block1 par1 line1
            "5\t1\t1\t1\t2\t1\t100\t80\t80\t20\t95.0\tAndra",  # block1 par1 line2
            "5\t1\t1\t2\t1\t1\t100\t150\t80\t20\t95.0\tNy",  # block1 par2 line1 (resets!)
            "5\t1\t1\t2\t1\t2\t190\t150\t80\t20\t95.0\tparagraf",  # block1 par2 line1
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert len(words) == 5

    forsta, rad, andra, ny, paragraf = words
    # Same visual line -> same (block, line) key.
    assert (forsta.block, forsta.line) == (rad.block, rad.line)
    assert (ny.block, ny.line) == (paragraf.block, paragraf.line)
    # Three distinct visual lines total, despite only two distinct raw
    # tesseract line_num values (1 and 2) across the two paragraphs.
    keys = {(w.block, w.line) for w in words}
    assert len(keys) == 3
    # Paragraph 2's line 1 must NOT collide with paragraph 1's line 1.
    assert (ny.block, ny.line) != (forsta.block, forsta.line)
    # Paragraph 1's line 2 must also stay distinct from paragraph 2's line 1.
    assert (andra.block, andra.line) != (ny.block, ny.line)


def test_non_word_level_rows_ignored():
    tsv = "\n".join(
        [
            HEADER,
            "1\t1\t0\t0\t0\t0\t0\t0\t1000\t1400\t-1\t",
            "2\t1\t1\t0\t0\t0\t50\t50\t500\t100\t-1\t",
            "3\t1\t1\t1\t0\t0\t50\t50\t500\t50\t-1\t",
            "4\t1\t1\t1\t1\t0\t50\t50\t500\t20\t-1\t",
            "5\t1\t1\t1\t1\t1\t50\t50\t80\t20\t92.0\tOrd",
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert len(words) == 1
    assert words[0].text == "Ord"


def test_blank_text_word_rows_dropped_even_at_level_5():
    tsv = "\n".join(
        [
            HEADER,
            "5\t1\t1\t1\t1\t1\t100\t50\t80\t20\t95.0\t",
            "5\t1\t1\t1\t1\t2\t190\t50\t80\t20\t95.0\tOrd",
        ]
    )
    words = parse_tesseract_tsv(tsv, dpi=250)
    assert [w.text for w in words] == ["Ord"]
