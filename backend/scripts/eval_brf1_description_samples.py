"""BRF-1: five samples of the product description prompt, isolated selection.

    uv run python -m scripts.eval_brf1_description_samples

Same prompt as product descriptions, five independent samples (temperature 1.0
on generation only). Isolated one-document selection against each set at the
product complete() temperature. Does not call ask(). Does not rewrite the
lock. Network stays on loopback. Sample texts go under backend/out/ (gitignored).
"""

from __future__ import annotations

import hashlib
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

from app.document_describe import (  # noqa: E402
    apply_description_lock,
    description_prompt,
    description_set_version,
    document_text_from_pages,
    parse_description,
)
from app.full_corpus import server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import CASES, N_CTX, STORE_DIR, letters_for  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402
from scripts.query_expansion import (  # noqa: E402
    cumulative_union_counts,
    hit_spread,
    isolated_selection_prompt,
    parse_selected_document,
    per_set_hit_counts,
    picks_hit_ids,
    unique_text_counts,
)

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-description-samples"
HARD = ("R5", "R6", "R7", "R3b", "R7b")
HANDWRITTEN = ("R7", "R7b")
N_SETS = 5
SAMPLE_TEMPERATURE = 1.0


def dump(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def ordered_letters(letters: dict[str, str]) -> list[str]:
    return [letter for _doc_id, letter in sorted(letters.items(), key=lambda item: item[1])]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def select_one(provider, model: str, entries: list[tuple[str, str]], question: str) -> str | None:
    system, user = isolated_selection_prompt(entries, question)
    raw = provider.complete(system, user, max_tokens=96, model=model)
    return parse_selected_document(raw, {letter for letter, _desc in entries})


def complete_sampled(provider, system: str, user: str, *, max_tokens: int, model: str) -> str:
    """Eval-only: same payload as product complete(), temperature overwritten."""
    original_post = provider._client.post

    def post(url, **kwargs):
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["temperature"] = SAMPLE_TEMPERATURE
            kwargs = dict(kwargs)
            kwargs["json"] = payload
        return original_post(url, **kwargs)

    provider._client.post = post
    try:
        return provider.complete(system, user, max_tokens=max_tokens, model=model)
    finally:
        provider._client.post = original_post


def load_or_generate_set(
    index: int,
    *,
    store: Store,
    provider,
    model: str,
    letters_map: dict[str, str],
) -> dict[str, str]:
    path = OUT / f"set-{index}.json"
    if path.exists():
        payload = json.loads(path.read_text("utf-8"))
        texts = payload["texts"]
        print(f"reusing set {index} {path.name}", flush=True)
        return texts
    id_by_letter = {letter: doc_id for doc_id, letter in letters_map.items()}
    letters = ordered_letters(letters_map)
    texts: dict[str, str] = {}
    meta = []
    for letter in letters:
        doc_id = id_by_letter[letter]
        meta_doc = store.documents[doc_id]
        text = document_text_from_pages(store.pages[doc_id])
        system, user = description_prompt(meta_doc.name, text)
        t0 = time.perf_counter()
        raw = complete_sampled(provider, system, user, max_tokens=512, model=model)
        desc = parse_description(raw)
        elapsed = round(time.perf_counter() - t0, 3)
        texts[letter] = desc
        meta.append(
            {
                "letter": letter,
                "chars": len(desc),
                "empty": not desc,
                "hash": text_hash(desc) if desc else "",
                "elapsed_s": elapsed,
            }
        )
        print(
            f"set {index} {letter} chars={len(desc)} empty={not desc} {elapsed}s",
            flush=True,
        )
    if any(row["empty"] for row in meta):
        raise SystemExit(f"tom beskrivning i uppsättning {index}")
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"texts": texts, "generation": meta}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return texts


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    gold_by_id = {case["id"]: case["doc"] for case in spec}
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)

    store = Store(data_dir=STORE_DIR)
    lock = json.loads(LOCK_PATH.read_text("utf-8"))
    version = apply_description_lock(store, lock)
    version_before = description_set_version(store.documents)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    letters_map = letters_for(store)
    letters = ordered_letters(letters_map)

    n_lock_rewrites = 0
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        return original_complete(system, user, max_tokens=max_tokens, model=model)

    provider.complete = wrapped  # type: ignore[method-assign]

    state: dict = {
        "provider": provider.name,
        "model": model,
        "n_ctx": N_CTX,
        "lock_version": lock.get("version"),
        "description_version": version,
        "sample_temperature": SAMPLE_TEMPERATURE,
        "n_sets": N_SETS,
        "n_archive": len(store.documents),
        "sets": [],
        "external_connections": [],
    }
    dump(state)
    print(
        f"lock={version} letters={''.join(letters)} sample_temp={SAMPLE_TEMPERATURE}",
        flush=True,
    )

    texts_by_set: list[dict[str, str]] = []
    for index in range(1, N_SETS + 1):
        print(f"\n=== generate set {index}/{N_SETS} ===", flush=True)
        texts = load_or_generate_set(
            index,
            store=store,
            provider=provider,
            model=model,
            letters_map=letters_map,
        )
        missing = [letter for letter in letters if not texts.get(letter)]
        if missing:
            raise SystemExit(f"vyer saknas i uppsättning {index}: {missing}")
        texts_by_set.append(texts)
        state["sets"].append(
            {
                "index": index,
                "n_chars": {letter: len(texts[letter]) for letter in letters},
                "hashes": {letter: text_hash(texts[letter]) for letter in letters},
            }
        )
        dump(state)

    unique = unique_text_counts(texts_by_set)
    state["unique_texts_per_letter"] = unique
    dump(state)
    print(f"unika texter per handling {unique}", flush=True)

    picks_by_set: list[dict[str, str | None]] = []
    for index, texts in enumerate(texts_by_set, start=1):
        print(f"\n=== select set {index}/{N_SETS} ===", flush=True)
        entries = [(letter, texts[letter]) for letter in letters]
        picks: dict[str, str | None] = {}
        t0 = time.perf_counter()
        for case in spec:
            pick = select_one(provider, model, entries, case["question"])
            picks[case["id"]] = pick
            mark = "HIT" if pick == case["doc"] else "miss"
            print(
                f"set {index} {case['id']} pick={pick} gold={case['doc']} {mark}",
                flush=True,
            )
        print(f"set {index} select {time.perf_counter() - t0:.1f}s", flush=True)
        picks_by_set.append(picks)

    hits = per_set_hit_counts(picks_by_set, gold_by_id)
    union = cumulative_union_counts(picks_by_set, gold_by_id)
    spread = hit_spread(hits)
    per_set_rows = []
    acc: set[str] = set()
    for index, picks in enumerate(picks_by_set, start=1):
        hit_ids = picks_hit_ids(picks, gold_by_id)
        acc |= hit_ids
        per_set_rows.append(
            {
                "index": index,
                "hits": hits[index - 1],
                "hit_ids": sorted(hit_ids),
                "picks": picks,
                "cumulative_union": union[index - 1],
                "cumulative_ids": sorted(acc),
            }
        )
        state["sets"][index - 1]["hits"] = hits[index - 1]
        state["sets"][index - 1]["hit_ids"] = sorted(hit_ids)
        state["sets"][index - 1]["picks"] = picks
        state["sets"][index - 1]["cumulative_union"] = union[index - 1]
        state["sets"][index - 1]["cumulative_ids"] = sorted(acc)

    hard_rows = []
    for case in spec:
        if case["id"] not in HARD:
            continue
        hard_rows.append(
            {
                "id": case["id"],
                "gold": case["doc"],
                "handwritten": case["id"] in HANDWRITTEN,
                "picks": [picks[case["id"]] for picks in picks_by_set],
                "hit_in_any": any(picks[case["id"]] == case["doc"] for picks in picks_by_set),
            }
        )

    version_after = description_set_version(store.documents)
    state["selection"] = {
        "hits_per_set": hits,
        "spread": spread,
        "cumulative_union": union,
        "per_set": per_set_rows,
        "hard": hard_rows,
    }
    state["n_lock_rewrites"] = n_lock_rewrites
    state["lock_unchanged"] = version_after == version_before
    state["external_connections"] = [entry for entry in audit_log if not entry["allowed"]]
    dump(state)

    print(
        f"\nträff per uppsättning {hits}  spann {spread['min']}–{spread['max']} "
        f"(spread {spread['span']})",
        flush=True,
    )
    print(f"kumulativ union {union}", flush=True)
    print("hårda:", flush=True)
    for row in hard_rows:
        print(
            f"  {row['id']} gold={row['gold']} picks={row['picks']} "
            f"{'HIT' if row['hit_in_any'] else 'miss'}",
            flush=True,
        )
    if version_after != version_before:
        raise SystemExit("låset skrevs om under mätningen")
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
