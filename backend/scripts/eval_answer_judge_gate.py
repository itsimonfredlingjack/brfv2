"""BRF-1 document path with the answer judge connected.

    uv run python -m scripts.eval_answer_judge_gate

Product ask(): description selection, then judge after numeric grounding.
Network stays on loopback. Writes letters and numbers, not archive text.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

backend = Path(__file__).resolve().parent.parent
os.chdir(backend)
sys.path.insert(0, str(backend))

os.environ.setdefault("BRF_EMBEDDER", "model2vec")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("BRF_LLM", "selfhosted")
os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")
os.environ["BRF_PREFIX_WARMUP"] = "0"
os.environ.pop("BRF_PLANNED_ASK", None)

import app.answer as answer_mod  # noqa: E402
from app.answer import ask  # noqa: E402
from app.answer_judge import INCOMPLETE_MARK, judge_answer as original_judge  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

STORE_DIR = Path("/tmp/brf1-store")
CASES = Path("/tmp/brf1-cases/eleven.json")
DESC_CACHE = backend / "out" / "brf1-doc-descriptions" / "descriptions.json"
OUT = backend / "out" / "brf1-answer-judge-gate"
N_CTX = 65536

JUDGE_LOG: list[dict] = []
TIMINGS: list[dict] = []


def install_timing_log_capture() -> None:
    handler = logging.Handler()

    def emit(record: logging.LogRecord) -> None:
        msg = record.getMessage()
        m = re.search(r"prompt_n=(\S+) prompt_ms=(\S+) cache_n=(\S+)", msg)
        if m:
            TIMINGS.append(
                {
                    "prompt_n": int(float(m.group(1))),
                    "prompt_ms": float(m.group(2)),
                    "cache_n": int(float(m.group(3))),
                }
            )
        j = re.search(r"svarsdomare utfall=(\S+) elapsed_s=(\S+)", msg)
        if j:
            JUDGE_LOG.append({"outcome": j.group(1), "elapsed_s": float(j.group(2))})

    handler.emit = emit  # type: ignore[method-assign]
    logging.getLogger("brf.llm").addHandler(handler)
    logging.getLogger("brf.answer").addHandler(handler)


def letters_for(store: Store) -> dict[str, str]:
    return {
        m.id: chr(ord("A") + i)
        for i, m in enumerate(sorted(store.documents.values(), key=lambda m: m.name))
    }


def install_descriptions(store: Store) -> None:
    data = json.loads(DESC_CACHE.read_text("utf-8"))
    by_letter = {e["letter"]: e["description"] for e in data["entries"]}
    letters = letters_for(store)
    for doc_id, letter in letters.items():
        desc = by_letter[letter]
        meta = store.documents[doc_id]
        store.documents[doc_id] = meta.model_copy(
            update={"description": desc, "description_fp": "eval-gate"}
        )


def three_outcome(resp, gold: str, letters: dict[str, str]) -> str:
    cited = [letters.get(c.document_id, "?") for c in resp.citations]
    if resp.refusal or not cited:
        return "vägrad"
    if gold in cited:
        return "verifierat_i_facit"
    return "verifierat_i_fel_handling"


def display_of(resp) -> str:
    if resp.refusal:
        return "vägrad"
    warning = resp.warning or ""
    if INCOMPLETE_MARK in warning:
        return "markerat"
    return "visat"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")

    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)
    install_timing_log_capture()

    store = Store(data_dir=STORE_DIR)
    store.update_settings(store.settings.model_copy(update={"fullCorpusTokenThreshold": None}))
    install_descriptions(store)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")

    wrapped_n = {"n": 0}

    def wrapped_judge(provider, question, quotes, answer, *, model):
        wrapped_n["n"] += 1
        t0 = time.perf_counter()
        result = original_judge(provider, question, quotes, answer, model=model)
        JUDGE_LOG.append(
            {
                "outcome": result.outcome,
                "elapsed_s": round(time.perf_counter() - t0, 3),
                "parse": result.reason,
            }
        )
        return result

    answer_mod.judge_answer = wrapped_judge  # type: ignore[method-assign]

    rows: list[dict] = []
    for case in spec:
        gold = case["doc"]
        before_judge = len(JUDGE_LOG)
        before_t = len(TIMINGS)
        t0 = time.perf_counter()
        resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
        elapsed = time.perf_counter() - t0
        cited = [
            {"doc": letters.get(c.document_id, "?"), "page": c.page, "quotes": list(c.quotes)}
            for c in resp.citations
        ]
        judge_slice = JUDGE_LOG[before_judge:]
        timing_slice = TIMINGS[before_t:]
        row = {
            "id": case["id"],
            "gold": gold,
            "question": case["question"],
            "answer": resp.answer,
            "refusal": bool(resp.refusal),
            "refusal_reason": resp.refusal_reason,
            "warning": resp.warning,
            "cited": cited,
            "three": three_outcome(resp, gold, letters),
            "display": display_of(resp),
            "judge": judge_slice[-1] if judge_slice else None,
            "judge_called": bool(judge_slice),
            "elapsed_s": round(elapsed, 3),
            "timings": timing_slice,
        }
        rows.append(row)
        print(
            f"{case['id']} three={row['three']} display={row['display']} "
            f"judge={row['judge']} elapsed={row['elapsed_s']}",
            flush=True,
        )

    counts = {
        "verifierat_i_facit": sum(1 for r in rows if r["three"] == "verifierat_i_facit"),
        "verifierat_i_fel_handling": sum(1 for r in rows if r["three"] == "verifierat_i_fel_handling"),
        "vägrad": sum(1 for r in rows if r["three"] == "vägrad"),
    }
    displays = {
        "visat": sum(1 for r in rows if r["display"] == "visat"),
        "markerat": sum(1 for r in rows if r["display"] == "markerat"),
        "vägrad": sum(1 for r in rows if r["display"] == "vägrad"),
    }
    judge_elapsed = [r["judge"]["elapsed_s"] for r in rows if r["judge"]]
    summary = {
        "provider": provider.name,
        "model": model,
        "n": len(rows),
        "three": counts,
        "display": displays,
        "judge_called_n": sum(1 for r in rows if r["judge_called"]),
        "judge_elapsed_s": {
            "n": len(judge_elapsed),
            "mean": round(sum(judge_elapsed) / len(judge_elapsed), 3) if judge_elapsed else None,
            "max": round(max(judge_elapsed), 3) if judge_elapsed else None,
        },
        "per_case_avg_elapsed_s": round(sum(r["elapsed_s"] for r in rows) / len(rows), 3),
        "wrapped_judge_n": wrapped_n["n"],
        "external_connections": [e for e in audit_log if not e["allowed"]],
        "rows": rows,
    }
    (OUT / "result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\nthree {counts['verifierat_i_facit']}/{counts['verifierat_i_fel_handling']}/{counts['vägrad']} "
        f"display visat={displays['visat']} markerat={displays['markerat']} vägrad={displays['vägrad']} "
        f"judge_mean={summary['judge_elapsed_s']['mean']}s",
        flush=True,
    )
    if summary["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
