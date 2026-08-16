"""Annual-report table validation on the REAL Swedish BRF corpus.

Validates the citation-verification + highlight chain specifically against
financial TABLES inside real annual reports (årsredovisningar) — the layout
where a fact lives as a bare number next to a row label rather than inside a
prose sentence. Beyond the existing structural check ("did a citation come
back and pass `citations.resolve_citation`?"), this script adds a
deterministic, independent geometric check: does the citation's highlight
actually sit on the SAME table row as the label term the question asked
about (`row_landing_verdict`), rather than merely landing somewhere on the
right page?

Each document is ingested into its OWN throwaway temp tenant (`common.
temp_store`) so retrieval never crosses documents. Questions are asked via
`app.answer.ask(store, question)` with NO explicit provider — the AMBIENT
one (`app.llm.pick_provider`), exactly like `scripts/eval.py`'s own default.
This script therefore sets NO `BRF_LLM`/`BRF_EMBEDDER` env defaults itself
(unlike `digital_reality.py`/`fragment_facts.py`/`scanned_ingestion.py`,
which each force their own offline default) — the caller controls the
provider; this script never calls a live model on its own initiative, and
its own tests script `FakeLLM` explicitly.

Network semantics differ from the no-LLM scripts in this folder: a nonzero
TOTAL connection count is EXPECTED (the real LLM endpoint) — this script
does NOT use `common.assert_zero_connections`. Only an EXTERNAL connection
(anything outside loopback / `BRF_LLM_BASE_URL`) is disqualifying, and is a
hard failure (`enforce_no_external_connections`, non-zero exit).

Usage (from backend/):
    uv run python -m scripts.reality.annual_reports [--folder DIR] [--docs DOC...]
        [--out DIR] [--limit-questions N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz  # noqa: E402  (PyMuPDF)

from app.normalize import norm_token  # noqa: E402
from app.schemas import PageData  # noqa: E402
from scripts.reality import common  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent.parent
# Corpus lives OUTSIDE the repo (guard/corpus-isolation): a path boundary, not
# a gitignore convention — see docs/evidence/annual-reports.md.
DEFAULT_FOLDER = Path.home() / "brf-corpus-public" / "brf-annual-reports-2026-07-18" / "sample-ars"
DEFAULT_OUT = BACKEND / "out" / "reality" / "annual_reports"

DEFAULT_DOCS: list[str] = [
    "hsb-perrongen/2024_hsb.pdf",
    "hsb-taltrasten/2025_hsb.pdf",
    "rb-lycksaligheten/2025.pdf",
    "brf-grantorp/2025.pdf",
]

# (qid, question, labels) — labels is None for the unanswerable control (no
# row-landing check applies to a question that must refuse). Labels are
# generic Swedish accounting vocabulary, not document content.
QUESTIONS: list[tuple[str, str, list[str] | None]] = [
    ("q_interest", "Hur stora var föreningens räntekostnader under året?", ["räntekostnader"]),
    ("q_solidity", "Hur stor är föreningens soliditet i procent?", ["soliditet"]),
    ("q_loans", "Hur stora är föreningens skulder till kreditinstitut?", ["kreditinstitut", "fastighetslån"]),
    ("q_fund", "Hur mycket finns avsatt i fonden för yttre underhåll?", ["yttre underhåll", "underhållsfond"]),
    ("q_fee", "Vilken årsavgift per kvadratmeter har föreningen?", ["årsavgift"]),
    ("q_control", "Vilket datum hölls föreningens kräftskiva enligt årsredovisningen?", None),
]


# ---------- row-landing check (the heart of this validation) ----------
#
# A citation's highlight rects come back in PDF points, top-left origin
# (app/schemas.py:1-2). A label "occurrence" is a run of the label's own
# words matched, in reading-order (left-to-right by x0), across ADJACENT
# words sharing one (block, line) id on one page — i.e. one visual line/
# table row. The row's own y-band (min y0 .. max y1 across the matched
# words) is expanded by half its own line height above and below (a
# deliberately small tolerance — enough to absorb baseline/ascender
# differences between the label cell and a numeric-column cell on the same
# visual row, not so wide it reaches an adjacent row).


def _label_tokens(label: str) -> list[str]:
    return [t for t in (norm_token(w) for w in label.split()) if t]


def find_label_line_occurrences(pages: list[PageData], label: str) -> list[dict]:
    """Every occurrence of `label` (one or more space-separated words) found
    across adjacent words on ONE visual line of `pages`. Case/diacritic
    folding via `app.normalize.norm_token` (NFKC + casefold). Returns one
    dict per occurrence: `{"page": int, "y0": float, "y1": float}` — the
    matched words' own min-y0..max-y1 span. The row-band tolerance is
    applied separately, at compare time, by `label_row_band`."""
    tokens = _label_tokens(label)
    if not tokens:
        return []
    n = len(tokens)
    out: list[dict] = []
    for page in pages:
        lines: dict[tuple[int, int], list] = {}
        for w in page.words:
            lines.setdefault((w.block, w.line), []).append(w)
        for words in lines.values():
            ordered = sorted(words, key=lambda w: w.x0)
            norm = [norm_token(w.text) for w in ordered]
            for start in range(len(norm) - n + 1):
                if all(norm[start + k] == tokens[k] for k in range(n)):
                    span = ordered[start : start + n]
                    out.append(
                        {
                            "page": page.number,
                            "y0": min(w.y0 for w in span),
                            "y1": max(w.y1 for w in span),
                        }
                    )
    return out


def label_row_band(occurrence: dict) -> tuple[float, float]:
    """The occurrence's own y-band, expanded by half its own line height
    above and below (the "half-a-line tolerance")."""
    height = occurrence["y1"] - occurrence["y0"]
    pad = height * 0.5
    return occurrence["y0"] - pad, occurrence["y1"] + pad


def _rect_overlaps_band(rect: list[float], band: tuple[float, float]) -> bool:
    y0, y1 = rect[1], rect[3]
    b0, b1 = band
    return y0 <= b1 and y1 >= b0


def row_landing_verdict(
    pages: list[PageData], labels: list[str], cited_page: int, rects: list[list[float]]
) -> dict:
    """Whether a citation's rects land on the row of ANY of `labels`'
    occurrences. `label_pages` lists every page (across ALL labels) that
    carries >=1 occurrence — reported even when landing is False, so a
    reader can tell "cited the wrong page" from "cited the right page but
    the wrong row"."""
    occurrences: list[dict] = []
    for label in labels:
        occurrences.extend(find_label_line_occurrences(pages, label))
    label_pages = sorted({o["page"] for o in occurrences})
    same_page = [o for o in occurrences if o["page"] == cited_page]
    lands = any(_rect_overlaps_band(r, label_row_band(o)) for r in rects for o in same_page)
    return {"lands_on_label_row": lands, "label_pages": label_pages, "cited_page": cited_page}


