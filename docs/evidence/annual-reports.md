# Evidence — annual-report table validation (2026-07-18)

First contact between the pipeline and real Swedish BRF annual reports (the corpus the
reality report flagged as missing). Question: does the citation-verification + highlight
chain hold inside financial tables (flerårsöversikt, balansräkning, resultaträkning, noter)?
**Redaction:** real documents; this report is metrics-only — no verbatim passages, amounts,
or org numbers. Raw artifacts live in gitignored `backend/out/reality/annual_reports/`.

## Corpus and method

4 born-digital reports from the public corpus (24 PDFs, stored outside the repo under
`~/brf-corpus-public/` — see guard/corpus-isolation), spanning three
property-manager template families: 2 HSB (`hsb-perrongen_2024`, `hsb-taltrasten_2025`),
1 Riksbyggen (`rb-lycksaligheten_2025`), 1 own-template (`brf-grantorp_2025`); 95 pages,
1 700–2 130 chars/page. Runner: `backend/scripts/reality/annual_reports.py` (committed,
content-free) — real ingestion path (`Store.add_document`), 6 questions per document
(5 financial + 1 unanswerable control) through the full `ask()` pipeline with the
self-hosted Gemma 4 12B (llama.cpp, `n_ctx_slot=8192` verified) via SSH tunnel;
`BRF_EMBEDDER=hashed`, `HF_HUB_OFFLINE=1`, socket-level network audit on every run.

A first run was DISCARDED: the embedder attempted a HuggingFace fetch (env not pinned);
the audit **blocked all 4 external connection attempts at the socket layer and failed the
run loudly** — the tripwire working as designed. The clean re-run (audit: **1 connection
total, `127.0.0.1:8000` only, 0 external**) reproduced the discarded run's outcomes
identically.

## Results (clean run)

| metric | value |
|---|---|
| questions asked | 24 (4 docs × 6) |
| answered | 7 |
| refused | 17 (13 substantive — all `insufficient_data`; 4 = the unanswerable controls, correct) |
| citations emitted | 10 — **10/10 verbatim-verified** |
| lands on correct label row (deterministic geometry check) | **10/10** |
| independent rect-tokens-vs-span-tokens check | **10/10 exact**, 0 violations |
| multi-span citations emitted | 0 (see refusal-diagnosis evidence) |
| rejected citations across all 24 questions | 0 |

**Chain verdict: HOLDS inside financial tables.** Every citation the model produced
verified verbatim and its highlight landed on the correct table row — including
balance-sheet pages where the same liability label legitimately appears twice
(long-term/short-term): the pipeline emitted two distinct citations, one per row, each
correctly scoped. Adversarial verification (independent geometric re-derivation for 3/10,
pixel inspection of all 10 highlight renders, plus a per-case reconciliation pass — see
`refusal-diagnosis.md`) found **zero disagreements** with the runner's verdicts.
Honest bounds: n=10 citations; the rejection path (`quote_not_found`→refusal) got no
natural exercise in this run (no model fabrication occurred) — it is exercised by the
corruption probes in the scanned-ingestion and fragment-fact evidence instead.

Answered-question texture: single-span citations with up to 6 rects — PyMuPDF extracts
these standard financial tables **row-major**, so a label+value row is one contiguous text
run that renders as several boxes. The contracts-corpus fragment problem largely does not
manifest in standard annual-report tables (one measured exception: a transposed table —
see `refusal-diagnosis.md`).

The 13 substantive refusals are diagnosed exhaustively in
`docs/evidence/refusal-diagnosis.md`. Headline: all 13 are retrieval-bounded at the
default topK=6; none is a citation-contract or extraction failure.

## Reproduce

`cd backend && BRF_EMBEDDER=hashed HF_HUB_OFFLINE=1 BRF_LLM=selfhosted \
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=<serving-model-id> \
uv run python -m scripts.reality.annual_reports`
(requires the public corpus at `~/brf-corpus-public/brf-annual-reports-2026-07-18/sample-ars`
— the script's default — and the self-hosted model endpoint; the script hard-fails on any
external network connection).
