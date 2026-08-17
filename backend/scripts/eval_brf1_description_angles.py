"""BRF-1: description-set union and four-angle selection.

    uv run python -m scripts.eval_brf1_description_angles

Does not call ask(). Does not change the product answer path. The locked
description set is not rewritten. Network stays on loopback. Generated
four-angle texts go under backend/out/ (gitignored).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

backend = Path(__file__).resolve().parent.parent
os.chdir(backend)
sys.path.insert(0, str(backend))

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("BRF_LLM", "selfhosted")
os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")
os.environ["BRF_PREFIX_WARMUP"] = "0"
os.environ.pop("BRF_PLANNED_ASK", None)

from app.document_describe import apply_description_lock  # noqa: E402
from app.full_corpus import server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import CASES, DESC_CACHE, N_CTX, STORE_DIR, letters_for  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402
from scripts.query_expansion import (  # noqa: E402
    four_angle_prompt,
    four_angle_selection_prompt,
    parse_four_angles,
    parse_selected_document,
    isolated_selection_prompt,
    union_case,
    union_summary,
)

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-description-angles"
HARD = ("R5", "R6", "R7", "R3b", "R7b")


def dump(name: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def ordered_letters(letters: dict[str, str]) -> list[str]:
    return [letter for _doc_id, letter in sorted(letters.items(), key=lambda item: item[1])]


def full_document_text(pages) -> str:
    return "\n".join(" ".join(word.text for word in page.words) for page in pages)


def select_one(provider, model: str, entries: list[tuple[str, str]], question: str) -> str | None:
    system, user = isolated_selection_prompt(entries, question)
    raw = provider.complete(system, user, max_tokens=96, model=model)
    return parse_selected_document(raw, {letter for letter, _desc in entries})


def select_four(provider, model: str, entries: list[tuple[str, dict]], question: str) -> str | None:
    system, user = four_angle_selection_prompt(entries, question)
    raw = provider.complete(system, user, max_tokens=96, model=model)
    return parse_selected_document(raw, {letter for letter, _angles in entries})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)

    if not DESC_CACHE.exists():
        raise SystemExit(f"gamla beskrivningar saknas: {DESC_CACHE}")
    old_cache = json.loads(DESC_CACHE.read_text("utf-8"))
    old_by_letter = {entry["letter"]: entry["description"] for entry in old_cache["entries"]}

    store = Store(data_dir=STORE_DIR)
    lock = json.loads(LOCK_PATH.read_text("utf-8"))
    version = apply_description_lock(store, lock)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    letters_map = letters_for(store)
    letters = ordered_letters(letters_map)
    id_by_letter = {letter: doc_id for doc_id, letter in letters_map.items()}
    if any(letter not in old_by_letter for letter in letters):
        raise SystemExit("gamla beskrivningar täcker inte namnordningen")
    old_entries = [(letter, old_by_letter[letter]) for letter in letters]
    new_entries = [
        (letter, store.documents[id_by_letter[letter]].description or "")
        for letter in letters
    ]
    if any(not text for _letter, text in old_entries + new_entries):
        raise SystemExit("tom beskrivning i gammal eller ny uppsättning")

    n_describe_calls = 0
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        nonlocal n_describe_calls
        if "Du beskriver vad en föreningshandling reglerar" in system:
            n_describe_calls += 1
        return original_complete(system, user, max_tokens=max_tokens, model=model)

    provider.complete = wrapped  # type: ignore[method-assign]

    state: dict = {
        "provider": provider.name,
        "model": model,
        "n_ctx": N_CTX,
        "description_version": version,
        "lock_version": lock.get("version"),
        "old_cache": str(DESC_CACHE),
        "n_archive": len(store.documents),
        "n_describe_calls": 0,
        "external_connections": [],
    }
    dump("result.json", state)
    print(
        f"lock={version} old_cache={DESC_CACHE.name} letters={''.join(letters)}",
        flush=True,
    )

    print("\n=== 1. union: gamla beskrivningar ===", flush=True)
    old_picks: dict[str, str | None] = {}
    t0 = time.perf_counter()
    for case in spec:
        pick = select_one(provider, model, old_entries, case["question"])
        old_picks[case["id"]] = pick
        mark = "HIT" if pick == case["doc"] else "miss"
        print(f"old {case['id']} pick={pick} gold={case['doc']} {mark}", flush=True)
    print(f"old done {time.perf_counter() - t0:.1f}s", flush=True)

    print("\n=== 1. union: låsta beskrivningar 97b4e7bfc71f ===", flush=True)
    new_picks: dict[str, str | None] = {}
    t0 = time.perf_counter()
    for case in spec:
        pick = select_one(provider, model, new_entries, case["question"])
        new_picks[case["id"]] = pick
        mark = "HIT" if pick == case["doc"] else "miss"
        print(f"new {case['id']} pick={pick} gold={case['doc']} {mark}", flush=True)
    print(f"new done {time.perf_counter() - t0:.1f}s", flush=True)

    union_rows = [
        union_case(case["id"], case["doc"], old_picks[case["id"]], new_picks[case["id"]])
        for case in spec
    ]
    summary = union_summary(union_rows)
    state["union"] = {"summary": summary, "rows": union_rows}
    dump("result.json", state)
    print(
        f"\nunion old {summary['old']}/{summary['n']}  "
        f"new {summary['new']}/{summary['n']}  "
        f"minst en {summary['union']}/{summary['n']}",
        flush=True,
    )
    print("hårda:", flush=True)
    for row in union_rows:
        if row["id"] in HARD:
            print(
                f"  {row['id']} gold={row['gold']} old={row['old']} "
                f"new={row['new']} union={row['hit_union']}",
                flush=True,
            )

    print("\n=== 2. fyra vinklar: generation ===", flush=True)
    angles_by_letter: dict[str, dict[str, str]] = {}
    gen_meta = []
    for letter in letters:
        text = full_document_text(store.pages[id_by_letter[letter]])
        system, user = four_angle_prompt(text)
        t1 = time.perf_counter()
        raw = provider.complete(system, user, max_tokens=768, model=model)
        angles = parse_four_angles(raw)
        elapsed = round(time.perf_counter() - t1, 3)
        angles_by_letter[letter] = angles
        empty = [key for key, value in angles.items() if not value]
        gen_meta.append(
            {
                "letter": letter,
                "n_chars": {key: len(value) for key, value in angles.items()},
                "empty": empty,
                "elapsed_s": elapsed,
            }
        )
        print(
            f"angles {letter} empty={empty or '—'} "
            f"chars={gen_meta[-1]['n_chars']} {elapsed}s",
            flush=True,
        )
    dump("angles.json", {"angles": angles_by_letter})
    state["four_angle_generation"] = {"per_document": gen_meta}
    dump("result.json", state)
    if any(row["empty"] for row in gen_meta):
        raise SystemExit("tom fyravinkelbeskrivning")

    angle_entries = [(letter, angles_by_letter[letter]) for letter in letters]
    print("\n=== 2. fyra vinklar: urval ===", flush=True)
    angle_rows = []
    t0 = time.perf_counter()
    for case in spec:
        pick = select_four(provider, model, angle_entries, case["question"])
        gold = case["doc"]
        row = {
            "id": case["id"],
            "gold": gold,
            "pick": pick,
            "hit": pick == gold,
            "hard": case["id"] in HARD,
        }
        angle_rows.append(row)
        mark = "HIT" if row["hit"] else "miss"
        print(f"angles {case['id']} pick={pick} gold={gold} {mark}", flush=True)
    n_hits = sum(1 for row in angle_rows if row["hit"])
    print(f"four-angle hits {n_hits}/{len(angle_rows)} {time.perf_counter() - t0:.1f}s", flush=True)
    state["four_angle_selection"] = {"hits": n_hits, "rows": angle_rows}
    state["n_describe_calls"] = n_describe_calls
    state["external_connections"] = [entry for entry in audit_log if not entry["allowed"]]
    dump("result.json", state)

    print("\nhårda fyravinkel:", flush=True)
    for row in angle_rows:
        if row["id"] in HARD:
            print(
                f"  {row['id']} gold={row['gold']} pick={row['pick']} "
                f"{'HIT' if row['hit'] else 'miss'}",
                flush=True,
            )

    if n_describe_calls:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {n_describe_calls}")
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