# ---------- output-filename slugging (gitignored --out dir only) ----------

_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def doc_slug(rel_doc: str) -> str:
    """A filesystem/metric-safe slug for a folder-relative doc path (e.g.
    "hsb-perrongen/2024_hsb.pdf" -> "hsb-perrongen_2024_hsb"). Used only for
    output filenames under the gitignored --out dir — never committed."""
    p = Path(rel_doc)
    parent = p.parent.name if str(p.parent) not in ("", ".") else ""
    raw = f"{parent}_{p.stem}" if parent else p.stem
    return _SLUG_UNSAFE.sub("_", raw)


# ---------- network semantics (a live-run script — nonzero total expected) ----------


def enforce_no_external_connections(audit_log: list[dict]) -> None:
    """Hard-fail (non-zero exit, loud message) iff ANY EXTERNAL connection
    was recorded. Unlike `common.assert_zero_connections` (for the no-LLM
    scripts in this folder, which expect EXACTLY zero connections), a
    nonzero TOTAL is expected here — the real LLM endpoint is a legitimate,
    allowed connection. Only a connection outside loopback/BRF_LLM_BASE_URL
    is disqualifying."""
    external = [e for e in audit_log if not e.get("allowed", False)]
    if external:
        hosts = sorted({f"{e['host']}:{e['port']}" for e in external})
        raise SystemExit(
            f"NÄTVERKSREVISION MISSLYCKADES: {len(external)} extern(a) anslutning(ar) "
            f"upptäcktes under valideringskörningen. Värdar: {hosts}"
        )


# ---------- highlight rendering (digital_reality.py's pattern) ----------


