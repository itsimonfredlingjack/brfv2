"""BRF-1 variance: five runs of the eleven cases on two ask paths.

    uv run python -m scripts.eval_brf1_variance

Does not change product defaults. Document path = current ask()
(description selection). Retrieval = fullCorpusTokenThreshold=0.
Network stays on loopback. Incremental JSON after every ask.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
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

from app.answer import ask  # noqa: E402
from app.answer_judge import INCOMPLETE_MARK  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

STORE_DIR = Path("/tmp/brf1-store")
CASES = Path("/tmp/brf1-cases/eleven.json")
DESC_CACHE = backend / "out" / "brf1-doc-descriptions" / "descriptions.json"
OUT = backend / "out" / "brf1-variance"
N_CTX = 65536
RUNS = 5
PATHS = ("documents", "retrieval")


def letters_for(store: Store) -> dict[str, str]:
    return {
        m.id: chr(ord("A") + i)
        for i, m in enumerate(sorted(store.documents.values(), key=lambda m: m.name))
    }


def install_descriptions(store: Store) -> None:
    data = json.loads(DESC_CACHE.read_text("utf-8"))
    by_letter = {e["letter"]: e["description"] for e in data["entries"]}
    for doc_id, letter in letters_for(store).items():
        desc = by_letter[letter]
        meta = store.documents[doc_id]
        store.documents[doc_id] = meta.model_copy(
            update={"description": desc, "description_fp": "eval-variance"}
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
    if INCOMPLETE_MARK in (resp.warning or ""):
        return "markerat"
    return "visat"


def summarize(rows: list[dict], path: str) -> dict:
    path_rows = [r for r in rows if r["path"] == path]
    per_run: list[Counter] = []
    for run in range(1, RUNS + 1):
        c = Counter(r["three"] for r in path_rows if r["run"] == run)
        per_run.append(c)
    facit = [c["verifierat_i_facit"] for c in per_run]
    fel = [c["verifierat_i_fel_handling"] for c in per_run]
    vag = [c["vägrad"] for c in per_run]
    by_case: dict[str, dict] = {}
    ids = []
    for r in path_rows:
        if r["id"] not in ids:
            ids.append(r["id"])
    for case_id in ids:
        counts = Counter(r["three"] for r in path_rows if r["id"] == case_id)
        by_case[case_id] = {
            "verifierat_i_facit": counts["verifierat_i_facit"],
            "verifierat_i_fel_handling": counts["verifierat_i_fel_handling"],
            "vägrad": counts["vägrad"],
            "outcomes": [r["three"] for r in path_rows if r["id"] == case_id],
        }
    return {
        "path": path,
        "runs": RUNS,
        "n_cases": 11,
        "facit_per_run": facit,
        "fel_per_run": fel,
        "vagrad_per_run": vag,
        "facit_span": [min(facit), max(facit)] if facit else None,
        "fel_span": [min(fel), max(fel)] if fel else None,
        "vagrad_span": [min(vag), max(vag)] if vag else None,
        "by_case": by_case,
    }


def dump(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)

    store = Store(data_dir=STORE_DIR)
    original_threshold = store.settings.fullCorpusTokenThreshold
    install_descriptions(store)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")

    state: dict = {
        "provider": provider.name,
        "model": model,
        "temperature_in_request": 0,
        "top_p_in_request": None,
        "seed_in_request": None,
        "server_defaults": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
            "seed": "unset (4294967295)",
        },
        "runs": RUNS,
        "rows": [],
        "external_connections": [],
    }
    dump(state)

    try:
        _run_matrix(store, spec, provider, runtime, letters, state)
    finally:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": original_threshold})
        )

    state["documents"] = summarize(state["rows"], "documents")
    state["retrieval"] = summarize(state["rows"], "retrieval")
    state["external_connections"] = [e for e in audit_log if not e["allowed"]]
    dump(state)
    d, r = state["documents"], state["retrieval"]
    print(
        f"\ndokumentväg facit {d['facit_span'][0]}–{d['facit_span'][1]} av 11 "
        f"(per körning {d['facit_per_run']})",
        flush=True,
    )
    print(
        f"retrieval facit {r['facit_span'][0]}–{r['facit_span'][1]} av 11 "
        f"(per körning {r['facit_per_run']})",
        flush=True,
    )
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


def _run_matrix(store, spec, provider, runtime, letters, state) -> None:
    for run in range(1, RUNS + 1):
        for path in PATHS:
            threshold = None if path == "documents" else 0
            store.update_settings(store.settings.model_copy(update={"fullCorpusTokenThreshold": threshold}))
            print(f"\n=== run {run}/{RUNS} path={path} threshold={threshold} ===", flush=True)
            for case in spec:
                gold = case["doc"]
                t0 = time.perf_counter()
                resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
                elapsed = time.perf_counter() - t0
                cited = [letters.get(c.document_id, "?") for c in resp.citations]
                row = {
                    "run": run,
                    "path": path,
                    "id": case["id"],
                    "gold": gold,
                    "three": three_outcome(resp, gold, letters),
                    "display": display_of(resp),
                    "refusal": bool(resp.refusal),
                    "refusal_reason": resp.refusal_reason,
                    "warning": resp.warning,
                    "cited": cited,
                    "elapsed_s": round(elapsed, 3),
                }
                state["rows"].append(row)
                dump(state)
                print(
                    f"r{run} {path} {case['id']} {row['three']} "
                    f"display={row['display']} cited={cited} {row['elapsed_s']}s",
                    flush=True,
                )


if __name__ == "__main__":
    raise SystemExit(main())
