"""Ränta, soliditet and two-document questions, five runs, locked descriptions.

    uv run python -m scripts.eval_brf1_eken_finance

Primary store: /tmp/brf1-store-eken (Eken's own annual report + stadgar).
Optional --digital-ars runs ränta/soliditet only against /tmp/brf1-store-with-ars
(the previously ingested born-digital report from another association).
"""

from __future__ import annotations

import argparse
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
from app.document_describe import apply_description_lock, freeze_descriptions  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import N_CTX, RUNS, display_of, letters_for  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

STORE_EKEN = Path("/tmp/brf1-store-eken")
STORE_DIGITAL_ARS = Path("/tmp/brf1-store-with-ars")
LOCK_EKEN = backend / "out" / "brf1-eken-ingest" / "lock.json"
OUT_EKEN = backend / "out" / "brf1-eken-finance"
OUT_DIGITAL = backend / "out" / "brf1-digital-ars-finance"
PACK_LOG: list[dict] = []

FINANCE = [
    {
        "id": "q_interest",
        "question": "Hur stora var föreningens räntekostnader under året?",
        "golds": ["annual_report"],
        "layer": "ocr",
    },
    {
        "id": "q_solidity",
        "question": "Hur stor är föreningens soliditet i procent?",
        "golds": ["annual_report"],
        "layer": "ocr",
    },
]
TWO_DOC = [
    {
        "id": "q_fund_vs_stadgar",
        "question": (
            "Vad säger stadgarna om avsättning till underhållsfond, "
            "och hur mycket fanns avsatt enligt årsredovisningen?"
        ),
        "golds": ["stadgar", "annual_report"],
        "layer": "ocr",
    },
    {
        "id": "q_notice_vs_meeting",
        "question": (
            "Vilken kallelsetid till stämman gäller enligt stadgarna, "
            "och vilket datum hölls senaste stämman enligt årsredovisningen?"
        ),
        "golds": ["stadgar", "annual_report"],
        "layer": "ocr",
    },
]


def document_kind(name: str) -> str:
    n = name.casefold()
    if "stadgar" in n:
        return "stadgar"
    if "årsred" in n or "arsred" in n:
        return "annual_report"
    if "revision" in n:
        return "auditor_report"
    if "ekonomisk plan" in n:
        return "economic_plan"
    if "bofaktablad" in n:
        return "brochure"
    return "other"


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


def three_outcome_kinds(resp, gold_kinds: list[str], kind_of: dict[str, str]) -> str:
    cited_kinds = [kind_of.get(c.document_id, "other") for c in resp.citations]
    if resp.refusal or not cited_kinds:
        return "vägrad"
    missing = [g for g in gold_kinds if g not in cited_kinds]
    if not missing:
        return "verifierat_i_facit"
    return "verifierat_i_fel_handling"


def dump(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize(rows: list[dict], n_cases: int) -> dict:
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
            "layer": case_rows[0]["layer"] if case_rows else None,
            "golds": case_rows[0]["golds"] if case_rows else [],
            "partial": [r["partial"] for r in case_rows],
        }
    packed_all = [r["n_packed"] for r in rows]
    return {
        "runs": RUNS,
        "n_cases": n_cases,
        "facit_per_run": facit,
        "fel_per_run": fel,
        "vagrad_per_run": vag,
        "facit_span": [min(facit), max(facit)] if facit else None,
        "fel_span": [min(fel), max(fel)] if fel else None,
        "vagrad_span": [min(vag), max(vag)] if vag else None,
        "n_packed_span": [min(packed_all), max(packed_all)] if packed_all else None,
        "by_case": by_case,
    }


def load_lock(store: Store, lock_path: Path | None) -> str:
    if lock_path and lock_path.exists():
        payload = json.loads(lock_path.read_text("utf-8"))
        return apply_description_lock(store, payload)
    return freeze_descriptions(store)


