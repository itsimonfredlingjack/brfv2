"""BRF-1: measure whether insufficient_data refusals name the gold kind.

    uv run python -m scripts.eval_brf1_refusal_help

Locked descriptions, document path, one ask() per case. Does not change
selection, citation verification, or the answer judge. Network on loopback.
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

from app.answer import ask  # noqa: E402
from app.document_ask import catalog_entries, parse_selected_letters  # noqa: E402
from app.document_describe import apply_description_lock  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.refusal_help import extract_kind_clause, names_gold_kind  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import (  # noqa: E402
    CASES,
    N_CTX,
    STORE_DIR,
    display_of,
    letters_for,
    three_outcome,
)
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-refusal-help"
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
    refused = [r for r in rows if r["refusal"]]
    helpful = [r for r in refused if r["refusal_reason"] == "insufficient_data"]
    named = [r for r in helpful if r["names_gold_kind"]]
    return {
        "n_cases": len(rows),
        "n_refused": len(refused),
        "n_insufficient_data": len(helpful),
        "n_named_gold_kind": len(named),
        "named_rate": None if not helpful else len(named) / len(helpful),
        "insufficient_ids": [r["id"] for r in helpful],
        "named_ids": [r["id"] for r in named],
        "missed_ids": [r["id"] for r in helpful if not r["names_gold_kind"]],
        "other_refusals": [
            {"id": r["id"], "reason": r["refusal_reason"]}
            for r in refused
            if r["refusal_reason"] != "insufficient_data"
        ],
    }


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
    lock = json.loads(LOCK_PATH.read_text("utf-8"))
    version = apply_description_lock(store, lock)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    id_by_letter = {letter: doc_id for doc_id, letter in letters.items()}
    catalog_pairs = catalog_entries(store.documents)
    id_by_catalog = {letter: meta.id for letter, meta in catalog_pairs}
    valid_catalog = set(id_by_catalog)
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")

    captured: list[dict] = []
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        captured.append(
            {
                "is_describe": "Du beskriver vad en föreningshandling reglerar" in system,
                "is_selection": "Du väljer vilka handlingar" in system,
                "is_judge": system.startswith("Du är en domare."),
                "is_kind": system.startswith("Du säger vilken sorts handling"),
                "is_match": system.startswith("Du matchar en handlingssort"),
            }
        )
        raw = original_complete(system, user, max_tokens=max_tokens, model=model)
        captured[-1]["raw"] = raw[:400]
        return raw

    provider.complete = wrapped  # type: ignore[method-assign]

    state: dict = {
        "provider": provider.name,
        "model": model,
        "description_version": version,
        "lock_version": lock.get("version"),
        "n_archive": len(store.documents),
        "n_ctx": N_CTX,
        "rows": [],
        "n_describe_calls": 0,
        "external_connections": [],
    }
    dump(state)

    try:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": None})
        )
        for case in spec:
            gold = case["doc"]
            gold_id = id_by_letter[gold]
            gold_meta = store.documents[gold_id]
            captured.clear()
            PACK_LOG.clear()
            t0 = time.perf_counter()
            resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
            elapsed = time.perf_counter() - t0
            packed: list[str] = []
            packed_names: list[str] = []
            for hit in resp.retrieval:
                letter = letters.get(hit.document_id, "?")
                if letter not in packed:
                    packed.append(letter)
                    packed_names.append(hit.document_name)
            describes = [c for c in captured if c["is_describe"]]
            selections = [c for c in captured if c["is_selection"]]
            kinds = [c for c in captured if c["is_kind"]]
            matches = [c for c in captured if c["is_match"]]
            state["n_describe_calls"] += len(describes)
            if selections:
                selected_catalog = parse_selected_letters(selections[-1]["raw"], valid_catalog)
                selected = [
                    letters.get(id_by_catalog[letter], "?")
                    for letter in selected_catalog
                    if letter in id_by_catalog
                ]
            else:
                selected = []
            kind_clause = extract_kind_clause(resp.answer) if resp.refusal else None
            named = bool(
                resp.refusal
                and resp.refusal_reason == "insufficient_data"
                and names_gold_kind(
                    resp.answer, gold_meta.name, gold_meta.description or ""
                )
            )
            row = {
                "id": case["id"],
                "question": case["question"],
                "gold": gold,
                "gold_name": gold_meta.name,
                "three": three_outcome(resp, gold, letters),
                "display": display_of(resp),
                "refusal": bool(resp.refusal),
                "refusal_reason": resp.refusal_reason,
                "answer": resp.answer,
                "kind_clause": kind_clause,
                "names_gold_kind": named,
                "packed": packed,
                "packed_names": packed_names,
                "selected": selected,
                "n_kind_calls": len(kinds),
                "n_match_calls": len(matches),
                "kind_raw": kinds[-1]["raw"] if kinds else None,
                "match_raw": matches[-1]["raw"] if matches else None,
                "n_describe_calls": len(describes),
                "prefix_tokens": PACK_LOG[-1].get("prefix_tokens") if PACK_LOG else None,
                "elapsed_s": round(elapsed, 3),
            }
            state["rows"].append(row)
            dump(state)
            print(
                f"{case['id']} {row['three']} reason={row['refusal_reason']} "
                f"named={named} kind={kind_clause!r} {row['elapsed_s']}s",
                flush=True,
            )
    finally:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": original_threshold})
        )

    if state["n_describe_calls"]:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {state['n_describe_calls']}")

    state["summary"] = summarize(state["rows"])
    state["external_connections"] = [e for e in audit_log if not e["allowed"]]
    dump(state)
    s = state["summary"]
    print(
        f"\ninsufficient_data {s['n_insufficient_data']} av {s['n_cases']}; "
        f"namngav facitsort {s['n_named_gold_kind']}/{s['n_insufficient_data']} "
        f"({s['named_rate']})",
        flush=True,
    )
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
