"""BRF-1: two independent description views, union selection, full ask path.

    uv run python -m scripts.eval_brf1_union_select

Generates two standalone description views per document with different
prompts. Runs isolated one-document selection against each view, packs the
union under today's n_ctx token cap, then ask(). Five runs of the eleven
cases. Does not rewrite the product lock. Network stays on loopback.
Generated views go under backend/out/ (gitignored).
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

import app.answer as answer_mod  # noqa: E402
from app.answer import ask  # noqa: E402
from app.document_ask import DocumentScore, PackDecision, pack_documents  # noqa: E402
from app.document_describe import apply_description_lock, parse_description  # noqa: E402
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
from scripts.query_expansion import (  # noqa: E402
    gold_in_package,
    isolated_selection_prompt,
    parse_selected_document,
    union_selected_ids,
    view_fragor_prompt,
    view_reglerar_prompt,
)

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-union-select"
HARD = ("R5", "R6", "R7", "R3b", "R7b")
HANDWRITTEN = ("R7", "R7b")
PACK_LOG: list[dict] = []
LAST_SELECT: dict = {}


def dump(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def ordered_letters(letters: dict[str, str]) -> list[str]:
    return [letter for _doc_id, letter in sorted(letters.items(), key=lambda item: item[1])]


def full_document_text(pages) -> str:
    return "\n".join(" ".join(word.text for word in page.words) for page in pages)


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


def as_letters(ids: list[str], letters: dict[str, str]) -> list[str]:
    out: list[str] = []
    for doc_id in ids:
        letter = letters.get(doc_id, "?")
        if letter not in out:
            out.append(letter)
    return out


def select_one(provider, model: str, entries: list[tuple[str, str]], question: str) -> str | None:
    system, user = isolated_selection_prompt(entries, question)
    raw = provider.complete(system, user, max_tokens=96, model=model)
    return parse_selected_document(raw, {letter for letter, _desc in entries})


def load_or_generate_views(
    store: Store,
    provider,
    model: str,
    letters_map: dict[str, str],
) -> dict:
    path = OUT / "views.json"
    if path.exists():
        payload = json.loads(path.read_text("utf-8"))
        print(f"reusing views {path}", flush=True)
        return payload
    id_by_letter = {letter: doc_id for doc_id, letter in letters_map.items()}
    letters = ordered_letters(letters_map)
    reglerar: dict[str, str] = {}
    fragor: dict[str, str] = {}
    meta = []
    for letter in letters:
        text = full_document_text(store.pages[id_by_letter[letter]])
        row = {"letter": letter, "empty": []}
        for name, prompt_fn, bucket in (
            ("reglerar", view_reglerar_prompt, reglerar),
            ("fragor", view_fragor_prompt, fragor),
        ):
            system, user = prompt_fn(text)
            t0 = time.perf_counter()
            raw = provider.complete(system, user, max_tokens=512, model=model)
            desc = parse_description(raw)
            elapsed = round(time.perf_counter() - t0, 3)
            bucket[letter] = desc
            if not desc:
                row["empty"].append(name)
            row[f"{name}_chars"] = len(desc)
            row[f"{name}_s"] = elapsed
            print(
                f"view {letter}/{name} chars={len(desc)} empty={not desc} {elapsed}s",
                flush=True,
            )
        meta.append(row)
    payload = {"reglerar": reglerar, "fragor": fragor, "generation": meta}
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if any(row["empty"] for row in meta):
        raise SystemExit(f"tom vy: {meta}")
    return payload


def install_union_path(
    *,
    view_a: dict[str, str],
    view_b: dict[str, str],
    letters_map: dict[str, str],
) -> None:
    id_by_letter = {letter: doc_id for doc_id, letter in letters_map.items()}
    letters = ordered_letters(letters_map)
    entries_a = [(letter, view_a[letter]) for letter in letters]
    entries_b = [(letter, view_b[letter]) for letter in letters]

    def union_evaluate_document_path(
        *,
        question: str,
        index,
        chunks,
        documents,
        runtime,
        settings,
        provider,
        store=None,
    ) -> PackDecision:
        _ = index
        docs = dict(store.documents) if store is not None else dict(documents)
        model = getattr(provider, "model", "") or settings.aiModel
        pick_a = select_one(provider, model, entries_a, question)
        pick_b = select_one(provider, model, entries_b, question)
        union_letters = union_selected_ids(
            [pick_a] if pick_a else [],
            [pick_b] if pick_b else [],
        )
        picked_ids = [id_by_letter[letter] for letter in union_letters if letter in id_by_letter]
        LAST_SELECT.clear()
        LAST_SELECT.update(
            {
                "a": pick_a,
                "b": pick_b,
                "union": union_letters,
                "ids": picked_ids,
            }
        )
        if not picked_ids:
            return PackDecision(False, "no_selection", [], [], None)
        scores = [
            DocumentScore(
                document_id=doc_id,
                document_name=docs[doc_id].name if doc_id in docs else doc_id,
                max_score=1.0 - i * 0.01,
                n_matching_chunks=1,
            )
            for i, doc_id in enumerate(picked_ids)
            if doc_id in docs
        ]
        return pack_documents(
            scores=scores,
            chunks=chunks,
            documents=docs,
            runtime=runtime,
            system=answer_mod._system_prompt(settings),
            n_ctx=runtime.n_ctx(),
            response_budget=settings.maxResponseLength + answer_mod._CITATION_HEADROOM_TOKENS,
            threshold=None,
        )

    answer_mod.evaluate_document_path = union_evaluate_document_path  # type: ignore[method-assign]


def summarize(rows: list[dict]) -> dict:
    per_run: list[Counter] = []
    gold_pack_per_run: list[int] = []
    for run in range(1, RUNS + 1):
        run_rows = [r for r in rows if r["run"] == run]
        per_run.append(Counter(r["three"] for r in run_rows))
        gold_pack_per_run.append(sum(1 for r in run_rows if r["gold_in_pack"]))
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
        prefixes = [r["prefix_tokens"] for r in case_rows if r["prefix_tokens"] is not None]
        by_case[case_id] = {
            "verifierat_i_facit": counts["verifierat_i_facit"],
            "verifierat_i_fel_handling": counts["verifierat_i_fel_handling"],
            "vägrad": counts["vägrad"],
            "outcomes": [r["three"] for r in case_rows],
            "gold_in_pack": sum(1 for r in case_rows if r["gold_in_pack"]),
            "gold_in_union": sum(1 for r in case_rows if r["gold_in_union"]),
            "n_packed": packed_counts,
            "n_packed_span": [min(packed_counts), max(packed_counts)] if packed_counts else None,
            "prefix_tokens": prefixes,
            "prefix_span": [min(prefixes), max(prefixes)] if prefixes else None,
            "selected_a": [r["selected_a"] for r in case_rows],
            "selected_b": [r["selected_b"] for r in case_rows],
            "packed": case_rows[0]["packed"] if case_rows else [],
        }
    packed_all = [r["n_packed"] for r in rows]
    prefixes_all = [r["prefix_tokens"] for r in rows if r["prefix_tokens"] is not None]
    return {
        "path": "union-select",
        "runs": RUNS,
        "n_cases": 11,
        "gold_in_pack_per_run": gold_pack_per_run,
        "gold_in_pack_span": (
            [min(gold_pack_per_run), max(gold_pack_per_run)] if gold_pack_per_run else None
        ),
        "facit_per_run": facit,
        "fel_per_run": fel,
        "vagrad_per_run": vag,
        "facit_span": [min(facit), max(facit)] if facit else None,
        "fel_span": [min(fel), max(fel)] if fel else None,
        "vagrad_span": [min(vag), max(vag)] if vag else None,
        "n_packed_span": [min(packed_all), max(packed_all)] if packed_all else None,
        "prefix_span": [min(prefixes_all), max(prefixes_all)] if prefixes_all else None,
        "by_case": by_case,
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
    letters_map = letters_for(store)
    letters = ordered_letters(letters_map)
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    n_archive = len(store.documents)

    n_describe_calls = 0
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        nonlocal n_describe_calls
        if "Du beskriver vad en föreningshandling reglerar" in system:
            n_describe_calls += 1
        return original_complete(system, user, max_tokens=max_tokens, model=model)

    provider.complete = wrapped  # type: ignore[method-assign]

    result_path = OUT / "result.json"
    if result_path.exists():
        state = json.loads(result_path.read_text("utf-8"))
        print(f"resuming {len(state.get('rows', []))} rows", flush=True)
    else:
        state = {
            "provider": provider.name,
            "model": model,
            "description_version": version,
            "lock_version": lock.get("version"),
            "n_archive": n_archive,
            "n_ctx": N_CTX,
            "runs": RUNS,
            "rows": [],
            "n_describe_calls": 0,
            "external_connections": [],
        }

    print(
        f"lock={version} letters={''.join(letters)} n_archive={n_archive}",
        flush=True,
    )
    views = load_or_generate_views(store, provider, model, letters_map)
    state["view_generation"] = views.get("generation")
    dump(state)
    missing = [
        letter
        for letter in letters
        if not views["reglerar"].get(letter) or not views["fragor"].get(letter)
    ]
    if missing:
        raise SystemExit(f"vyer saknas: {missing}")

    install_union_path(
        view_a=views["reglerar"],
        view_b=views["fragor"],
        letters_map=letters_map,
    )
    done = {(row["run"], row["id"]) for row in state["rows"]}

    try:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": None})
        )
        for run in range(1, RUNS + 1):
            print(f"\n=== run {run}/{RUNS} path=union-select ===", flush=True)
            for case in spec:
                if (run, case["id"]) in done:
                    continue
                gold = case["doc"]
                PACK_LOG.clear()
                LAST_SELECT.clear()
                t0 = time.perf_counter()
                resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
                elapsed = time.perf_counter() - t0
                packed = as_letters(
                    [hit.document_id for hit in resp.retrieval],
                    letters_map,
                )
                pick_a = LAST_SELECT.get("a")
                pick_b = LAST_SELECT.get("b")
                union_letters = LAST_SELECT.get("union") or []
                pack_meta = PACK_LOG[-1] if PACK_LOG else {}
                cited = [letters_map.get(c.document_id, "?") for c in resp.citations]
                row = {
                    "run": run,
                    "path": "union-select",
                    "id": case["id"],
                    "gold": gold,
                    "hard": case["id"] in HARD,
                    "handwritten": case["id"] in HANDWRITTEN,
                    "three": three_outcome(resp, gold, letters_map),
                    "display": display_of(resp),
                    "refusal": bool(resp.refusal),
                    "refusal_reason": resp.refusal_reason,
                    "warning": resp.warning,
                    "cited": cited,
                    "selected_a": pick_a,
                    "selected_b": pick_b,
                    "selected_union": union_letters,
                    "packed": packed,
                    "n_packed": len(packed),
                    "n_union": len(union_letters),
                    "gold_in_a": pick_a == gold,
                    "gold_in_b": pick_b == gold,
                    "gold_in_union": gold_in_package(gold, union_letters),
                    "gold_in_pack": gold_in_package(gold, packed),
                    "pack_bound": pack_meta.get("bound"),
                    "prefix_tokens": pack_meta.get("prefix_tokens"),
                    "log_n_docs": pack_meta.get("n_docs"),
                    "elapsed_s": round(elapsed, 3),
                }
                state["rows"].append(row)
                state["n_describe_calls"] = n_describe_calls
                dump(state)
                mark = "facit-pack" if row["gold_in_pack"] else "miss-pack"
                print(
                    f"r{run} {case['id']} {row['three']} {mark} "
                    f"a={pick_a} b={pick_b} packed={packed} "
                    f"n={row['n_packed']} prefix={row['prefix_tokens']} "
                    f"cited={cited} {row['elapsed_s']}s",
                    flush=True,
                )
    finally:
        store.update_settings(
            store.settings.model_copy(update={"fullCorpusTokenThreshold": original_threshold})
        )

    state["n_describe_calls"] = n_describe_calls
    if n_describe_calls:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {n_describe_calls}")

    state["documents"] = summarize(state["rows"])
    state["external_connections"] = [entry for entry in audit_log if not entry["allowed"]]
    dump(state)
    summary = state["documents"]
    print(
        f"\nfacit i paketet {summary['gold_in_pack_span'][0]}–"
        f"{summary['gold_in_pack_span'][1]} av 11 "
        f"(per körning {summary['gold_in_pack_per_run']})",
        flush=True,
    )
    print(
        f"verifierat_i_facit {summary['facit_span'][0]}–{summary['facit_span'][1]} av 11 "
        f"(per körning {summary['facit_per_run']})",
        flush=True,
    )
    print(
        f"verifierat_i_fel_handling {summary['fel_span'][0]}–{summary['fel_span'][1]} "
        f"(per körning {summary['fel_per_run']})",
        flush=True,
    )
    print(
        f"n_packed {summary['n_packed_span'][0]}–{summary['n_packed_span'][1]} "
        f"prefix {summary['prefix_span'][0]}–{summary['prefix_span'][1]}",
        flush=True,
    )
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
