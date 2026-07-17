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
- `common.py` — shared helpers for the scripts below: temp-tenant ingestion
  through the REAL `Store.add_document` path, deterministic payload-window
  derivation from chunk text, retrieval-order K-alias resolution (mirrors
  `app.answer._render_excerpts`), and two independent verification methods
  (rect-vs-quote token check, ink-darkness check on returned rects).
- `scanned_ingestion.py` — end-to-end proof of scanned-document ingestion on
  every real scan: OCR through the production dispatch, FIXED citation
  payloads derived from the OCR'd text itself run through the full
  retrieve→generate→verify pipeline (`FakeLLM`, no live model), independent
  rect/ink checks, and a corruption probe proving the all-or-nothing
  multi-span invariant on real OCR text.

Usage (from `backend/`):

    uv run python -m scripts.reality.digital_reality [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.verify_highlights --run RUN_JSON
    uv run python -m scripts.reality.ocr_reality [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.scanned_ingestion [--folder DIR] [--out DIR] [--limit N]
