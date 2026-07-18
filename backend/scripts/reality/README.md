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
  `app.answer._render_excerpts`), two independent verification methods
  (rect-vs-quote token check, ink-darkness check on returned rects), and
  `assert_zero_connections` — a self-enforcing hard-fail (non-zero exit) for
  scripts whose embedder and LLM are both fully scripted and therefore expect
  EXACTLY zero connections, not just zero external ones.
- `scanned_ingestion.py` — end-to-end proof of scanned-document ingestion on
  every real scan: OCR through the production dispatch, FIXED citation
  payloads derived from the OCR'd text itself run through the full
  retrieve→generate→verify pipeline (`FakeLLM`, no live model), independent
  rect/ink checks, and a corruption probe proving the all-or-nothing
  multi-span invariant on real OCR text.
- `fragment_facts.py` — end-to-end proof of the multi-span citation contract
  on three real fragment-fact classes from the born-digital contract
  (org-number, party name, appendix cell-value): each located by a
  deterministic regex/proximity heuristic (no fuzzy matching), confirmed
  retrievable for an already-committed generic board question, then run
  through the full retrieve→generate→verify→resolve pipeline (`FakeLLM`, no
  live model) with a corruption probe (all-or-nothing) and a cross-chunk
  probe (`provenance_mismatch`) per case.
- `annual_reports.py` — citation-verification + highlight validation on real
  Swedish BRF annual-report FINANCIAL TABLES (räntekostnader, soliditet,
  kreditinstitut/fastighetslån, yttre underhåll, årsavgift, plus an
  unanswerable control), each document in its own temp tenant. Beyond the
  structural verified/rejected counts, an independent geometric check
  (`row_landing_verdict`) confirms a citation's highlight sits on the SAME
  table row as the label term the question asked about, not merely the
  right page. Unlike the scripts above, this one asks with the AMBIENT
  provider (no `BRF_LLM`/`BRF_EMBEDDER` default set here) — the caller
  controls whether a real self-hosted model is used — and a nonzero
  network-connection total is expected (the LLM endpoint); only an
  EXTERNAL connection hard-fails.

Usage (from `backend/`):

    uv run python -m scripts.reality.digital_reality [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.verify_highlights --run RUN_JSON
    uv run python -m scripts.reality.ocr_reality [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.scanned_ingestion [--folder DIR] [--out DIR] [--limit N]
    uv run python -m scripts.reality.fragment_facts [--folder DIR] [--out DIR]
    uv run python -m scripts.reality.annual_reports [--folder DIR] [--docs DOC...] [--out DIR] [--limit-questions N]
