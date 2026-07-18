"""Refusal-bucket diagnosis on the REAL annual-report validation run.

`scripts.reality.annual_reports` proved the citation-verification chain is
honest (all-or-nothing, row-landing checked) on the cases that DID answer.
This script explains the cases that DIDN'T: every non-control (doc, question)
pair the validation run (`out/reality/annual_reports/annual_reports.json`)
recorded as refused. For each, it re-derives — purely from retrieval geometry
and word-index bookkeeping, NO model of any kind — which of three buckets the
refusal belongs to:

  1. retrieval_miss     — no retrieved chunk contains both the label row's
                           label words AND one of its value tokens.
  2. extraction_garble   — a retrieved chunk DOES contain both, but the
                           chunk's own text string (the model's literal view)
                           scatters them far apart / interleaves foreign-row
                           tokens between them / splits a value token.
  3. citation_emission   — retrieved AND readable (label+value sit close
                           together, uninterleaved, in a retrieved chunk's
                           text) yet the model still refused. This is the
                           bucket a smarter/better-prompted model could fix
                           without any retrieval or extraction change.

Bucket 1/2 vs. 3 is decided by WORD-INDEX containment and CHUNK-STRING token
distance — never by re-running the LLM. The classification is a read of
retrieval + PDF geometry only; `common.assert_zero_connections` (this is a
zero-LLM context, unlike `annual_reports.py`'s live-run mode) enforces this at
the end of every invocation, including `--multispan-probe`, which uses a
scripted `FakeLLM` (see `scripts/reality/fragment_facts.py` for the pattern
this probe follows).

Question set, label terms, and the label-row locator all come from
`scripts.reality.annual_reports` (imported, not duplicated) — this script
only adds word-INDEX provenance on top of that locator's y-coordinate
geometry, which the containment/garble analysis needs and the row-landing
check does not.

Data discipline: real chunk text, quotes, and document filenames are written
ONLY to the gitignored `--out` JSON. Anything printed to stdout (the bucket-
distribution table) is metrics only — counts, distances, page numbers, chunk
ids — never quoted document text.

Usage (from backend/):
    uv run python -m scripts.reality.refusal_buckets [--run-json PATH]
        [--folder DIR] [--out DIR] [--multispan-probe] [--max-probe-cases N]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("BRF_LLM", "fake")  # only the --multispan-probe path calls ask(); never a live model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz  # noqa: E402  (PyMuPDF)

from app.normalize import norm_token  # noqa: E402
from app.schemas import Chunk, DocumentMeta, PageData, Word  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.reality import common  # noqa: E402
from scripts.reality.annual_reports import (  # noqa: E402
    QUESTIONS,
    _label_tokens,
    _render_highlight,
    doc_slug,
    label_row_band,
    row_landing_verdict,
)

BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_FOLDER = (
    BACKEND.parent / "docs-external" / "swarm-research" / "brf-annual-reports-2026-07-18" / "sample-ars"
)
DEFAULT_RUN_JSON = BACKEND / "out" / "reality" / "annual_reports" / "annual_reports.json"
DEFAULT_OUT = BACKEND / "out" / "reality" / "refusal_buckets"

_Q: dict[str, tuple[str, list[str] | None]] = {qid: (question, labels) for qid, question, labels in QUESTIONS}

# ---------- diagnostic classification thresholds (Bucket 2 only) ----------
#
# These constants CLASSIFY an already-retrieved, already-contained case as
# "garbled" vs. "clean" for reporting purposes. They gate NOTHING in the
# production pipeline — `citations.resolve_citation` has its own, wholly
# separate, all-or-nothing verbatim check. Chosen as "clearly not adjacent"
# bounds for a table row's label -> value token gap in the chunk's own text.
GARBLE_DISTANCE_TOKENS = 12
GARBLE_INTERLEAVE_FOREIGN = 6

_DIGIT_RE = re.compile(r"\d")


def is_value_token(word_text: str) -> bool:
    """Generic numeric-bearing detection: any Unicode digit anywhere in the
    word's own text. Deliberately format-agnostic (handles "45", "45,5",
    "18%", a lone "000" half of a space-thousands-separated amount, etc.)
    rather than pinning one number shape."""
    return bool(_DIGIT_RE.search(word_text))


# ---------- label-row occurrences WITH word-index provenance ----------


def label_row_occurrences(pages: list[PageData], label: str) -> list[dict]:
    """Every occurrence of `label` on one visual line, like
    `annual_reports.find_label_line_occurrences`, but additionally resolving
    the word-INDEX provenance the containment/garble analysis needs:
    `label_indices` (into `page.words`), `row_indices` (every word on the
    label's own y-band, per `annual_reports.label_row_band` — across ALL
    blocks/lines on the page, not just the label's own (block, line), since
    a table's value column can legitimately live in a different block than
    its label column while still sharing the visual row), and `value_indices`
    (the row's numeric-bearing words). `answer_bearing` is True iff
    `value_indices` is non-empty (label appears WITH an adjacent value
    somewhere in the doc, not just incidentally in prose)."""
    tokens = _label_tokens(label)
    if not tokens:
        return []
    n = len(tokens)
    out: list[dict] = []
    for page in pages:
        lines: dict[tuple[int, int], list[tuple[int, Word]]] = {}
        for idx, w in enumerate(page.words):
            lines.setdefault((w.block, w.line), []).append((idx, w))
        for entries in lines.values():
            ordered = sorted(entries, key=lambda e: e[1].x0)
            norm = [norm_token(e[1].text) for e in ordered]
            for start in range(len(norm) - n + 1):
                if not all(norm[start + k] == tokens[k] for k in range(n)):
                    continue
                span = ordered[start : start + n]
                label_indices = [idx for idx, _w in span]
                y0 = min(w.y0 for _i, w in span)
                y1 = max(w.y1 for _i, w in span)
                band = label_row_band({"y0": y0, "y1": y1})
                row_indices = [
                    idx for idx, w in enumerate(page.words) if w.y0 <= band[1] and w.y1 >= band[0]
                ]
                value_indices = [idx for idx in row_indices if is_value_token(page.words[idx].text)]
                out.append(
                    {
                        "page": page.number,
                        "label_indices": label_indices,
                        "row_indices": row_indices,
                        "value_indices": value_indices,
                        "answer_bearing": len(value_indices) > 0,
                    }
                )
    return out


# ---------- Bucket 1: word-index containment ----------


def chunk_contains_occurrence(chunk: Chunk, occurrence: dict) -> bool:
    """Does this retrieved chunk (its page + word_start..word_end) contain
    BOTH every label word of `occurrence` AND at least one of its row's
    value tokens — by word-INDEX range containment, never by string search."""
    if chunk.page != occurrence["page"]:
        return False
    if not occurrence["label_indices"] or not occurrence["value_indices"]:
        return False
    label_contained = all(chunk.word_start <= i <= chunk.word_end for i in occurrence["label_indices"])
    value_contained = any(chunk.word_start <= i <= chunk.word_end for i in occurrence["value_indices"])
    return label_contained and value_contained


# ---------- Bucket 2: chunk-string garble metrics ----------


def _string_token_span(word_text: str) -> int:
    """How many whitespace-separated tokens ONE geometric word becomes once
    folded into the chunk's plain-text string (`chunk.text` is a single
    `" ".join(...)` over `page.words[word_start:word_end+1]` —
    `app/chunker.py`). Normally 1; >1 only if the word's own extracted text
    itself contains embedded whitespace (an extraction quirk, e.g. a
    thousands-separator space PyMuPDF didn't treat as a word boundary) — the
    generic, structural definition of "value-token splitting" used below."""
    n = len(word_text.split())
    return n if n > 0 else 1


def _token_start_positions(words: list[Word]) -> list[int]:
    """Cumulative token-start position, in the chunk's plain-text string, for
    each word in `words` (already sliced to one chunk's word range)."""
    positions: list[int] = []
    pos = 0
    for w in words:
        positions.append(pos)
        pos += _string_token_span(w.text)
    return positions


def garble_metrics(chunk: Chunk, page: PageData, occurrence: dict) -> dict:
    """Analyze the CHUNK STRING the model actually saw for the NEAREST
    row-value token to the label: its token distance in the string, how many
    tokens from OTHER visual rows (word-index provenance, i.e. NOT in this
    row's own `row_indices`) are interleaved between them, and whether the
    value word itself splits across string tokens. Caller already
    established (`chunk_contains_occurrence`) that >=1 candidate exists."""
    words_in_chunk = page.words[chunk.word_start : chunk.word_end + 1]
    positions = _token_start_positions(words_in_chunk)

    def pos_of(abs_idx: int) -> int:
        return positions[abs_idx - chunk.word_start]

    last_label_idx = sorted(occurrence["label_indices"])[-1]
    label_anchor = pos_of(last_label_idx) + _string_token_span(page.words[last_label_idx].text) - 1

    value_candidates = [i for i in occurrence["value_indices"] if chunk.word_start <= i <= chunk.word_end]
    row_index_set = set(occurrence["row_indices"])

    best: dict | None = None
    for i in value_candidates:
        vpos = pos_of(i)
        lo, hi = sorted((label_anchor, vpos))
        distance = max(0, hi - lo - 1)
        foreign = 0
        for j, w in enumerate(words_in_chunk):
            tok_pos = positions[j]
            if lo < tok_pos < hi and (chunk.word_start + j) not in row_index_set:
                foreign += 1
        candidate = {
            "value_word_index": i,
            "token_distance": distance,
            "interleave_foreign_count": foreign,
            "value_split": _string_token_span(page.words[i].text) > 1,
        }
        if best is None or candidate["token_distance"] < best["token_distance"]:
            best = candidate
    assert best is not None
    return best


def is_garbled(metrics: dict) -> bool:
    return (
        metrics["token_distance"] > GARBLE_DISTANCE_TOKENS
        or metrics["value_split"]
        or metrics["interleave_foreign_count"] > GARBLE_INTERLEAVE_FOREIGN
    )


# ---------- per-case bucketing ----------


def classify(pages: list[PageData], retrieved_chunks: list[Chunk], labels: list[str]) -> dict:
    """The pure decision tree — no `Store`, no retrieval call — so it is
    directly unit-testable against synthetic fixtures: given the label's
    occurrences (word-index resolved) and the chunks retrieval actually
    returned, decide Bucket 1 (retrieval_miss) / 2 (extraction_garble) / 3
    (citation_emission). `bucket_case` below is the thin retrieval-calling
    wrapper around this."""
    occurrences: list[dict] = []
    for label in labels:
        occurrences.extend(label_row_occurrences(pages, label))
    answer_bearing = [o for o in occurrences if o["answer_bearing"]]

    result: dict = {
        "retrieved_pages": sorted({c.page for c in retrieved_chunks}),
        "retrieved_chunk_ids": [c.id for c in retrieved_chunks],
        "label_pages": sorted({o["page"] for o in occurrences}),
        "answer_bearing_pages": sorted({o["page"] for o in answer_bearing}),
        "n_occurrences": len(occurrences),
        "n_answer_bearing_occurrences": len(answer_bearing),
    }

    if not answer_bearing:
        result["bucket"] = 1
        result["bucket_label"] = "retrieval_miss"
        result["note"] = "no answer-bearing label row found anywhere in the document"
        return result

    contained_pairs: list[tuple[dict, Chunk]] = [
        (occ, c) for occ in answer_bearing for c in retrieved_chunks if chunk_contains_occurrence(c, occ)
    ]
    if not contained_pairs:
        result["bucket"] = 1
        result["bucket_label"] = "retrieval_miss"
        return result

    garble_analysis = []
    for occ, c in contained_pairs:
        page = pages[c.page - 1]
        metrics = garble_metrics(c, page, occ)
        garbled = is_garbled(metrics)
        garble_analysis.append(
            {
                "chunk_id": c.id,
                "chunk_word_start": c.word_start,
                "chunk_word_end": c.word_end,
                "occurrence_page": occ["page"],
                "chunk_text": c.text,  # real content — OK, this file is gitignored only
                **metrics,
                "garbled": garbled,
            }
        )
    result["garble_analysis"] = garble_analysis

    if any(not g["garbled"] for g in garble_analysis):
        result["bucket"] = 3
        result["bucket_label"] = "citation_emission"
    else:
        result["bucket"] = 2
        result["bucket_label"] = "extraction_garble"
    return result


def bucket_case(store: Store, doc_id: str, question: str, labels: list[str]) -> dict:
    """Retrieve (mirroring `app/answer.py:ask()`'s call at ~:98 exactly) then
    hand off the retrieved chunks + pages to `classify` for the actual
    decision."""
    s = store.settings
    index, chunks, pages_by_doc, _documents = store.snapshot()
    hits = index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=s.candidateCount,
        top_k=s.topK,
        min_confidence=0.0,
    )
    retrieved_chunks = [chunks[h.chunk_id] for h in hits]
    pages = pages_by_doc[doc_id]
    return classify(pages, retrieved_chunks, labels)


# ---------- multi-span probe ----------


def _contiguous_value_run(page: PageData, occurrence: dict, seed_idx: int) -> tuple[int, int]:
    """Extend `seed_idx` (one numeric-bearing word) into the maximal
    contiguous (by page-word index) run of the row's OWN value tokens — the
    natural "value fragment" when a number is split across multiple Word
    boxes (e.g. a thousands-separator space)."""
    row_set = set(occurrence["row_indices"])
    value_set = set(occurrence["value_indices"])
    start = end = seed_idx
    while (start - 1) in row_set and (start - 1) in value_set:
        start -= 1
    while (end + 1) in row_set and (end + 1) in value_set:
        end += 1
    return start, end


def construct_multispan_fragments(
    page: PageData, chunk: Chunk, occurrence: dict, metrics: dict
) -> tuple[str, str] | None:
    """Hand-construct [label fragment, value fragment] — both verbatim
    word-sequences copied straight from `page.words` at the occurrence's own
    indices — for a scripted multi-span citation. Returns None if either
    fragment doesn't fit fully inside the retrieved chunk's own word range
    (the honest "construction impossible" case, not silently skipped)."""
    label_indices = sorted(occurrence["label_indices"])
    if not (chunk.word_start <= label_indices[0] and label_indices[-1] <= chunk.word_end):
        return None
    start, end = _contiguous_value_run(page, occurrence, metrics["value_word_index"])
    if not (chunk.word_start <= start and end <= chunk.word_end):
        return None
    label_frag = " ".join(page.words[i].text for i in label_indices)
    value_frag = " ".join(page.words[i].text for i in range(start, end + 1))
    return label_frag, value_frag


def _scripted_multispan(alias: str, label_frag: str, value_frag: str) -> dict:
    return {
        "answer": "Se citerade fragment.",
        "citations": [{"chunk_id": alias, "quotes": [label_frag, value_frag]}],
        "insufficient_data": False,
    }


def probe_case(
    store: Store,
    meta: DocumentMeta,
    src: "fitz.Document",
    slug: str,
    qid: str,
    question: str,
    labels: list[str],
    case_result: dict,
    hl_dir: Path,
) -> dict:
    from app.answer import ask
    from app.llm import FakeLLM

    pages = store.pages[meta.id]
    _index, chunks, _pages_by_doc, _documents = store.snapshot()

    # Prefer a CLEAN (occ, chunk) pair if this case has one (bucket-3 cases
    # always do, by construction); fall back to the least-garbled pair for a
    # bucket-2 fallback case, so the probe still has something concrete to
    # construct against.
    garble_analysis = case_result.get("garble_analysis", [])
    clean = [g for g in garble_analysis if not g["garbled"]]
    pool = clean or garble_analysis
    if not pool:
        return {"qid": qid, "status": "no_contained_pair", "bucket": case_result["bucket"]}
    chosen = min(pool, key=lambda g: g["token_distance"])
    chunk = chunks[chosen["chunk_id"]]
    occ = next(
        o
        for o in [o for label in labels for o in label_row_occurrences(pages, label)]
        if chunk_contains_occurrence(chunk, o)
    )
    page = pages[chunk.page - 1]

    row: dict = {
        "qid": qid,
        "bucket": case_result["bucket"],
        "chunk_id": chunk.id,
        "used_garbled_fallback": chosen in garble_analysis and chosen not in clean,
    }

    fragments = construct_multispan_fragments(page, chunk, occ, chosen)
    if fragments is None:
        row["status"] = "construction_impossible"
        row["reason"] = "value fragment run not fully contained in the retrieved chunk's word range"
        return row
    label_frag, value_frag = fragments

    alias, _hits = common.alias_for_chunk(store, question, chunk.id)
    if alias is None:
        row["status"] = "construction_impossible"
        row["reason"] = "chosen chunk not retrieved for this question under fresh retrieval"
        return row

    fake = FakeLLM([_scripted_multispan(alias, label_frag, value_frag)])
    resp = ask(store, question, provider=fake)
    resolved = (not resp.refusal) and len(resp.citations) == 1
    row["resolved"] = resolved
    if not resolved:
        row["status"] = "not_resolved"
        row["refusal_reason"] = resp.refusal_reason
        row["rejected_reasons"] = [r.reason for r in resp.rejected_citations]
        return row

    cit = resp.citations[0]
    row["n_rects"] = len(cit.rects)
    row["n_spans"] = len(cit.quotes)
    landing = row_landing_verdict(pages, labels, cit.page, cit.rects)
    row["lands_on_label_row"] = landing["lands_on_label_row"]
    page_words = pages[cit.page - 1].words
    row["independent_verdict"] = common.independent_rect_verdict(page_words, cit.rects, cit.quotes)
    row["status"] = "resolved"
    _render_highlight(src, cit, slug, f"{qid}_probe", 0, hl_dir)

    return row, (alias, label_frag, value_frag)  # type: ignore[return-value]


def run_corruption_control(
    store: Store, question: str, alias: str, label_frag: str, value_frag: str
) -> dict:
    from app.answer import ask
    from app.llm import FakeLLM

    corrupted_value = common.corrupt_span(value_frag)
    fake = FakeLLM([_scripted_multispan(alias, label_frag, corrupted_value)])
    resp = ask(store, question, provider=fake)
    return {
        "refused": resp.refusal,
        "refusal_reason": resp.refusal_reason,
        "citations_shown": len(resp.citations),
        "rejected_reasons": [r.reason for r in resp.rejected_citations],
        "rejected_whole_citation": resp.refusal and len(resp.citations) == 0,
    }


# ---------- I/O + reporting ----------


def load_refused_cases(run_json_path: Path) -> list[dict]:
    """Non-control refused (doc, question) rows from the validation run's own
    JSON: `labels is not None` (control has none) and `refused` true and no
    ingest/ask error. Derived from the file, never hardcoded."""
    data = json.loads(run_json_path.read_text("utf-8"))
    cases = []
    for _slug, doc in data["documents"].items():
        rel_doc = doc["path"]
        for row in doc.get("questions", []):
            if row.get("error"):
                continue
            if row.get("labels") is None:
                continue
            if not row.get("refused"):
                continue
            cases.append({"rel_doc": rel_doc, "qid": row["qid"]})
    return cases


def print_bucket_table(results: list[dict]) -> None:
    n1 = sum(1 for r in results if r["bucket"] == 1)
    n2 = sum(1 for r in results if r["bucket"] == 2)
    n3 = sum(1 for r in results if r["bucket"] == 3)
    print(f"\nBucket distribution (of {len(results)} non-control refused cases):")
    print(f"  1 retrieval_miss     : {n1}")
    print(f"  2 extraction_garble  : {n2}")
    print(f"  3 citation_emission  : {n3}")
    print("\nPer case:")
    for r in results:
        extra = ""
        if r["bucket"] in (2, 3) and r.get("garble_analysis"):
            winner = min(r["garble_analysis"], key=lambda g: g["token_distance"])
            extra = (
                f" nearest_distance={winner['token_distance']} "
                f"interleave={winner['interleave_foreign_count']} "
                f"value_split={winner['value_split']}"
            )
        print(
            f"  {r['doc']}/{r['qid']}: bucket={r['bucket']}({r['bucket_label']}) "
            f"retrieved_pages={r['retrieved_pages']} label_pages={r['label_pages']}"
            f"{extra}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-json", type=Path, default=DEFAULT_RUN_JSON)
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--multispan-probe", action="store_true")
    ap.add_argument("--max-probe-cases", type=int, default=5)
    args = ap.parse_args()

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    cases = load_refused_cases(args.run_json)
    print(f"Loaded {len(cases)} non-control refused (doc, question) pairs from {args.run_json}", flush=True)
    docs_needed = sorted({c["rel_doc"] for c in cases})

    results: list[dict] = []
    probe_results: list[dict] = []
    corruption_control: dict | None = None

    with contextlib.ExitStack() as stack:
        doc_ctx: dict[str, tuple[Store, DocumentMeta]] = {}
        for rel_doc in docs_needed:
            store = stack.enter_context(common.temp_store())
            meta = common.ingest(store, args.folder / rel_doc)
            if meta.source != "digital":
                raise SystemExit(f"{rel_doc}: DocumentMeta.source={meta.source!r}, expected 'digital'")
            doc_ctx[rel_doc] = (store, meta)
            print(f"Ingested {rel_doc}: pages={meta.pages} words={meta.words} chunks={meta.chunks}", flush=True)

        for case in cases:
            rel_doc, qid = case["rel_doc"], case["qid"]
            store, meta = doc_ctx[rel_doc]
            question, labels = _Q[qid]
            assert labels is not None
            bucketed = bucket_case(store, meta.id, question, labels)
            bucketed["doc"] = doc_slug(rel_doc)
            bucketed["rel_doc"] = rel_doc
            bucketed["qid"] = qid
            results.append(bucketed)

        print_bucket_table(results)

        if args.multispan_probe:
            bucket3 = [r for r in results if r["bucket"] == 3]
            selected = list(bucket3[: args.max_probe_cases])
            fallback_used = False
            if len(selected) < 3:
                fallback_used = True
                bucket2 = [r for r in results if r["bucket"] == 2]
                need = args.max_probe_cases - len(selected)
                selected += bucket2[:need]
                print(
                    f"\nFewer than 3 bucket-3 (citation_emission) cases exist "
                    f"({len(bucket3)}) — falling back to bucket-2 (extraction_garble) "
                    f"cases too for the multi-span probe (SAY SO, per spec).",
                    flush=True,
                )
            print(f"\nMulti-span probe: {len(selected)} case(s) selected (fallback_used={fallback_used})", flush=True)

            hl_dir = args.out / "highlights"
            hl_dir.mkdir(parents=True, exist_ok=True)
            src_cache: dict[str, "fitz.Document"] = {}
            first_resolved: tuple[str, str, str, str] | None = None  # (rel_doc, alias, label_frag, value_frag)

            for r in selected:
                rel_doc = r["rel_doc"]
                store, meta = doc_ctx[rel_doc]
                if rel_doc not in src_cache:
                    src_cache[rel_doc] = fitz.open(str(args.folder / rel_doc))
                src = src_cache[rel_doc]
                slug = r["doc"]
                qid = r["qid"]
                question, labels = _Q[qid]
                assert labels is not None
                out = probe_case(store, meta, src, slug, qid, question, labels, r, hl_dir)
                if isinstance(out, tuple):
                    probe_row, (alias, label_frag, value_frag) = out
                    probe_row["doc"] = slug
                    probe_results.append(probe_row)
                    if first_resolved is None and probe_row.get("status") == "resolved":
                        first_resolved = (rel_doc, alias, label_frag, value_frag)
                else:
                    out["doc"] = slug
                    probe_results.append(out)
                print(
                    f"  probe {slug}/{qid}: status={probe_results[-1].get('status')} "
                    f"resolved={probe_results[-1].get('resolved')} "
                    f"n_rects={probe_results[-1].get('n_rects')} "
                    f"lands_on_label_row={probe_results[-1].get('lands_on_label_row')}",
                    flush=True,
                )

            if first_resolved is not None:
                rel_doc, alias, label_frag, value_frag = first_resolved
                store, _meta = doc_ctx[rel_doc]
                question, _labels = _Q[next(r["qid"] for r in selected if r["doc"] == doc_slug(rel_doc))]
                corruption_control = run_corruption_control(store, question, alias, label_frag, value_frag)
                print(f"\nCorruption control: {corruption_control}", flush=True)
            else:
                print("\nCorruption control: SKIPPED — no probe case resolved.", flush=True)
                corruption_control = {"skipped": True, "reason": "no probe case resolved"}

            for doc in src_cache.values():
                doc.close()

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "refusal_buckets.json"
    payload = {
        "cases": results,
        "summary": {
            "total": len(results),
            "bucket_1_retrieval_miss": sum(1 for r in results if r["bucket"] == 1),
            "bucket_2_extraction_garble": sum(1 for r in results if r["bucket"] == 2),
            "bucket_3_citation_emission": sum(1 for r in results if r["bucket"] == 3),
        },
    }
    if args.multispan_probe:
        payload["multispan_probe"] = probe_results
        payload["corruption_control"] = corruption_control
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    print(f"\nDONE → {out_json}", flush=True)

    common.assert_zero_connections(audit_log)


if __name__ == "__main__":
    main()
