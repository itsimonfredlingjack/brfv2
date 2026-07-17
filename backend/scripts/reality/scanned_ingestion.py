"""Scanned-ingestion end-to-end proof on the REAL scanned corpus (Task 4).

Ingests each real scanned PDF through the REAL `Store.add_document` path
(tesseract OCR at 250dpi/swe, conf-gated, chunked, indexed —
`app/store.py:129-149`), derives FIXED citation payloads from the OCR'd text
itself, and runs the FULL pipeline (retrieve -> generate -> verify ->
resolve) with a scripted `FakeLLM` so no live model is ever called. Two
independent checks re-derive whether each returned highlight is honest:

  (a) rect-covered OCR words match the cited span token-for-token through
      `app.normalize` — `verify_highlights.py`'s method, applied to the
      stored OCR `PageData` instead of embedded PDF text;
  (b) an ink check that the returned rects sit on dark pixels
      (`ocr_reality.ink_metrics`'s darkness formula, applied to the
      citation's own rects).

A final probe corrupts one character of a verified multi-span citation and
asserts the WHOLE citation is rejected and the answer refuses
(`grounding_failed`) — the all-or-nothing invariant, exercised on real OCR
text.

Offline discipline: `BRF_EMBEDDER=hashed`, `BRF_LLM=fake`, no live model is
ever called, and `scripts.eval.install_network_audit` hard-fails the process
on any non-loopback connection — the summary records the connection count
(expected: 0 external).

Usage (from backend/):
    uv run python -m scripts.reality.scanned_ingestion [--folder DIR] [--out DIR]
        [--limit N] [--max-chunks N]

`--limit` caps the number of scanned PDFs processed — for fast iteration
only; the evidence run must cover the full corpus (no --limit).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("BRF_LLM", "fake")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.reality import common  # noqa: E402

DEFAULT_MAX_CHUNKS = 10
MAX_CORRUPTION_SAMPLES_PER_DOC = 3


def _derive_payload(text: str, want_multi: bool):
    """Try the requested payload type first, fall back to the other so a
    short-but-not-too-short chunk still yields a payload; `(type, payload)`
    or `(None, None)` if the chunk can't hold either shape."""
    if want_multi:
        multi = common.multi_span_payload(text)
        if multi is not None:
            return "multi", multi
        single = common.single_span_payload(text)
        return ("single", single) if single is not None else (None, None)
    single = common.single_span_payload(text)
    if single is not None:
        return "single", single
    multi = common.multi_span_payload(text)
    return ("multi", multi) if multi is not None else (None, None)


def _scripted_response(alias: str, spans: list[str]) -> dict:
    citation = {"chunk_id": alias, "quotes": spans} if len(spans) > 1 else {"chunk_id": alias, "quote": spans[0]}
    return {"answer": "Se citerat utdrag.", "citations": [citation], "insufficient_data": False}


def _process_document(pdf: Path, slug: str, *, max_chunks: int) -> dict:
    from app.answer import ask
    from app.llm import FakeLLM

    doc_report: dict = {"slug": slug}
    with common.temp_store() as store:
        try:
            meta = common.ingest(store, pdf)
        except Exception as exc:  # the failure IS a finding — keep going
            doc_report["ingest_error"] = repr(exc)
            return doc_report

        doc_report.update(pages=meta.pages, words_kept=meta.words, chunks=meta.chunks, source=meta.source)
        blanks = common.blank_pages(store, meta.id)
        doc_report["blank_pages"] = blanks
        doc_report["blank_page_count"] = len(blanks)
        doc_report["conf_gate"] = common.conf_gate_stats(pdf)

        chunks = common.sorted_doc_chunks(store, meta.id)
        sampled = common.sample_chunks(chunks, n=max_chunks)

        payload_rows: list[dict] = []
        for j, chunk in enumerate(sampled):
            payload_type, payload = _derive_payload(chunk.text, want_multi=(j % 2 == 1))
            if payload is None:
                payload_rows.append({"chunk_id": chunk.id, "type": "none", "skip_reason": "chunk_too_short"})
                continue

            spans = list(payload) if payload_type == "multi" else [payload]
            question = " ".join(spans)
            alias, hits = common.alias_for_chunk(store, question, chunk.id)
            row: dict = {"chunk_id": chunk.id, "type": payload_type, "n_spans": len(spans), "spans": spans}
            if alias is None:
                row["retrieval_miss"] = True
                row["top_hit_chunk_ids"] = [h.chunk_id for h in hits[:3]]
                payload_rows.append(row)
                continue

            fake = FakeLLM([_scripted_response(alias, spans)])
            resp = ask(store, question, provider=fake)

            verified = (not resp.refusal) and len(resp.citations) == 1
            row["verified"] = verified
            if not verified:
                row["refusal_reason"] = resp.refusal_reason
                row["rejected_reasons"] = [r.reason for r in resp.rejected_citations]
                payload_rows.append(row)
                continue

            cit = resp.citations[0]
            row["approximate"] = cit.approximate
            row["rects_nonempty"] = bool(cit.rects)
            row["page"] = cit.page
            row["alias"] = alias
            page_words = store.pages[meta.id][cit.page - 1].words
            row["independent_verdict"] = common.independent_rect_verdict(page_words, cit.rects, spans)
            row["ink"] = common.rects_on_ink(pdf, cit.page, cit.rects)
            payload_rows.append(row)

        doc_report["payloads"] = payload_rows

        # Step 5: corrupt one span of verified multi-span payloads; the
        # question is left UNCHANGED (original spans) so retrieval/alias
        # match the already-proven run — only the cited quotes are
        # corrupted, isolating the verification-stage assertion.
        corruption_rows = []
        multi_verified = [r for r in payload_rows if r.get("type") == "multi" and r.get("verified")]
        for r in multi_verified[:MAX_CORRUPTION_SAMPLES_PER_DOC]:
            original_spans = r["spans"]
            corrupted = list(original_spans)
            corrupted[-1] = common.corrupt_span(corrupted[-1])
            question = " ".join(original_spans)
            fake = FakeLLM([_scripted_response(r["alias"], corrupted)])
            resp = ask(store, question, provider=fake)
            corruption_rows.append(
                {
                    "chunk_id": r["chunk_id"],
                    "refused": resp.refusal,
                    "refusal_reason": resp.refusal_reason,
                    "citations_shown": len(resp.citations),
                }
            )
        doc_report["corruption_probe"] = corruption_rows

    return doc_report


