"""BRF-1: locked descriptions, no document-count cap, five document-path runs.

    uv run python -m scripts.eval_brf1_locked

Freezes the store's current descriptions (product texts, versioned lock)
and runs the eleven cases five times on the document path. Packing follows
selection order until n_ctx — no MAX_FULL_DOCUMENTS. Does not inject the
old eval cache. Network stays on loopback.
"""

from __future__ import annotations

import json
import logging
import os
import re
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
from app.document_ask import catalog_entries, parse_selected_letters  # noqa: E402
from app.document_describe import (  # noqa: E402
    apply_description_lock,
    freeze_descriptions,
    snapshot_description_lock,
)
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import (  # noqa: E402
    CASES,
    N_CTX,
    RUNS,
    STORE_DIR,
    display_of,
    letters_for,
    three_outcome,
)
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-locked-pack"
PACK_LOG: list[dict] = []


def install_pack_log() -> None:
    handler = logging.Handler()

    def emit(record: logging.LogRecord) -> None:
        msg = record.getMessage()
        m = re.search(
            r"document_ask bound=(\S+) n_docs=(\S+) prefix_tokens=(\S+)",
            msg,
        )
        if m:
            raw_tokens = m.group(3)
            PACK_LOG.append(
                {
                    "bound": m.group(1),
                    "n_docs": int(m.group(2)),
                    "prefix_tokens": None if raw_tokens == "None" else int(float(raw_tokens)),
                }
            )

    handler.emit = emit  # type: ignore[method-assign]
    log = logging.getLogger("brf.document_ask")
    log.setLevel(logging.INFO)
    log.addHandler(handler)


