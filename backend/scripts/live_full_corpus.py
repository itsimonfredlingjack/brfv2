"""Live retrieval vs full-corpus path at operational n_ctx.

Temp-store threshold=0 (retrieval) vs None (window cap only).

Usage (from backend/):
    uv run python -m scripts.live_full_corpus --folder ../DONT_PUSH_brf_stuff --out out/full-corpus-64k
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

from app.answer import ask, evaluate_full_corpus  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.compare_ask_cases import compare_runs, format_table  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

logger = logging.getLogger("brf.live_full_corpus")

ARCHIVE_AFTER_THRESHOLD = None
ARCHIVE_N_CTX = 65536
QUESTIONS = [
    ("q_name", "Vad heter föreningen?"),
    ("q_seat", "Var har styrelsen sitt säte?"),
    ("q_notice", "Vilken kallelsetid till stämman gäller enligt stadgarna?"),
]


def _ingest(store: Store, folder: Path) -> None:
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"Inga PDF:er i {folder}")
    for pdf in pdfs:
        store.add_document(pdf.name, pdf.read_bytes())


class _TimingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "llama.cpp timings" in msg:
            self.lines.append(msg)


def _ask_case(store: Store, qid: str, question: str, runtime, timings: list[str]) -> dict:
    index, chunks, pages, documents = store.snapshot()
    evaluated = evaluate_full_corpus(store, chunks, documents, runtime)
    decision = evaluated[0] if evaluated is not None else None
    t0 = time.perf_counter()
    resp = ask(store, question, corpus_runtime=runtime)
    elapsed = round(time.perf_counter() - t0, 3)
    if decision is not None and decision.use_full_corpus:
        ask_path = "full_corpus"
        bound = decision.bound
        prefix_tokens = decision.prefix_tokens
    else:
        ask_path = "retrieval"
        bound = decision.bound if decision is not None else "unknown"
        prefix_tokens = decision.prefix_tokens if decision is not None else None
    return {
        "qid": qid,
        "refused": resp.refusal,
        "refusal_reason": resp.refusal_reason,
        "n_citations": len(resp.citations),
        "elapsed_s": elapsed,
        "ask_path": ask_path,
        "bound": bound,
        "prefix_tokens": prefix_tokens,
        "chunk_token_sum": decision.chunk_token_sum if decision is not None else None,
        "n_ctx": decision.n_ctx if decision is not None else None,
        "n_retrieval": len(resp.retrieval),
        "timings_log": list(timings[-1:]),
    }


def run_slice(folder: Path, threshold: int | None, data_dir: Path) -> dict:
    store = Store(data_dir=data_dir)
    store._prefer_full_corpus = True
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
    for qid, question in QUESTIONS:
        n_before = len(handler.lines)
        row = _ask_case(store, qid, question, runtime, handler.lines)
        row["timings_log"] = handler.lines[n_before:]
        rows.append(row)
        print(
            f"threshold={threshold} {qid} path={row['ask_path']} bound={row['bound']} "
            f"refused={row['refused']} elapsed_s={row['elapsed_s']}",
            flush=True,
        )
    logging.getLogger("brf.llm").removeHandler(handler)
    return {"documents": {"association": {"questions": rows}}}


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
    ap.add_argument("--out", type=Path, default=Path("out/full-corpus-64k"))
    args = ap.parse_args()

    os.environ.setdefault("BRF_EMBEDDER", "model2vec")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("BRF_LLM", "selfhosted")
    os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")

    base = os.environ["BRF_LLM_BASE_URL"]
    origin = server_origin(base)
    audit_log, _allowed = install_network_audit()
    args.out.mkdir(parents=True, exist_ok=True)

    before = None
    after = None
    if not wait_n_ctx(origin, ARCHIVE_N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx är inte {ARCHIVE_N_CTX} — driftfilen ska bära -c {ARCHIVE_N_CTX}")
    with tempfile.TemporaryDirectory() as tmp:
        before = run_slice(args.folder, 0, Path(tmp) / "before")
        after = run_slice(args.folder, ARCHIVE_AFTER_THRESHOLD, Path(tmp) / "after")

    if before is None or after is None:
        raise SystemExit("arkivmätningen producerade inga körningar")

    (args.out / "archive_before.json").write_text(json.dumps(before), encoding="utf-8")
    (args.out / "archive_after.json").write_text(json.dumps(after), encoding="utf-8")
    overall = compare_runs(before, after)
    after_paths = [r["ask_path"] for r in after["documents"]["association"]["questions"]]
    summary = {
        "verified_to_refused": overall["verified_to_refused"],
        "refused_to_verified": overall["refused_to_verified"],
        "after_paths": after_paths,
        "after_threshold": ARCHIVE_AFTER_THRESHOLD,
    }
    (args.out / "archive_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    print(format_table(overall), flush=True)
    print(f"after_paths={after_paths}", flush=True)
    _enforce_loopback(audit_log)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    main()
