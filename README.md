# BRF Dokument-AI — grounded Q&A vertical slice

Swedish housing-co-op boards ask questions about their PDFs and get answers where
**every claim cites a verbatim passage, every citation is verified against the source
text, and the passage is highlighted at the exact position in the rendered PDF**.
Unanswerable questions are refused — with an explanation — instead of guessed at.

- **MVP status and canonical frontend:** [docs/MVP-STATUS.md](docs/MVP-STATUS.md)
- **Spec:** [SPEC.md](SPEC.md) · **Demo script:** [DEMO.md](DEMO.md) ·
  **Plan:** [docs/superpowers/plans/2026-07-16-vertical-slice.md](docs/superpowers/plans/2026-07-16-vertical-slice.md)
- **Evidence (real run):** [docs/evidence/](docs/evidence/)

## Quick start

```bash
make backend      # FastAPI on :8787 (uv manages Python 3.12 + deps)
make frontend     # Vite/React on http://localhost:5173/brfv2/
make demo-reset   # seed the fictional Brf Gjutformen 12 corpus + golden set
```

LLM provider: Anthropic SDK when `ANTHROPIC_API_KEY` is set, otherwise the locally
authenticated `claude` CLI. Tests never touch the network.

## Architecture (backend/)

```
PDF ─► extract.py (PyMuPDF words+boxes) ─► chunker.py (word-range provenance)
    ─► indexer.py (BM25 ⊕ model2vec embeddings, Swedish compound-aware expansion)
    ─► answer.py (retrieval gate → LLM (strict JSON) → LLM gate → grounding gate)
    ─► citations.py (quote verification + per-line box resolution, SPEC §2)
    ─► React UI (pdf.js viewer with highlight overlays)
```

## Quality

```bash
make test         # 110 offline tests incl. every SPEC §2 failure mode
make eval         # full eval w/ real LLM against the golden set (gated)
make eval-sweep   # proof the settings knobs change real behavior
```

Latest full eval (46 answerable + 10 unanswerable Swedish questions):
recall@6 **1.000** · citation verification **1.000** · highlight correctness **≥ 0.97** ·
false-answer rate **0.000**. See `backend/eval/` and `docs/evidence/`.

## OCR spike rig (scanned PDFs)

Most real BRF documents are scans. `backend/scripts/ocr_spike.py` measures OCR
candidates (word-box overlays, coordinate drift vs digital ground truth, quote-match
rate through the same normalization pipeline) — the go/no-go decision is deliberately
left for when real scans and Simon are in the room. See SPEC §5.
