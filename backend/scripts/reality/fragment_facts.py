"""Fragment-fact end-to-end proof on the REAL born-digital contract (Task 5).

Extends Task 4's scanned-ingestion proof to the multi-span citation contract
itself: three real fragment-fact classes — an organisation number, a party
name, and an appendix table cell value — none of which lives in a
contiguous, quotable sentence. For each class this script:

  1. Locates a real occurrence with a DETERMINISTIC heuristic over the
     chunk's own text (regex/label-proximity — no fuzzy matching, no model
     help). If no occurrence is found, the case is reported `not_locatable`
     with the reason (SPEC honesty requirement) rather than faked.
  2. Confirms the owning chunk is actually retrievable (via
     `common.alias_for_chunk`) for a real, already-committed generic
     board-style question (`digital_reality.QUESTIONS`) — if every located
     occurrence is a genuine retrieval miss, that is reported too, distinct
     from `not_locatable`.
  3. Runs the FULL pipeline (retrieve -> generate -> verify -> resolve) via
     a scripted `FakeLLM` citing the two spans as `quotes` on the correct
     retrieved alias — no live model is ever called.
  4. Two probes per resolved case: corrupting one span (whole citation must
     reject, answer must refuse `grounding_failed`) and citing the SAME
     valid spans against a DIFFERENT retrieved chunk (must reject
     `provenance_mismatch`) — the all-or-nothing invariant and the
     wrong-occurrence guard, both on real fragment-fact text.

An independent check (`common.independent_rect_verdict`) re-derives, outside
`citations.resolve_citation`, whether the returned rects are honest.

Offline discipline: `BRF_EMBEDDER=hashed`, `BRF_LLM=fake` (an explicit
`FakeLLM` is passed to every `ask()` call), `scripts.eval.install_network_audit`
active for the whole run, and — this script's own hardening on top of Task 4's
review — `common.assert_zero_connections` hard-fails the process if ANY
connection (even an allowed loopback one) was made: a script that scripts
both the embedder and the LLM has no legitimate reason to open a socket.

Usage (from backend/):
    uv run python -m scripts.reality.fragment_facts [--folder DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("BRF_LLM", "fake")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.reality import common  # noqa: E402
from scripts.reality.digital_reality import QUESTIONS  # noqa: E402

_Q = dict(QUESTIONS)

# ---------- deterministic locators (pinned by unit tests) ----------

# Organisation-number shaped token, e.g. "123456-7890" (also matches the
# last 6+4 digits of a Swedish personnummer substring — the `_is_org_label`
# proximity gate below, not this regex alone, is what keeps a personnummer
# out of the org-number case).
_ORGNUM_RE = re.compile(r"^\d{6}-\d{4}$")

# Leaf-level appendix-table row codes, e.g. "X9.99.99" — at least two
# dotted segments after the leading letter+digit, which excludes section
# headers like "X9" or "X9.9" (one segment or none).
_ROW_CODE_RE = re.compile(r"^[A-ZÅÄÖ]\d+(\.\d+){2,}$")

# Short ALL-CAPS table-cell values, e.g. "B", "JA", "NEJ".
_VALUE_TOKEN_RE = re.compile(r"^[A-ZÅÄÖ]{1,3}$")

MAX_NAME_WORDS = 4
MAX_DESC_WORDS = 16

# Generic Swedish contract party/role labels — a small, deliberately open
# allowlist so the heuristic stays a proximity/shape rule, not a hardcode of
# this one document's exact wording.
PARTY_LABELS = {
    "företag",
    "part",
    "parter",
    "uppdragsgivare",
    "uppdragstagare",
    "beställare",
    "leverantör",
    "kund",
    "motpart",
    "avtalspart",
}


def _is_org_label(tok: str) -> bool:
    return tok.strip(":.").lower().startswith("org")


def _looks_like_name_token(tok: str) -> bool:
    return bool(tok) and tok[0].isupper() and not tok.endswith(":") and not _ORGNUM_RE.match(tok)


def locate_org_number(chunks: list) -> list[tuple]:
    """(chunk, entity_name_fragment, org_number_token) candidates, doc order.

    For each `\\d{6}-\\d{4}` token: skip one immediately preceding "org"-
    shaped label token (e.g. "Org.nr", "Org.nr:") if present, then collect
    the contiguous run of capitalized, non-label, non-numeric tokens
    immediately before that — the entity name — capped at `MAX_NAME_WORDS`
    so an unrelated preceding caption word never gets pulled in.
    """
    out: list[tuple] = []
    for chunk in chunks:
        words = chunk.text.split()
        for idx, w in enumerate(words):
            if not _ORGNUM_RE.match(w):
                continue
            j = idx - 1
            if j >= 0 and _is_org_label(words[j]):
                j -= 1
            collected: list[str] = []
            k = j
            while k >= 0 and _looks_like_name_token(words[k]) and len(collected) < MAX_NAME_WORDS:
                collected.append(words[k])
                k -= 1
            if not collected:
                continue
            out.append((chunk, " ".join(reversed(collected)), w))
    return out


def locate_party(chunks: list) -> list[tuple]:
    """(chunk, party_name_fragment, role_label_fragment) candidates, doc order.

    A role/label token (colon-terminated, stripped form in `PARTY_LABELS`)
    followed by the contiguous run of words up to the next colon-terminated
    token or an "org"-shaped label — the party-block fragment.
    """
    out: list[tuple] = []
    for chunk in chunks:
        words = chunk.text.split()
        for i, w in enumerate(words):
            if not w.endswith(":"):
                continue
            if w[:-1].lower() not in PARTY_LABELS:
                continue
            end = i + 1
            while (
                end < len(words)
                and not words[end].endswith(":")
                and not _is_org_label(words[end])
                and (end - i - 1) < MAX_NAME_WORDS
            ):
                end += 1
            name_words = words[i + 1 : end]
            if name_words:
                out.append((chunk, " ".join(name_words), w))
    return out


def locate_cell_value(chunks: list) -> list[tuple]:
    """(chunk, row_label_fragment, value_fragment) candidates, doc order.

    A leaf-level row code (`_ROW_CODE_RE`) followed by descriptive text up to
    the first short ALL-CAPS value token (`_VALUE_TOKEN_RE`) or the next row
    code — the appendix table's [label, value] cell pair.
    """
    out: list[tuple] = []
    for chunk in chunks:
        words = chunk.text.split()
        for i, w in enumerate(words):
            if not _ROW_CODE_RE.match(w):
                continue
            j = i + 1
            while (
                j < len(words)
                and not _VALUE_TOKEN_RE.match(words[j])
                and not _ROW_CODE_RE.match(words[j])
                and (j - i - 1) < MAX_DESC_WORDS
            ):
                j += 1
            if j >= len(words) or not _VALUE_TOKEN_RE.match(words[j]):
                continue
            desc_words = words[i + 1 : j]
            if len(desc_words) >= 2:
                out.append((chunk, " ".join(desc_words), words[j]))
    return out


# Case name -> (question id, locator). Question ids are the committed,
# content-free generic board questions from digital_reality.py:36-49
# (q03/q09 class) — chosen empirically per case for real top-K retrieval on
# this document (measured, not guessed): q09 for the org-number letterhead
# chunk, q08 for the parties-block chunk, q03 for the appendix task-list
# chunk (whose own headings include annual-report-adjacent bookkeeping
# tasks, a good thematic match for "who prepares the annual report").
CASES: list[tuple[str, str, "object"]] = [
    ("org_number", "q09", locate_org_number),
    ("party_name", "q08", locate_party),
    ("cell_value", "q03", locate_cell_value),
]


def _scripted_response(alias: str, spans: list[str]) -> dict:
    return {
        "answer": "Se citerat utdrag.",
        "citations": [{"chunk_id": alias, "quotes": spans}],
        "insufficient_data": False,
    }


def _process_case(name: str, qid: str, locate_fn, store, chunks: list) -> dict:
    from app.answer import ask
    from app.llm import FakeLLM

    question = _Q[qid]
    row: dict = {"case": name, "qid": qid}

    candidates = locate_fn(chunks)
    row["candidates_located"] = len(candidates)
    if not candidates:
        row["status"] = "not_locatable"
        row["reason"] = "no occurrence matched the deterministic heuristic in any chunk"
        return row

    chosen = None
    for chunk, span1, span2 in candidates:
        alias, hits = common.alias_for_chunk(store, question, chunk.id)
        if alias is not None:
            chosen = (chunk, span1, span2, alias, hits)
            break
    if chosen is None:
        row["status"] = "retrieval_miss"
        row["reason"] = (
            f"{len(candidates)} candidate(s) located but none of their chunks were "
            "retrieved in top-K for this question"
        )
        return row

    chunk, span1, span2, alias, hits = chosen
    spans = [span1, span2]
    row["page"] = chunk.page
    row["alias"] = alias
    row["n_spans"] = len(spans)

    # --- primary proof: full ask() with the correct scripted payload ---
    fake = FakeLLM([_scripted_response(alias, spans)])
    resp = ask(store, question, provider=fake)
    verified = (not resp.refusal) and len(resp.citations) == 1
    row["verified"] = verified
    if not verified:
        row["status"] = "verification_failed"
        row["refusal_reason"] = resp.refusal_reason
        row["rejected_reasons"] = [r.reason for r in resp.rejected_citations]
        return row

    cit = resp.citations[0]
    row["n_rects"] = len(cit.rects)
    row["multi_rect_ok"] = len(cit.rects) >= 2
    row["quotes_match"] = cit.quotes == spans
    page_words = store.pages[chunk.document_id][cit.page - 1].words
    row["independent_verdict"] = common.independent_rect_verdict(page_words, cit.rects, spans)
    row["independent_exact"] = row["independent_verdict"] == "exact"

    # --- probe 1: corrupt the last span -> whole citation rejects, answer refuses ---
    corrupted = list(spans)
    corrupted[-1] = common.corrupt_span(corrupted[-1])
    fake_corrupt = FakeLLM([_scripted_response(alias, corrupted)])
    resp_corrupt = ask(store, question, provider=fake_corrupt)
    row["corruption_probe"] = {
        "refused": resp_corrupt.refusal,
        "refusal_reason": resp_corrupt.refusal_reason,
        "citations_shown": len(resp_corrupt.citations),
        "rejected_reasons": [r.reason for r in resp_corrupt.rejected_citations],
    }

    # --- probe 2: same valid spans, cited against a DIFFERENT retrieved chunk ---
    other_idx = next((i for i, h in enumerate(hits) if h.chunk_id != chunk.id), None)
    if other_idx is None:
        row["cross_chunk_probe"] = {"skipped": True, "reason": "no second retrieved chunk available"}
    else:
        other_alias = f"K{other_idx + 1}"
        fake_cross = FakeLLM([_scripted_response(other_alias, spans)])
        resp_cross = ask(store, question, provider=fake_cross)
        row["cross_chunk_probe"] = {
            "cited_alias": other_alias,
            "refused": resp_cross.refusal,
            "refusal_reason": resp_cross.refusal_reason,
            "citations_shown": len(resp_cross.citations),
            "rejected_reasons": [r.reason for r in resp_cross.rejected_citations],
            "provenance_mismatch": any(
                r.reason == "provenance_mismatch" for r in resp_cross.rejected_citations
            ),
        }

    row["status"] = "resolved"
    return row


def _summarize(cases: dict, audit_log: list) -> dict:
    resolved = [c for c in cases.values() if c.get("status") == "resolved"]
    external = [e for e in audit_log if not e["allowed"]]
    corruption_ok = [
        c
        for c in resolved
        if c["corruption_probe"]["refused"]
        and c["corruption_probe"]["refusal_reason"] == "grounding_failed"
        and c["corruption_probe"]["citations_shown"] == 0
    ]
    cross_chunk_considered = [
        c for c in resolved if not c.get("cross_chunk_probe", {}).get("skipped")
    ]
    cross_chunk_ok = [c for c in cross_chunk_considered if c["cross_chunk_probe"]["provenance_mismatch"]]
    return {
        "cases_total": len(cases),
        "cases_resolved": len(resolved),
        "cases_not_locatable": sum(1 for c in cases.values() if c.get("status") == "not_locatable"),
        "cases_retrieval_miss": sum(1 for c in cases.values() if c.get("status") == "retrieval_miss"),
        "cases_verification_failed": sum(
            1 for c in cases.values() if c.get("status") == "verification_failed"
        ),
        "multi_rect_all_ok": (all(c["multi_rect_ok"] for c in resolved) if resolved else None),
        "independent_exact_all": (all(c["independent_exact"] for c in resolved) if resolved else None),
        "quotes_match_all": (all(c["quotes_match"] for c in resolved) if resolved else None),
        "corruption_probes": len(resolved),
        "corruption_all_refused_grounding_failed": (
            len(corruption_ok) == len(resolved) if resolved else None
        ),
        "cross_chunk_probes": len(cross_chunk_considered),
        "cross_chunk_all_provenance_mismatch": (
            len(cross_chunk_ok) == len(cross_chunk_considered) if cross_chunk_considered else None
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
    args = ap.parse_args()

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    digital = [pdf for pdf in sorted(args.folder.glob("*.pdf")) if common.classify(pdf)[0] == "digital"]
    if not digital:
        raise SystemExit(f"Ingen digital (born-digital) PDF hittades i {args.folder}")
    pdf = digital[0]

    cases: dict[str, dict] = {}
    with common.temp_store() as store:
        meta = common.ingest(store, pdf)
        chunks = common.sorted_doc_chunks(store, meta.id)
        print(f"Ingested: pages={meta.pages} words={meta.words} chunks={meta.chunks}", flush=True)

        for name, qid, locate_fn in CASES:
            cases[name] = _process_case(name, qid, locate_fn, store, chunks)
            c = cases[name]
            extra = f" verified={c['verified']}" if "verified" in c else ""
            print(f"{name} ({qid}): status={c['status']}{extra}", flush=True)

    summary = _summarize(cases, audit_log)
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "fragment_facts.json"
    out_json.write_text(json.dumps({"cases": cases, "summary": summary}, ensure_ascii=False, indent=2), "utf-8")
    print(f"DONE → {out_json}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    # Hardening (Task 4 review): a script whose embedder AND LLM are both
    # fully scripted has no legitimate reason to open ANY socket — hard-fail
    # loudly rather than let a non-zero-but-"allowed" count pass silently.
    common.assert_zero_connections(audit_log)


if __name__ == "__main__":
    main()