def dump(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def summarize(rows: list[dict]) -> dict:
    per_run: list[Counter] = []
    for run in range(1, RUNS + 1):
        per_run.append(Counter(r["three"] for r in rows if r["run"] == run))
    facit = [c["verifierat_i_facit"] for c in per_run]
    fel = [c["verifierat_i_fel_handling"] for c in per_run]
    vag = [c["vägrad"] for c in per_run]
    ids: list[str] = []
    for r in rows:
        if r["id"] not in ids:
            ids.append(r["id"])
    by_case: dict[str, dict] = {}
    for case_id in ids:
        case_rows = [r for r in rows if r["id"] == case_id]
        counts = Counter(r["three"] for r in case_rows)
        packed_counts = [r["n_packed"] for r in case_rows]
        by_case[case_id] = {
            "verifierat_i_facit": counts["verifierat_i_facit"],
            "verifierat_i_fel_handling": counts["verifierat_i_fel_handling"],
            "vägrad": counts["vägrad"],
            "outcomes": [r["three"] for r in case_rows],
            "n_packed": packed_counts,
            "n_packed_span": [min(packed_counts), max(packed_counts)] if packed_counts else None,
            "packed": case_rows[0]["packed"] if case_rows else [],
            "selected": case_rows[0]["selected"] if case_rows else [],
        }
    packed_all = [r["n_packed"] for r in rows]
    return {
        "path": "documents",
        "runs": RUNS,
        "n_cases": 11,
        "facit_per_run": facit,
        "fel_per_run": fel,
        "vagrad_per_run": vag,
        "facit_span": [min(facit), max(facit)] if facit else None,
        "fel_span": [min(fel), max(fel)] if fel else None,
        "vagrad_span": [min(vag), max(vag)] if vag else None,
        "n_packed_span": [min(packed_all), max(packed_all)] if packed_all else None,
        "by_case": by_case,
    }


def load_or_create_lock(store: Store) -> tuple[str, dict]:
    if LOCK_PATH.exists():
        payload = json.loads(LOCK_PATH.read_text("utf-8"))
        version = apply_description_lock(store, payload)
        return version, payload
    payload = snapshot_description_lock(store)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    version = freeze_descriptions(store)
    return version, payload


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)
    install_pack_log()

    store = Store(data_dir=STORE_DIR)
    original_threshold = store.settings.fullCorpusTokenThreshold
    version, lock = load_or_create_lock(store)
    (OUT / "lock.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8")
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    catalog_pairs = catalog_entries(store.documents)
    catalog = {meta.id: letter for letter, meta in catalog_pairs}
    id_by_catalog = {letter: meta.id for letter, meta in catalog_pairs}
    valid_catalog = set(id_by_catalog)
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    n_archive = len(store.documents)

    captured: list[dict] = []
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        captured.append(
            {
                "is_describe": "Du beskriver vad en föreningshandling reglerar" in system,
                "is_selection": "Du väljer vilka handlingar" in system,
                "is_judge": system.startswith("Du är en domare."),
            }
        )
        raw = original_complete(system, user, max_tokens=max_tokens, model=model)
        captured[-1]["raw"] = raw[:300]
        return raw

    provider.complete = wrapped  # type: ignore[method-assign]

    state: dict = {
        "provider": provider.name,
        "model": model,
        "description_version": version,
        "lock_version": lock.get("version"),
        "lock_path": str(LOCK_PATH),
        "n_archive": n_archive,
        "n_ctx": N_CTX,
        "runs": RUNS,
        "rows": [],
        "n_describe_calls": 0,
        "external_connections": [],
    }
    dump(state)
    print(
        f"descriptions version={version} lock={lock.get('version')} "
        f"n_archive={n_archive} frozen={getattr(store, '_descriptions_frozen', False)}",
        flush=True,
    )

    try:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": None})
        )
        for run in range(1, RUNS + 1):
            print(f"\n=== run {run}/{RUNS} path=documents ===", flush=True)
            for case in spec:
                gold = case["doc"]
                captured.clear()
                PACK_LOG.clear()
                t0 = time.perf_counter()
                resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
                elapsed = time.perf_counter() - t0
                packed: list[str] = []
                packed_catalog: list[str] = []
                for hit in resp.retrieval:
                    letter = letters.get(hit.document_id, "?")
                    if letter not in packed:
                        packed.append(letter)
                    cat = catalog.get(hit.document_id, "?")
                    if cat not in packed_catalog:
                        packed_catalog.append(cat)
                describes = [c for c in captured if c["is_describe"]]
                selections = [c for c in captured if c["is_selection"]]
                state["n_describe_calls"] += len(describes)
                if selections:
                    selected_catalog = parse_selected_letters(selections[-1]["raw"], valid_catalog)
                    selected = [letters.get(id_by_catalog[L], "?") for L in selected_catalog if L in id_by_catalog]
                else:
                    selected_catalog = []
                    selected = []
                pack_meta = PACK_LOG[-1] if PACK_LOG else {}
                cited = [letters.get(c.document_id, "?") for c in resp.citations]
                row = {
                    "run": run,
                    "path": "documents",
                    "id": case["id"],
                    "gold": gold,
                    "three": three_outcome(resp, gold, letters),
                    "display": display_of(resp),
                    "refusal": bool(resp.refusal),
                    "refusal_reason": resp.refusal_reason,
                    "warning": resp.warning,
                    "cited": cited,
                    "packed": packed,
                    "packed_catalog": packed_catalog,
                    "selected": selected,
                    "selected_catalog": selected_catalog,
                    "n_packed": len(packed),
                    "n_selected": len(selected),
                    "selection_raw": selections[-1]["raw"] if selections else None,
                    "n_describe_calls": len(describes),
                    "pack_bound": pack_meta.get("bound"),
                    "prefix_tokens": pack_meta.get("prefix_tokens"),
                    "log_n_docs": pack_meta.get("n_docs"),
                    "elapsed_s": round(elapsed, 3),
                }
                state["rows"].append(row)
                dump(state)
                print(
                    f"r{run} {case['id']} {row['three']} packed={packed} "
                    f"n={row['n_packed']}/{n_archive} prefix={row['prefix_tokens']} "
                    f"cited={cited} {row['elapsed_s']}s",
                    flush=True,
                )
    finally:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": original_threshold})
        )

    if state["n_describe_calls"]:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {state['n_describe_calls']}")

    state["documents"] = summarize(state["rows"])
    state["external_connections"] = [e for e in audit_log if not e["allowed"]]
    dump(state)
    d = state["documents"]
    print(
        f"\ndokumentväg facit {d['facit_span'][0]}–{d['facit_span'][1]} av 11 "
        f"(per körning {d['facit_per_run']})",
        flush=True,
    )
    print(
        f"n_packed {d['n_packed_span'][0]}–{d['n_packed_span'][1]} "
        f"(arkiv {n_archive})",
        flush=True,
    )
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