def run_eval(
    *,
    store_dir: Path,
    out_dir: Path,
    cases: list[dict],
    lock_path: Path | None,
    layer_label: str,
) -> dict:
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin} store={store_dir} layer={layer_label}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)
    install_pack_log()

    store = Store(data_dir=store_dir)
    original_threshold = store.settings.fullCorpusTokenThreshold
    version = load_lock(store, lock_path)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    kind_of = {m.id: document_kind(m.name) for m in store.documents.values()}
    source_of = {m.id: m.source for m in store.documents.values()}
    catalog_pairs = catalog_entries(store.documents)
    id_by_catalog = {letter: meta.id for letter, meta in catalog_pairs}
    valid_catalog = set(id_by_catalog)
    n_archive = len(store.documents)
    captured: list[dict] = []
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        captured.append(
            {
                "is_describe": "Du beskriver vad en föreningshandling reglerar" in system,
                "is_selection": "Du väljer vilka handlingar" in system,
            }
        )
        raw = original_complete(system, user, max_tokens=max_tokens, model=model)
        captured[-1]["raw"] = raw
        return raw

    provider.complete = wrapped  # type: ignore[method-assign]
    result_path = out_dir / "result.json"
    state: dict = {
        "store": str(store_dir),
        "layer_label": layer_label,
        "description_version": version,
        "n_archive": n_archive,
        "n_ctx": N_CTX,
        "runs": RUNS,
        "kinds": {
            letters[i]: {"kind": kind_of[i], "source": source_of[i]}
            for i in letters
        },
        "rows": [],
        "n_describe_calls": 0,
        "external_connections": [],
    }
    dump(result_path, state)

    try:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": None})
        )
        for run in range(1, RUNS + 1):
            print(f"\n=== run {run}/{RUNS} {layer_label} ===", flush=True)
            for case in cases:
                captured.clear()
                PACK_LOG.clear()
                t0 = time.perf_counter()
                resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
                elapsed = time.perf_counter() - t0
                packed_kinds: list[str] = []
                packed: list[str] = []
                for hit in resp.retrieval:
                    letter = letters.get(hit.document_id, "?")
                    if letter not in packed:
                        packed.append(letter)
                    k = kind_of.get(hit.document_id, "other")
                    if k not in packed_kinds:
                        packed_kinds.append(k)
                describes = [c for c in captured if c["is_describe"]]
                selections = [c for c in captured if c["is_selection"]]
                state["n_describe_calls"] += len(describes)
                if selections:
                    selected_catalog = parse_selected_letters(selections[-1]["raw"], valid_catalog)
                    selected = [
                        letters.get(id_by_catalog[L], "?")
                        for L in selected_catalog
                        if L in id_by_catalog
                    ]
                    selected_kinds = [
                        kind_of.get(id_by_catalog[L], "other")
                        for L in selected_catalog
                        if L in id_by_catalog
                    ]
                else:
                    selected, selected_kinds = [], []
                pack_meta = PACK_LOG[-1] if PACK_LOG else {}
                cited = [letters.get(c.document_id, "?") for c in resp.citations]
                cited_kinds = [kind_of.get(c.document_id, "other") for c in resp.citations]
                cited_sources = [source_of.get(c.document_id, "?") for c in resp.citations]
                gold_hit = [g for g in case["golds"] if g in cited_kinds]
                row = {
                    "run": run,
                    "id": case["id"],
                    "golds": case["golds"],
                    "layer": case["layer"],
                    "three": three_outcome_kinds(resp, case["golds"], kind_of),
                    "partial": bool(gold_hit) and set(gold_hit) != set(case["golds"]),
                    "gold_hit": gold_hit,
                    "display": display_of(resp),
                    "refusal": bool(resp.refusal),
                    "refusal_reason": resp.refusal_reason,
                    "warning": resp.warning,
                    "cited": cited,
                    "cited_kinds": cited_kinds,
                    "cited_sources": cited_sources,
                    "packed": packed,
                    "packed_kinds": packed_kinds,
                    "selected": selected,
                    "selected_kinds": selected_kinds,
                    "n_packed": len(packed),
                    "pack_bound": pack_meta.get("bound"),
                    "prefix_tokens": pack_meta.get("prefix_tokens"),
                    "elapsed_s": round(elapsed, 3),
                    "n_describe_calls": len(describes),
                }
                state["rows"].append(row)
                dump(result_path, state)
                print(
                    f"r{run} {case['id']} {row['three']} packed={packed_kinds} "
                    f"cited={cited_kinds} src={cited_sources} {row['elapsed_s']}s",
                    flush=True,
                )
    finally:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": original_threshold})
        )

    if state["n_describe_calls"]:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {state['n_describe_calls']}")
    state["summary"] = summarize(state["rows"], n_cases=len(cases))
    state["external_connections"] = [e for e in audit_log if not e["allowed"]]
    dump(result_path, state)
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    d = state["summary"]
    print(
        f"\n{layer_label} facit {d['facit_span'][0]}–{d['facit_span'][1]} av {len(cases)} "
        f"(per körning {d['facit_per_run']})",
        flush=True,
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--digital-ars",
        action="store_true",
        help="Also run ränta/soliditet against the born-digital other-association report",
    )
    args = parser.parse_args()
    run_eval(
        store_dir=STORE_EKEN,
        out_dir=OUT_EKEN,
        cases=FINANCE + TWO_DOC,
        lock_path=LOCK_EKEN,
        layer_label="eken-ocr",
    )
    if args.digital_ars:
        digital_cases = [
            {**c, "layer": "digital"}
            for c in FINANCE
        ]
        run_eval(
            store_dir=STORE_DIGITAL_ARS,
            out_dir=OUT_DIGITAL,
            cases=digital_cases,
            lock_path=None,
            layer_label="digital-ars",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