def _summarize(docs: dict, audit_log: list) -> dict:
    all_payloads = [r for d in docs.values() for r in d.get("payloads", [])]
    considered = [r for r in all_payloads if r.get("type") != "none" and not r.get("retrieval_miss")]
    verified = [r for r in considered if r.get("verified")]
    ink_rows = [r["ink"] for r in verified if r.get("ink") and r["ink"].get("total")]
    ink_total = sum(x["total"] for x in ink_rows)
    ink_on = sum(x["on_ink"] for x in ink_rows)
    independent_ok = sum(1 for r in verified if r.get("independent_verdict") in ("exact", "superset(edge-spill)"))
    corruption_rows = [c for d in docs.values() for c in d.get("corruption_probe", [])]
    external = [e for e in audit_log if not e["allowed"]]
    return {
        "documents": len(docs),
        "ingest_failures": sum(1 for d in docs.values() if "ingest_error" in d),
        "blank_page_total": sum(d.get("blank_page_count", 0) for d in docs.values()),
        "payloads_attempted": len(all_payloads),
        "payloads_skipped_too_short": sum(1 for r in all_payloads if r.get("skip_reason") == "chunk_too_short"),
        "retrieval_misses": sum(1 for r in all_payloads if r.get("retrieval_miss")),
        "payloads_considered": len(considered),
        "payloads_verified": len(verified),
        "payload_verification_rate": round(len(verified) / len(considered), 4) if considered else None,
        "independent_check_ok": independent_ok,
        "independent_check_rate": round(independent_ok / len(verified), 4) if verified else None,
        "ink_boxes_checked": ink_total,
        "ink_on_ink": ink_on,
        "rects_on_ink_rate": round(ink_on / ink_total, 4) if ink_total else None,
        "approximate_all_true": all(r.get("approximate") is True for r in verified) if verified else None,
        "corruption_probes": len(corruption_rows),
        "corruption_all_refused_grounding_failed": (
            all(
                c["refused"] and c["refusal_reason"] == "grounding_failed" and c["citations_shown"] == 0
                for c in corruption_rows
            )
            if corruption_rows
            else None
        ),
        "network_audit": {
            "total_connections": len(audit_log),
            "distinct_endpoints": sorted({f"{e['host']}:{e['port']}" for e in audit_log}),
            "external_connections": external,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=common.DEFAULT_FOLDER)
    ap.add_argument("--out", type=Path, default=common.DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=None, help="cap number of scanned PDFs (iteration only)")
    ap.add_argument("--max-chunks", type=int, default=DEFAULT_MAX_CHUNKS)
    args = ap.parse_args()

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    scans = [pdf for pdf in sorted(args.folder.glob("*.pdf")) if common.classify(pdf)[0] == "scan"]
    if args.limit:
        scans = scans[: args.limit]

    docs: dict[str, dict] = {}
    for i, pdf in enumerate(scans):
        slug = f"scan-{chr(65 + i)}"
        print(f"== {slug} ==", flush=True)
        docs[slug] = _process_document(pdf, slug, max_chunks=args.max_chunks)
        d = docs[slug]
        if "ingest_error" in d:
            print(f"{slug}: INGEST FAILED {d['ingest_error']}", flush=True)
        else:
            n_payloads = len(d.get("payloads", []))
            n_verified = sum(1 for r in d["payloads"] if r.get("verified"))
            print(
                f"{slug}: pages={d['pages']} chunks={d['chunks']} blanks={d['blank_page_count']} "
                f"payloads={n_payloads} verified={n_verified}",
                flush=True,
            )

    summary = _summarize(docs, audit_log)
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "scanned_ingestion.json"
    out_json.write_text(json.dumps({"docs": docs, "summary": summary}, ensure_ascii=False, indent=2), "utf-8")
    print(f"DONE → {out_json}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