def _render_highlight(src: "fitz.Document", citation, slug: str, qid: str, ci: int, hl_dir: Path) -> None:
    if not citation.rects:
        return
    page = src[citation.page - 1]
    rects = [fitz.Rect(*r) for r in citation.rects]
    shape = page.new_shape()
    for r in rects:
        shape.draw_rect(r)
    shape.finish(color=(1, 0, 0), width=1.2)
    shape.commit()
    union = rects[0]
    for r in rects[1:]:
        union |= r
    clip = fitz.Rect(0, max(0, union.y0 - 90), page.rect.x1, min(page.rect.y1, union.y1 + 90))
    page.get_pixmap(dpi=150, clip=clip).save(str(hl_dir / f"{slug}_{qid}_c{ci}.png"))


# ---------- the question loop ----------


def _process_question(
    store, meta, src, qid: str, question: str, labels: list[str] | None, slug: str, hl_dir: Path, *,
    corpus_runtime=None,
) -> dict:
    from app.answer import ask

    row: dict = {"qid": qid, "labels": labels}
    t0 = time.perf_counter()
    try:
        resp = ask(store, question, corpus_runtime=corpus_runtime)
    except Exception as exc:  # the failure IS a finding — keep going
        row["error"] = repr(exc)
        row["elapsed_s"] = round(time.perf_counter() - t0, 3)
        return row
    row["elapsed_s"] = round(time.perf_counter() - t0, 3)
    row["refused"] = resp.refusal
    row["refusal_reason"] = resp.refusal_reason
    row["n_citations"] = len(resp.citations)
    row["rejected"] = [{"reason": r.reason} for r in resp.rejected_citations]
    if labels is None:
        row["control_refused"] = resp.refusal

    pages = store.pages[meta.id]
    citations_detail: list[dict] = []
    for ci, c in enumerate(resp.citations):
        page_words = pages[c.page - 1].words
        detail: dict = {
            "page": c.page,
            "n_spans": len(c.quotes),
            "multi_span": len(c.quotes) > 1,
            "n_rects": len(c.rects),
            "approximate": c.approximate,
            "independent_verdict": common.independent_rect_verdict(page_words, c.rects, c.quotes),
        }
        if labels is not None:
            detail.update(row_landing_verdict(pages, labels, c.page, c.rects))
        citations_detail.append(detail)
        _render_highlight(src, c, slug, qid, ci, hl_dir)
    row["citations"] = citations_detail

    return row


def _process_document(
    pdf_path: Path, rel_doc: str, slug: str, questions: list, hl_dir: Path, *, rerank: bool = False
) -> dict:
    doc_report: dict = {"path": rel_doc}
    if not pdf_path.exists():
        doc_report["ingest_error"] = f"file not found: {rel_doc}"
        return doc_report

    with common.temp_store() as store:
        try:
            meta = common.ingest(store, pdf_path)
        except (AssertionError, SystemExit):
            raise
        except Exception as exc:  # the failure IS a finding — keep going
            doc_report["ingest_error"] = repr(exc)
            return doc_report

        if rerank:
            store.update_settings(store.settings.model_copy(update={"rerankEnabled": True}))

        raw_threshold = os.environ.get("BRF_FULL_CORPUS_THRESHOLD")
        if raw_threshold is not None and raw_threshold != "":
            store.update_settings(
                store.settings.model_copy(update={"fullCorpusTokenThreshold": int(raw_threshold)})
            )

        from app.full_corpus import live_corpus_runtime

        corpus_runtime = live_corpus_runtime()

        doc_report.update(pages=meta.pages, words=meta.words, chunks=meta.chunks, source=meta.source)
        if meta.source != "digital":
            raise SystemExit(
                f"{rel_doc}: DocumentMeta.source={meta.source!r}, väntat 'digital' "
                "(det här skriptet validerar den born-digital-pipelinen; en oväntat "
                "skannad korpusfil är ett fynd, inte något att tyst hoppa över)"
            )

        src = fitz.open(str(pdf_path))
        try:
            question_rows = []
            for qid, question, labels in questions:
                row = _process_question(
                    store, meta, src, qid, question, labels, slug, hl_dir, corpus_runtime=corpus_runtime
                )
                question_rows.append(row)
                extra = f" citations={row['n_citations']}" if "n_citations" in row else f" error={row.get('error')}"
                print(f"  {qid}: refused={row.get('refused')}{extra}", flush=True)
            doc_report["questions"] = question_rows
        finally:
            src.close()

    return doc_report


