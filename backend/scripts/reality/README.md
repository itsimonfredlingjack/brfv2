# Reality-check diagnostics (2026-07-16)

Measurement rigs behind `docs/evidence/reality-report.md`. They read REAL BRF
documents from a local, gitignored folder (default `DONT_PUSH_brf_stuff/`) and
write only to gitignored/temp locations. Nothing derived from a real document
may be committed — metrics JSON only, and the committed evidence is redacted.

Every run is offline: embeddings load from cache (`HF_HUB_OFFLINE=1`), the LLM
is the local self-hosted endpoint, and `scripts.eval.install_network_audit`
hard-fails the process on any non-loopback connection.

- `digital_reality.py` — full pipeline (ingest → ask → cite → highlight) on the
  first born-digital PDF in the corpus, real board-style questions, per-citation
  highlight renders, network audit. Highlights are then verified computationally
  by `verify_highlights.py` (rect-covered words vs the cited quote, both through
  `app.normalize`).
- `ocr_reality.py` — OCR feasibility over every scanned PDF (word boxes,
  confidence, ink-coverage of boxes, dual-DPI self-consistency through
  `find_spans`) plus real-layout calibration and end-to-end highlight fidelity
  (OCR boxes vs embedded-truth boxes) on the born-digital PDF.

Usage (from `backend/`):

    uv run python -m scripts.reality.digital_reality [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.verify_highlights --run RUN_JSON
    uv run python -m scripts.reality.ocr_reality [--folder DIR] [--out DIR]
