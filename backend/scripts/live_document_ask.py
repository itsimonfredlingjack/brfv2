"""Live retrieval vs document-path comparison. Numbers only in committed evidence.

Usage (from backend/):
    uv run python -m scripts.live_document_ask --folder ../DONT_PUSH_brf_stuff --slice one-doc --out out/document-ask
    uv run python -m scripts.live_document_ask --folder ../DONT_PUSH_brf_stuff --slice two-doc --out out/document-ask
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import ask  # noqa: E402
from app.document_ask import evaluate_document_path  # noqa: E402
from app.full_corpus import live_corpus_runtime  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.compare_ask_cases import compare_runs, format_table  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402

logger = logging.getLogger("brf.live_document_ask")

ONE_DOC = [
    ("q_name", "Vad heter föreningen?"),
    ("q_seat", "Var har styrelsen sitt säte?"),
    ("q_interest", "Hur stora var föreningens räntekostnader under året?"),
    ("q_solidity", "Hur stor är föreningens soliditet i procent?"),
]
TWO_DOC = [
    (
        "q_fund_vs_stadgar",
        "Vad säger stadgarna om avsättning till underhållsfond, och hur mycket fanns avsatt enligt årsredovisningen?",
    ),
    (
        "q_notice_vs_meeting",
        "Vilken kallelsetid till stämman gäller enligt stadgarna, och vilket datum hölls senaste stämman enligt årsredovisningen?",
    ),
]


def document_kind(name: str) -> str:
    n = name.casefold()
    if "stadgar" in n:
        return "stadgar"
    if any(token in n for token in ("årsred", "arsred", "årsr", "arsr")):
        return "annual_report"
    return "other"


def _ingest(store: Store, folder: Path) -> None:
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"Inga PDF:er i {folder}")
    for pdf in pdfs:
        store.add_document(pdf.name, pdf.read_bytes())


def _score_rows(decision) -> list[dict]:
    out = []
    for row in decision.scores[:3]:
        out.append(
            {
                "kind": document_kind(row.document_name),
                "max_score": row.max_score,
                "n_matching_chunks": row.n_matching_chunks,
            }
        )
    return out


def _ask_case(store: Store, qid: str, question: str, runtime, timings: list[str]) -> dict:
    index, chunks, pages, documents = store.snapshot()
    decision = evaluate_document_path(
        question=question,
        index=index,
        chunks=chunks,
        documents=documents,
        runtime=runtime,
        settings=store.settings,
    )
    t0 = time.perf_counter()
    resp = ask(store, question, corpus_runtime=runtime)
    elapsed = round(time.perf_counter() - t0, 3)
    if store.settings.fullCorpusTokenThreshold == 0:
        ask_path = "retrieval"
        bound = "threshold"
        n_packed = 0
    elif decision.use_documents:
        ask_path = "documents"
        bound = decision.bound
        n_packed = len(decision.document_ids)
    else:
        ask_path = "retrieval"
        bound = decision.bound
        n_packed = 0
    top_kind = document_kind(decision.scores[0].document_name) if decision.scores else None
    return {
        "qid": qid,
        "refused": resp.refusal,
        "refusal_reason": resp.refusal_reason,
        "n_citations": len(resp.citations),
        "elapsed_s": elapsed,
        "ask_path": ask_path,
        "bound": bound,
        "n_packed": n_packed,
        "top_document_kind": top_kind,
        "scores": _score_rows(decision),
        "n_retrieval": len(resp.retrieval),
        "timings_log": list(timings[-1:]),
    }


class _TimingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "llama.cpp timings" in msg:
            self.lines.append(msg)


def run_slice(folder: Path, questions: list[tuple[str, str]], threshold: int, data_dir: Path) -> dict:
    store = Store(data_dir=data_dir)
    _ingest(store, folder)
    store.update_settings(
        store.settings.model_copy(update={"fullCorpusTokenThreshold": threshold, "minRelevance": 0.0})
    )
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("live_corpus_runtime saknas — sätt BRF_LLM och BRF_LLM_BASE_URL")
    handler = _TimingHandler()
    logging.getLogger("brf.llm").addHandler(handler)
    rows = []
    for qid, question in questions:
        n_before = len(handler.lines)
        row = _ask_case(store, qid, question, runtime, handler.lines)
        row["timings_log"] = handler.lines[n_before:]
        rows.append(row)
        print(
            f"threshold={threshold} {qid} path={row['ask_path']} bound={row['bound']} "
            f"refused={row['refused']} packed={row['n_packed']} elapsed_s={row['elapsed_s']}",
            flush=True,
        )
    logging.getLogger("brf.llm").removeHandler(handler)
    return {"documents": {"association": {"questions": rows}}}


def top_miss_rate(run: dict) -> float:
    rows = (run.get("documents") or {}).get("association", {}).get("questions") or []
    if not rows:
        return 0.0
    misses = sum(1 for r in rows if r.get("bound") == "top_document_n_ctx")
    return misses / len(rows)


def packed_only_runs(before: dict, after: dict) -> tuple[dict, dict]:
    after_q = {
        r["qid"]: r
        for r in (after.get("documents") or {}).get("association", {}).get("questions") or []
        if r.get("ask_path") == "documents"
    }
    before_q = {
        r["qid"]: r
        for r in (before.get("documents") or {}).get("association", {}).get("questions") or []
        if r["qid"] in after_q
    }
    return (
        {"documents": {"association": {"questions": list(before_q.values())}}},
        {"documents": {"association": {"questions": list(after_q.values())}}},
    )


def _enforce_loopback(audit_log: list[dict]) -> None:
    external = [e for e in audit_log if not e.get("allowed", False)]
    if external:
        hosts = sorted({f"{e['host']}:{e['port']}" for e in external})
        raise SystemExit(
            f"NÄTVERKSREVISION MISSLYCKADES: {len(external)} extern(a) anslutning(ar). Värdar: {hosts}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("out/document-ask"))
    ap.add_argument("--slice", choices=("one-doc", "two-doc"), required=True)
    args = ap.parse_args()

    os.environ.setdefault("BRF_EMBEDDER", "hashed")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("BRF_LLM", "selfhosted")
    os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")

    audit_log, _allowed = install_network_audit()
    questions = ONE_DOC if args.slice == "one-doc" else TWO_DOC
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        before = run_slice(args.folder, questions, 0, Path(tmp) / "before")
        after = run_slice(args.folder, questions, 32000, Path(tmp) / "after")
    (args.out / f"{args.slice}_before.json").write_text(json.dumps(before), encoding="utf-8")
    (args.out / f"{args.slice}_after.json").write_text(json.dumps(after), encoding="utf-8")
    overall = compare_runs(before, after)
    packed_b, packed_a = packed_only_runs(before, after)
    packed = compare_runs(packed_b, packed_a)
    summary = {
        "slice": args.slice,
        "top_miss_rate": top_miss_rate(after),
        "overall": {"verified_to_refused": overall["verified_to_refused"], "refused_to_verified": overall["refused_to_verified"]},
        "packed_only": {"verified_to_refused": packed["verified_to_refused"], "refused_to_verified": packed["refused_to_verified"]},
    }
    (args.out / f"{args.slice}_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    print(format_table(overall), flush=True)
    print(f"top_miss_rate={summary['top_miss_rate']}", flush=True)
    print(
        f"packed_only verified_to_refused={packed['verified_to_refused']} "
        f"refused_to_verified={packed['refused_to_verified']}",
        flush=True,
    )
    _enforce_loopback(audit_log)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    main()