# ---------- summary ----------


def _summarize(documents: dict, audit_log: list) -> dict:
    all_rows = [(slug, r) for slug, d in documents.items() for r in d.get("questions", [])]
    errored = [(s, r) for s, r in all_rows if r.get("error")]
    refused = [(s, r) for s, r in all_rows if not r.get("error") and r.get("refused")]
    answered = [(s, r) for s, r in all_rows if not r.get("error") and not r.get("refused")]
    control_rows = [(s, r) for s, r in all_rows if r.get("labels") is None and not r.get("error")]

    all_citations = [c for _, r in answered for c in r.get("citations", [])]
    row_landing_considered = [c for c in all_citations if "lands_on_label_row" in c]
    lands_true = [c for c in row_landing_considered if c["lands_on_label_row"]]
    verdicts = Counter(c["independent_verdict"] for c in all_citations)
    independent_exact = verdicts.get("exact", 0)
    independent_spill = verdicts.get("superset(edge-spill)", 0)
    independent_violations = sum(v for k, v in verdicts.items() if k not in ("exact", "superset(edge-spill)"))

    external = [e for e in audit_log if not e["allowed"]]
    return {
        "documents": len(documents),
        "ingest_failures": sum(1 for d in documents.values() if "ingest_error" in d),
        "questions_asked": len(all_rows),
        "questions_answered": len(answered),
        "questions_refused": len(refused),
        "questions_errored": len(errored),
        "citations_total": len(all_citations),
        # Structural only: everything counted here already passed
        # citations.resolve_citation (all-or-nothing) inside ask().
        "citations_verified": len(all_citations),
        "multi_span_emitted": sum(1 for c in all_citations if c["multi_span"]),
        "lands_on_label_row_considered": len(row_landing_considered),
        "lands_on_label_row_true": len(lands_true),
        "lands_on_label_row_rate": (
            round(len(lands_true) / len(row_landing_considered), 4) if row_landing_considered else None
        ),
        "independent_exact": independent_exact,
        "independent_superset_edge_spill": independent_spill,
        "independent_violations": independent_violations,
        "control_refused": {s: r["refused"] for s, r in control_rows},
        "control_refused_all": (all(r["refused"] for _, r in control_rows) if control_rows else None),
        "network_audit": {
            "total_connections": len(audit_log),
            "distinct_endpoints": sorted({f"{e['host']}:{e['port']}" for e in audit_log}),
            "external_connections": external,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--docs", nargs="+", default=list(DEFAULT_DOCS))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit-questions", type=int, default=None, help="cap the question set (cheap iteration only)")
    ap.add_argument(
        "--rerank",
        action="store_true",
        help="enable the cross-encoder rerank stage (Settings.rerankEnabled=True; rerankCandidates default 40)",
    )
    args = ap.parse_args()

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    questions = QUESTIONS[: args.limit_questions] if args.limit_questions else QUESTIONS

    hl_dir = args.out / "highlights"
    hl_dir.mkdir(parents=True, exist_ok=True)

    documents: dict[str, dict] = {}
    for rel_doc in args.docs:
        slug = doc_slug(rel_doc)
        print(f"== {slug} ({rel_doc}) ==", flush=True)
        documents[slug] = _process_document(
            args.folder / rel_doc, rel_doc, slug, questions, hl_dir, rerank=args.rerank
        )
        d = documents[slug]
        if "ingest_error" in d:
            print(f"{slug}: INGEST FAILED {d['ingest_error']}", flush=True)
        else:
            print(f"{slug}: pages={d['pages']} words={d['words']} chunks={d['chunks']}", flush=True)

    summary = _summarize(documents, audit_log)
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "annual_reports.json"
    out_json.write_text(
        json.dumps(
            {"rerank_enabled": args.rerank, "documents": documents, "summary": summary},
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print(f"DONE → {out_json}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    # Live-run network semantics (differs from the no-LLM scripts in this
    # folder): a nonzero TOTAL is expected (the real LLM endpoint) — only an
    # EXTERNAL connection hard-fails.
    print(
        f"Nätverksrevision: {len(audit_log)} anslutningar totalt, "
        f"{len(summary['network_audit']['external_connections'])} externa.",
        flush=True,
    )
    enforce_no_external_connections(audit_log)


if __name__ == "__main__":
    main()
