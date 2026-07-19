"""Deterministic retrieval-recovery measurement for enriched chunk representation.

For every (document, financial question), does the true answer-bearing table
row get retrieved into topK — and at what rank — under baseline vs enriched vs
enriched+rerank? NO model of any kind: the answer-bearing row is located by the
AUTHORITATIVE word-index locator (refusal_buckets.label_row_occurrences +
chunk_contains_occurrence), reused, never a crude label+value string heuristic
(which false-positives on prose digits — see refusal-diagnosis.md).

Arms are selected by the caller's environment, not flags: run once with
BRF_ENRICH=0 (baseline) and once with BRF_ENRICH=1 (enriched); pass --rerank to
add the cross-encoder stage. This is a zero-LLM context — common.assert_zero_
connections enforces it (BRF_EMBEDDER=hashed, no ask()).

Data discipline: real chunk text/filenames only to the gitignored --out JSON;
stdout is metrics only (ranks, counts, page numbers).

Usage (from backend/):
    BRF_ENRICH=0 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/baseline.json
    BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/enriched.json
    BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/enrichment/enriched_rerank.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("BRF_LLM", "fake")  # never a live model here

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.rerank import rerank_chunks  # noqa: E402
from scripts.reality import common  # noqa: E402
from scripts.reality.annual_reports import (  # noqa: E402
    DEFAULT_DOCS,
    DEFAULT_FOLDER,
    QUESTIONS,
    doc_slug,
)
from scripts.reality.refusal_buckets import (  # noqa: E402
    chunk_contains_occurrence,
    label_row_occurrences,
)

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "out" / "reality" / "enrichment" / "recovery.json"
WIDE_TOP_K = 60  # rank across (almost) all chunks so a miss still reports its rank


def _answer_bearing_occurrences(pages, labels):
    occ = []
    for label in labels:
        occ.extend(o for o in label_row_occurrences(pages, label) if o["answer_bearing"])
    return occ


def true_row_rank(store, doc_id, question, labels, *, rerank: bool = False) -> int | None:
    """1-based rank of the first retrieved chunk that CONTAINS an answer-bearing
    label row. None if the document has no answer-bearing occurrence for these
    labels (question not gradeable on this doc)."""
    s = store.settings
    index, chunks, pages_by_doc, _documents = store.snapshot()
    pages = pages_by_doc[doc_id]
    occ = _answer_bearing_occurrences(pages, labels)
    if not occ:
        return None
    hits = index.search(question, weight=s.searchWeighting / 100.0,
                        candidates=max(s.candidateCount, WIDE_TOP_K),
                        top_k=WIDE_TOP_K, min_confidence=0.0)
    if rerank:
        hits = rerank_chunks(question, hits, WIDE_TOP_K)
    for i, h in enumerate(hits):
        c = chunks[h.chunk_id]
        if any(chunk_contains_occurrence(c, o) for o in occ):
            return i + 1
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--docs", nargs="+", default=list(DEFAULT_DOCS))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--top-k", type=int, default=6, help="the production window; a rank <= this is a recovery")
    ap.add_argument("--rerank", action="store_true")
    args = ap.parse_args()

    from app.enrich import enrichment_enabled

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna: {sorted(allowed)}", flush=True)
    print(f"enrichment_enabled={enrichment_enabled()} rerank={args.rerank} top_k={args.top_k}", flush=True)

    answerable = [(qid, q, labels) for qid, q, labels in QUESTIONS if labels is not None]
    rows = []
    for rel_doc in args.docs:
        slug = doc_slug(rel_doc)
        with common.temp_store() as store:
            meta = common.ingest(store, args.folder / rel_doc)
            for qid, question, labels in answerable:
                rank = true_row_rank(store, meta.id, question, labels, rerank=args.rerank)
                gradeable = rank is not None
                recovered = gradeable and rank <= args.top_k
                rows.append({"doc": slug, "qid": qid, "rank": rank,
                             "gradeable": gradeable, "in_topk": recovered})
                print(f"  {slug}/{qid}: rank={rank} in_top{args.top_k}={recovered}", flush=True)

    gradeable = [r for r in rows if r["gradeable"]]
    in_topk = [r for r in gradeable if r["in_topk"]]
    summary = {
        "enrichment_enabled": enrichment_enabled(),
        "rerank": args.rerank,
        "top_k": args.top_k,
        "gradeable_cases": len(gradeable),
        "in_topk": len(in_topk),
        "missed": len(gradeable) - len(in_topk),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2), "utf-8")
    print(f"\nSUMMARY {json.dumps(summary, ensure_ascii=False)}", flush=True)
    print(f"DONE → {args.out}", flush=True)
    common.assert_zero_connections(audit_log)


if __name__ == "__main__":
    main()
