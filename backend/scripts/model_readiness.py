"""One-command model-readiness harness (Task 6).

Ingests the real corpus via the REAL `Store.add_document` path
(`scripts/reality/common.py`): the born-digital PDF(s) into ONE temp-tenant
`Store` — the Q&A tenant the question set below is asked against, the exact
configuration Task 5's `fragment_facts.py` measured retrievability against —
and, separately, the scanned PDF(s) too when a working tesseract install is
detected, each into its OWN throwaway temp tenant as an ingestion-only health
check (never mixed into the Q&A tenant, so it cannot dilute retrieval for the
committed questions below). The question set then runs through whichever LLM
provider the ambient environment picks — exactly `scripts/eval.py`'s own
default (`BRF_LLM`/`BRF_LLM_BASE_URL`/`BRF_LLM_MODEL`, `pick_provider()`).

Question set (reused, not duplicated, from already-committed scripts):
  - three fragment-fact board questions (org-number/party/cell-value classes
    and their qids — Task 5's empirically-measured mapping,
    `scripts/reality/fragment_facts.py:CASES`),
  - two prose-answerable controls,
  - one unanswerable control,
all drawn from `scripts/reality/digital_reality.py:QUESTIONS` (the committed
generic Swedish board questions).

Per question: answered/refused, verified citations emitted, single- vs
multi-span (`len(c.quotes) > 1`), rejected citations with reasons, and
`approximate` flags. The verification verdict here is purely STRUCTURAL —
anything in `resp.citations` has already passed `citations.resolve_citation`
(all-or-nothing); this script does not re-verify, only counts and reports.

READY iff every fragment-fact question is answered with >=1 verified
citation AND the unanswerable control refuses (`compute_verdict`, unit-tested
with fixed inputs independent of any real corpus or LLM).

Self-test proving the harness itself, no live model ever called:
  --selftest           scripts a FakeLLM with the CORRECT multi-span payload
                        derived from the real chunks (fragment_facts.py's
                        locate_* heuristics + common's alias resolution) ->
                        must print READY, exit 0.
  --selftest-negative  scripts a FakeLLM with a FABRICATED payload (one span
                        corrupted by a single-character edit, Task 5's
                        `common.corrupt_span` corruption-probe technique) for
                        every fragment-fact question -> must print NOT READY,
                        exit 1.
Both self-tests install the network audit unconditionally and hard-fail via
`common.assert_zero_connections` if the log is non-empty at all (FakeLLM +
BRF_EMBEDDER=hashed has no legitimate reason to open any socket).

A LIVE-provider run (the future gate this harness exists to support) is
deliberately never invoked by this repo's own tests or CI this phase — only
the two self-tests are exercised as evidence (global constraint: zero
live-model dependencies).

Usage (from backend/):
    uv run python -m scripts.model_readiness [--folder DIR] [--out DIR] [--network-audit]
    uv run python -m scripts.model_readiness --selftest
    uv run python -m scripts.model_readiness --selftest-negative
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.reality import common  # noqa: E402
from scripts.ocr_spike import TesseractAdapter  # noqa: E402


def _import_reused():
    """Reuse the committed question text and fragment-fact locators from
    Task 4/5 scripts without letting THEIR OWN module-level env defaults
    leak into this script's ambient-env provider selection.

    `digital_reality.py` forces `BRF_LLM=selfhosted` (its own generation
    default) and `fragment_facts.py` forces `BRF_LLM=fake`/`BRF_EMBEDDER=
    hashed` (its own offline default) via `os.environ.setdefault` at import
    time. This script's contract is different: "default provider = ambient
    env, exactly like scripts/eval.py" — so any env value THIS import would
    have set-by-default (i.e. was previously unset) is reverted immediately
    after the import completes.
    """
    keys = ("BRF_LLM", "BRF_LLM_BASE_URL", "BRF_LLM_MODEL", "HF_HUB_OFFLINE", "BRF_EMBEDDER")
    saved = {k: os.environ.get(k) for k in keys}
    from scripts.reality import fragment_facts as ff

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return ff


_ff = _import_reused()

# This script's OWN deliberate default (independent of the reused-import
# revert above): deterministic, offline, no HF network dependency for the
# embedding side of retrieval. Orthogonal to the BRF_LLM* provider choice.
os.environ.setdefault("BRF_EMBEDDER", "hashed")

_Q: dict[str, str] = dict(_ff.QUESTIONS)
# (case name, qid) pairs — Task 5's measured mapping (fragment_facts.py:CASES).
FRAGMENT_CASES: list[tuple[str, str]] = [(name, qid) for name, qid, _fn in _ff.CASES]
_LOCATORS = {name: fn for name, _qid, fn in _ff.CASES}

PROSE_CONTROLS = ["q01", "q02"]
UNANSWERABLE_CONTROL = "q11"

QUESTION_SET: list[dict] = (
    [{"qid": qid, "question": _Q[qid], "class_": "fragment", "case": case} for case, qid in FRAGMENT_CASES]
    + [{"qid": qid, "question": _Q[qid], "class_": "prose", "case": None} for qid in PROSE_CONTROLS]
    + [{"qid": UNANSWERABLE_CONTROL, "question": _Q[UNANSWERABLE_CONTROL], "class_": "unanswerable", "case": None}]
)


# ---------- ingestion (born-digital always, scans conditionally) ----------
#
# The question set (fragment-fact classes + controls) is asked against a
# temp tenant holding ONLY the born-digital document(s) — the exact
# configuration Task 5's fragment_facts.py measured retrievability against
# (q09/q08/q03). Scanned documents are ingested too (when tesseract is
# available) as a SEPARATE ingestion-only health check, each in its own
# throwaway temp tenant (scanned_ingestion.py's one-store-per-document
# pattern) — proving the full real corpus loads without failure, without
# diluting retrieval for the born-digital questions with unrelated chunks.


def _ingest_digital(store, folder: Path) -> list[str]:
    """Ingest the born-digital PDF(s) into `store` (the Q&A temp tenant).
    Returns their document ids."""
    pdfs = sorted(folder.glob("*.pdf"))
    digital_paths = [p for p in pdfs if common.classify(p)[0] == "digital"]
    if not digital_paths:
        raise SystemExit(f"Ingen digital (born-digital) PDF hittades i {folder}")
    meta = [common.ingest(store, p) for p in digital_paths]
    return [m.id for m in meta]


def _ingest_scans_smoke(folder: Path) -> dict:
    """Ingestion-only health check on the scanned corpus: each scan gets its
    own throwaway temp tenant (never mixed into the Q&A store above). A soft
    skip (not a hard failure) when tesseract is unavailable."""
    pdfs = sorted(folder.glob("*.pdf"))
    scan_paths = [p for p in pdfs if common.classify(p)[0] == "scan"]
    ocr_skip_reason = TesseractAdapter().availability()
    if ocr_skip_reason is not None:
        return {
            "docs_ingested": 0,
            "docs_skipped": len(scan_paths),
            "skip_reason": ocr_skip_reason,
            "pages": 0,
            "words": 0,
            "chunks": 0,
        }
    pages = words = chunks = 0
    for p in scan_paths:
        with common.temp_store() as scan_store:
            meta = common.ingest(scan_store, p)
            pages += meta.pages
            words += meta.words
            chunks += meta.chunks
    return {
        "docs_ingested": len(scan_paths),
        "docs_skipped": 0,
        "skip_reason": None,
        "pages": pages,
        "words": words,
        "chunks": chunks,
    }


# ---------- the question loop (shared by live runs and both self-tests) ----------


def _ask_all(store, provider) -> list[dict]:
    from app.answer import ask

    rows: list[dict] = []
    for q in QUESTION_SET:
        resp = ask(store, q["question"], provider=provider)
        citations_detail = [
            {"n_spans": len(c.quotes), "multi_span": len(c.quotes) > 1, "approximate": c.approximate}
            for c in resp.citations
        ]
        rows.append(
            {
                "qid": q["qid"],
                "class_": q["class_"],
                "case": q["case"],
                "refused": resp.refusal,
                "refusal_reason": resp.refusal_reason,
                # Structural only: everything counted here already passed
                # citations.resolve_citation (all-or-nothing) inside ask().
                "n_citations": len(resp.citations),
                "citations_detail": citations_detail,
                "n_rejected": len(resp.rejected_citations),
                "rejected_reasons": [r.reason for r in resp.rejected_citations],
            }
        )
    return rows


# ---------- readiness verdict (pure function — unit-tested with fixed inputs) ----------


def compute_verdict(rows: list[dict]) -> tuple[bool, list[str]]:
    """READY iff every fragment-fact question is answered with >=1 verified
    citation AND the unanswerable control refuses. Prose controls are
    reported (per-question table) but do not gate the verdict — context
    only, per the brief.

    Requires >=1 row of EACH gating class to even be eligible for READY:
    empty input, or input missing the fragment class or the unanswerable
    class entirely, is NOT READY with an explicit reason — a vacuous pass
    ("no evidence of failure" != "evidence of readiness") is not a valid
    verdict for a go/no-go gate."""
    reasons: list[str] = []
    fragment_rows = [r for r in rows if r["class_"] == "fragment"]
    unanswerable_rows = [r for r in rows if r["class_"] == "unanswerable"]

    if not fragment_rows:
        reasons.append(
            "inga fragment-fact-frågor i indata — kan inte fastställa READY "
            "(kräver minst en fragment-fact-fråga)"
        )
    if not unanswerable_rows:
        reasons.append(
            "ingen obesvarbar kontrollfråga i indata — kan inte fastställa READY "
            "(kräver minst en obesvarbar kontrollfråga)"
        )

    for r in fragment_rows:
        if r["refused"] or r["n_citations"] < 1:
            reasons.append(
                f"{r['qid']} ({r['case']}): fragment-fact-fråga inte besvarad med en "
                f"verifierad källhänvisning (refused={r['refused']}, citations={r['n_citations']})"
            )
    for r in unanswerable_rows:
        if not r["refused"]:
            reasons.append(f"{r['qid']}: den obesvarbara kontrollfrågan avböjde inte")

    return (not reasons), reasons


def print_table(rows: list[dict]) -> None:
    print("\n| qid | class | status | citations | multi-span | rejected | approximate |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        label = r["qid"] + (f" ({r['case']})" if r["case"] else "")
        status = f"refused:{r['refusal_reason']}" if r["refused"] else "answered"
        multi = sum(1 for c in r["citations_detail"] if c["multi_span"])
        approx = sum(1 for c in r["citations_detail"] if c["approximate"])
        rejected = ",".join(r["rejected_reasons"]) if r["rejected_reasons"] else "-"
        print(f"| {label} | {r['class_']} | {status} | {r['n_citations']} | {multi} | {rejected} | {approx} |")


# ---------- self-test payload scripting (no live model) ----------


def _scripted_response(alias: str, spans: list[str]) -> dict:
    citation = {"chunk_id": alias, "quotes": spans} if len(spans) > 1 else {"chunk_id": alias, "quote": spans[0]}
    return {"answer": "Se citerat utdrag.", "citations": [citation], "insufficient_data": False}


_UNANSWERABLE_RESPONSE = {
    "answer": "Dokumenten innehåller inte tillräcklig information för att besvara frågan.",
    "citations": [],
    "insufficient_data": True,
}


def _prose_payload(store, question: str) -> tuple[str | None, str | None]:
    """(alias, payload) for the store's own top retrieval hit on `question` —
    a genuine verbatim substring of THAT chunk's own text, so it verifies
    against the real chunk it is scripted for."""
    s = store.settings
    index, chunks, _pages, _documents = store.snapshot()
    hits = index.search(
        question, weight=s.searchWeighting / 100.0, candidates=s.candidateCount, top_k=s.topK, min_confidence=0.0
    )
    if not hits:
        return None, None
    chunk = chunks[hits[0].chunk_id]
    payload = common.single_span_payload(chunk.text)
    if payload is None:
        return None, None
    alias, _hits = common.alias_for_chunk(store, question, chunk.id)
    return alias, payload


def _selftest_responses(store, digital_doc_ids: list[str], *, negative: bool) -> list[dict]:
    """Scripted FakeLLM responses, one per `QUESTION_SET` entry, in order —
    must match the order `_ask_all` calls `ask()` exactly (FakeLLM pops its
    queue in call order)."""
    doc_chunks: list = []
    for doc_id in digital_doc_ids:
        doc_chunks.extend(common.sorted_doc_chunks(store, doc_id))

    responses: list[dict] = []
    for q in QUESTION_SET:
        if q["class_"] == "fragment":
            locate_fn = _LOCATORS[q["case"]]
            candidates = locate_fn(doc_chunks)
            chosen = None
            for chunk, span1, span2 in candidates:
                alias, _hits = common.alias_for_chunk(store, q["question"], chunk.id)
                if alias is not None:
                    chosen = (alias, span1, span2)
                    break
            if chosen is None:
                raise SystemExit(
                    f"self-test: hittade ingen lokaliserbar+hämtningsbar förekomst för "
                    f"{q['qid']} ({q['case']}) — korpusen eller heuristiken har ändrats sedan Task 5"
                )
            alias, span1, span2 = chosen
            spans = [span1, span2]
            if negative:
                # Task 5's corruption-probe technique (common.corrupt_span):
                # flip one alphabetic character in the second span so it is
                # byte-for-byte non-verbatim. Chosen over a literal
                # quote-stitch fabrication because whether two real
                # fragments sit textually adjacent (and would then
                # coincidentally still verify as one contiguous quote)
                # varies per real occurrence — a corrupted span always fails
                # verbatim verification regardless of that detail.
                spans = [span1, common.corrupt_span(span2)]
            responses.append(_scripted_response(alias, spans))
        elif q["class_"] == "prose":
            alias, payload = _prose_payload(store, q["question"])
            if alias is None:
                raise SystemExit(f"self-test: kunde inte härleda en payload för {q['qid']}")
            responses.append(_scripted_response(alias, [payload]))
        else:
            responses.append(_UNANSWERABLE_RESPONSE)
    return responses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=common.DEFAULT_FOLDER)
    ap.add_argument("--out", type=Path, default=common.DEFAULT_OUT)
    ap.add_argument(
        "--network-audit",
        action="store_true",
        help="hard-fail on any TCP connect outside loopback/BRF_LLM_BASE_URL; report the connection count",
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="score the harness with a scripted CORRECT FakeLLM (no live model) -> must print READY, exit 0",
    )
    ap.add_argument(
        "--selftest-negative",
        action="store_true",
        help="score the harness with a scripted FABRICATED FakeLLM (no live model) -> must print NOT READY, exit 1",
    )
    args = ap.parse_args()

    if args.selftest and args.selftest_negative:
        raise SystemExit("--selftest och --selftest-negative är ömsesidigt uteslutande")

    audit_log = None
    if args.selftest or args.selftest_negative or args.network_audit:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        audit_log, allowed = common.install_network_audit()
        print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    with common.temp_store() as store:
        digital_doc_ids = _ingest_digital(store, args.folder)
        scan_report = _ingest_scans_smoke(args.folder)
        ingest_report = {
            "digital_docs": len(digital_doc_ids),
            "scan_docs_ingested": scan_report["docs_ingested"],
            "scan_docs_skipped": scan_report["docs_skipped"],
            "ocr_skip_reason": scan_report["skip_reason"],
            "scan_pages": scan_report["pages"],
            "scan_words": scan_report["words"],
            "scan_chunks": scan_report["chunks"],
        }
        print(
            f"Ingested (Q&A tenant): digital_docs={ingest_report['digital_docs']}. "
            f"Ingested (scan smoke-check): docs={ingest_report['scan_docs_ingested']} "
            f"skipped={ingest_report['scan_docs_skipped']} pages={ingest_report['scan_pages']} "
            f"chunks={ingest_report['scan_chunks']}",
            flush=True,
        )

        if args.selftest or args.selftest_negative:
            # Deterministic retrieval for the scripted FakeLLM queue: the
            # pre-LLM low-relevance refusal gate must never fire here, or
            # the response list desyncs from the question order.
            store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
            responses = _selftest_responses(store, digital_doc_ids, negative=args.selftest_negative)
            from app.llm import FakeLLM

            provider = FakeLLM(responses)
            provider_name = "fake-selftest-negative" if args.selftest_negative else "fake-selftest-correct"
        else:
            from app.llm import pick_provider

            provider = pick_provider()
            provider_name = provider.name

        rows = _ask_all(store, provider)

    ready, reasons = compute_verdict(rows)

    external: list[dict] = []
    if audit_log is not None:
        external = [e for e in audit_log if not e["allowed"]]
        if external:
            ready = False
            reasons.append(f"nätverksrevision: {len(external)} otillåten(a) anslutning(ar)")

    print_table(rows)
    print(f"\nVERDICT: {'READY' if ready else 'NOT READY'} (provider={provider_name})")
    for reason in reasons:
        print(f"  - {reason}")

    result = {
        "provider": provider_name,
        "ingest": ingest_report,
        "questions": rows,
        "ready": ready,
        "reasons": reasons,
    }
    if audit_log is not None:
        result["network_audit"] = {
            "total_connections": len(audit_log),
            "distinct_endpoints": sorted({f"{e['host']}:{e['port']}" for e in audit_log}),
            "external_connections": external,
        }
        print(f"Nätverksrevision: {len(audit_log)} anslutningar, {len(external)} externa", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "model_readiness.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(f"DONE → {out_json}", flush=True)

    # Hardening (Task 5's pattern): a self-test whose embedder AND LLM are
    # both fully scripted has no legitimate reason to open ANY socket.
    if args.selftest or args.selftest_negative:
        common.assert_zero_connections(audit_log)

    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
