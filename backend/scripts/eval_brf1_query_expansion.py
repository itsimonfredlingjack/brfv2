"""BRF-1: measure doc2query and query2doc separately on the eleven cases.

    uv run python -m scripts.eval_brf1_query_expansion

Does not call ask(). Does not change the product answer path. Descriptions
stay locked. Network stays on loopback. Generated questions and passages
are written under backend/out/ (gitignored), not into the evidence file.
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
from scripts.eval_brf1_variance import CASES, N_CTX, STORE_DIR, letters_for  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402
from scripts.query_expansion import (  # noqa: E402
    DOC2QUERY_N,
    QUERY2DOC_REPEATS,
    concatenate_query2doc,
    doc2query_prompt,
    expand_document_text,
    fit_document_bm25,
    index_growth,
    isolated_selection_prompt,
    parse_passage,
    parse_questions,
    parse_selected_document,
    query2doc_prompt,
    rank_letters,
    token_contains,
)

LOCK_PATH = backend / "eval" / "brf1-descriptions.lock.json"
OUT = backend / "out" / "brf1-query-expansion"
HARD = ("R5", "R6", "R7", "R3b", "R7b")
PROBES = {
    "R5": ["extra", "avgift", "stena", "fakturorna"],
    "R6": ["kostnaderna", "föreningen", "betala"],
    "R7": ["stena", "höjer", "priset"],
    "R3b": ["kostnaden", "bil", "skada", "gården"],
    "R7b": ["leverantören", "höja", "priset", "meddela"],
}


def dump(name: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def ordered_letters(letters: dict[str, str]) -> list[str]:
    return [letter for _doc_id, letter in sorted(letters.items(), key=lambda item: item[1])]


def full_document_text(pages) -> str:
    return "\n".join(" ".join(word.text for word in page.words) for page in pages)


def probe_map(text: str, terms: list[str]) -> dict[str, bool]:
    return {term: token_contains(text, term) for term in terms}


def bm25_rows(spec: list[dict], bm25, letters: list[str], query_of) -> list[dict]:
    rows = []
    for case in spec:
        ranked = rank_letters(bm25, query_of(case), letters)
        gold = case["doc"]
        rank = ranked.index(gold) + 1 if gold in ranked else None
        rows.append(
            {
                "id": case["id"],
                "gold": gold,
                "top": ranked[0],
                "ranked": ranked,
                "gold_rank": rank,
                "hit": ranked[0] == gold,
                "hard": case["id"] in HARD,
            }
        )
    return rows


def hits_of(rows: list[dict]) -> int:
    return sum(1 for row in rows if row["hit"])


def print_bm25(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===", flush=True)
    for row in rows:
        mark = "HIT" if row["hit"] else "miss"
        print(
            f"{row['id']} gold={row['gold']} top={row['top']} "
            f"rank={row['gold_rank']} {mark}",
            flush=True,
        )
    print(f"hits {hits_of(rows)}/{len(rows)}", flush=True)


def print_desc(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===", flush=True)
    for row in rows:
        mark = "HIT" if row["hit"] else "miss"
        print(
            f"{row['id']} gold={row['gold']} pick={row['pick']} {mark}",
            flush=True,
        )
    print(f"hits {hits_of(rows)}/{len(rows)}", flush=True)


def select_one(provider, model: str, entries: list[tuple[str, str]], question: str) -> str | None:
    system, user = isolated_selection_prompt(entries, question)
    raw = provider.complete(system, user, max_tokens=96, model=model)
    return parse_selected_document(raw, {letter for letter, _desc in entries})


def desc_rows(spec, provider, model, entries) -> list[dict]:
    rows = []
    for case in spec:
        pick = select_one(provider, model, entries, case["question"])
        gold = case["doc"]
        rows.append(
            {
                "id": case["id"],
                "gold": gold,
                "pick": pick,
                "hit": pick == gold,
                "hard": case["id"] in HARD,
            }
        )
        print(
            f"desc {case['id']} pick={pick} gold={gold} "
            f"{'HIT' if pick == gold else 'miss'}",
            flush=True,
        )
    return rows


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
    lock = json.loads(LOCK_PATH.read_text("utf-8"))
    version = apply_description_lock(store, lock)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    letters_map = letters_for(store)
    letters = ordered_letters(letters_map)
    id_by_letter = {letter: doc_id for doc_id, letter in letters_map.items()}
    texts = [full_document_text(store.pages[id_by_letter[letter]]) for letter in letters]
    entries = [
        (letter, store.documents[id_by_letter[letter]].description or "")
        for letter in letters
    ]
    if any(not description for _letter, description in entries):
        raise SystemExit("låsta beskrivningar saknas")

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
        "n_archive": len(store.documents),
        "doc2query_n_requested": DOC2QUERY_N,
        "query2doc_repeats_bm25": QUERY2DOC_REPEATS,
        "query2doc_repeats_desc": 1,
        "n_describe_calls": 0,
        "external_connections": [],
    }
    dump("result.json", state)
    print(
        f"descriptions version={version} lock={lock.get('version')} "
        f"n_archive={len(store.documents)} letters={''.join(letters)}",
        flush=True,
    )

    bm25_base = fit_document_bm25(texts)
    baseline_bm25 = bm25_rows(spec, bm25_base, letters, lambda case: case["question"])
    print_bm25("BM25 före (baslinje)", baseline_bm25)
    state["bm25_baseline"] = {"hits": hits_of(baseline_bm25), "rows": baseline_bm25}
    dump("result.json", state)

    print("\n=== beskrivningsurval före (låsta texter, en handling) ===", flush=True)
    t0 = time.perf_counter()
    baseline_desc = desc_rows(spec, provider, model, entries)
    print(
        f"hits {hits_of(baseline_desc)}/{len(baseline_desc)} "
        f"{time.perf_counter() - t0:.1f}s",
        flush=True,
    )
    state["desc_baseline"] = {"hits": hits_of(baseline_desc), "rows": baseline_desc}
    dump("result.json", state)

    print(f"\n=== doc2query generation ({DOC2QUERY_N} frågor / handling) ===", flush=True)
    questions_by_letter: dict[str, list[str]] = {}
    gen_meta = []
    for letter, text in zip(letters, texts, strict=True):
        system, user = doc2query_prompt(text, n=DOC2QUERY_N)
        t1 = time.perf_counter()
        raw = provider.complete(system, user, max_tokens=1024, model=model)
        questions = parse_questions(raw)
        elapsed = round(time.perf_counter() - t1, 3)
        questions_by_letter[letter] = questions
        gen_meta.append(
            {
                "letter": letter,
                "n_questions": len(questions),
                "elapsed_s": elapsed,
            }
        )
        print(f"doc2query {letter} n={len(questions)} {elapsed}s", flush=True)
    expanded_texts = [
        expand_document_text(text, questions_by_letter[letter])
        for letter, text in zip(letters, texts, strict=True)
    ]
    growth = index_growth(texts, expanded_texts)
    for row, letter in zip(growth["per_document"], letters, strict=True):
        row["letter"] = letter
        row["n_questions"] = len(questions_by_letter[letter])
    state["doc2query_generation"] = {
        "per_document": gen_meta,
        "growth": growth,
    }
    dump("generations.json", {"questions": questions_by_letter})
    dump("result.json", state)

    bm25_d2q = fit_document_bm25(expanded_texts)
    doc2query_bm25 = bm25_rows(spec, bm25_d2q, letters, lambda case: case["question"])
    print_bm25("BM25 efter doc2query", doc2query_bm25)
    state["bm25_doc2query"] = {"hits": hits_of(doc2query_bm25), "rows": doc2query_bm25}
    dump("result.json", state)

    print("\n=== query2doc generation ===", flush=True)
    passages: dict[str, str] = {}
    passage_meta = []
    for case in spec:
        system, user = query2doc_prompt(case["question"])
        t1 = time.perf_counter()
        raw = provider.complete(system, user, max_tokens=256, model=model)
        passage = parse_passage(raw)
        elapsed = round(time.perf_counter() - t1, 3)
        passages[case["id"]] = passage
        passage_meta.append(
            {
                "id": case["id"],
                "n_chars": len(passage),
                "elapsed_s": elapsed,
            }
        )
        print(f"query2doc {case['id']} chars={len(passage)} {elapsed}s", flush=True)
    dump("generations.json", {"questions": questions_by_letter, "passages": passages})
    state["query2doc_generation"] = {"per_case": passage_meta}
    dump("result.json", state)

    def q2d_bm25_query(case: dict) -> str:
        return concatenate_query2doc(case["question"], passages[case["id"]])

    query2doc_bm25 = bm25_rows(spec, bm25_base, letters, q2d_bm25_query)
    print_bm25("BM25 efter query2doc (ursprungligt index)", query2doc_bm25)
    state["bm25_query2doc"] = {"hits": hits_of(query2doc_bm25), "rows": query2doc_bm25}
    dump("result.json", state)

    print("\n=== beskrivningsurval efter query2doc (fråga + stycke, en gång) ===", flush=True)
    t0 = time.perf_counter()
    q2d_desc_rows = []
    for case in spec:
        question = concatenate_query2doc(
            case["question"], passages[case["id"]], repeats=1
        )
        pick = select_one(provider, model, entries, question)
        gold = case["doc"]
        row = {
            "id": case["id"],
            "gold": gold,
            "pick": pick,
            "hit": pick == gold,
            "hard": case["id"] in HARD,
        }
        q2d_desc_rows.append(row)
        print(
            f"desc-q2d {case['id']} pick={pick} gold={gold} "
            f"{'HIT' if pick == gold else 'miss'}",
            flush=True,
        )
    print(
        f"hits {hits_of(q2d_desc_rows)}/{len(q2d_desc_rows)} "
        f"{time.perf_counter() - t0:.1f}s",
        flush=True,
    )
    state["desc_query2doc"] = {"hits": hits_of(q2d_desc_rows), "rows": q2d_desc_rows}
    dump("result.json", state)

    both_give = hits_of(doc2query_bm25) > 0 and hits_of(query2doc_bm25) > 0
    state["combined_ran"] = both_give
    if both_give:
        combined = bm25_rows(spec, bm25_d2q, letters, q2d_bm25_query)
        print_bm25("BM25 doc2query + query2doc", combined)
        d2q_ids = {row["id"] for row in doc2query_bm25 if row["hit"]}
        q2d_ids = {row["id"] for row in query2doc_bm25 if row["hit"]}
        comb_ids = {row["id"] for row in combined if row["hit"]}
        state["bm25_combined"] = {
            "hits": hits_of(combined),
            "rows": combined,
            "doc2query_only": sorted(d2q_ids - q2d_ids),
            "query2doc_only": sorted(q2d_ids - d2q_ids),
            "both": sorted(d2q_ids & q2d_ids),
            "union": sorted(d2q_ids | q2d_ids),
            "combined_hits": sorted(comb_ids),
            "added": sorted(comb_ids - (d2q_ids | q2d_ids)),
            "lost": sorted((d2q_ids | q2d_ids) - comb_ids),
        }
        print(
            f"överlapp båda={state['bm25_combined']['both']} "
            f"bara_d2q={state['bm25_combined']['doc2query_only']} "
            f"bara_q2d={state['bm25_combined']['query2doc_only']} "
            f"adderade={state['bm25_combined']['added']} "
            f"förlorade={state['bm25_combined']['lost']}",
            flush=True,
        )
    else:
        print("\ncombined hoppades över: minst en BM25-kanal var 0", flush=True)
        state["bm25_combined"] = None
    dump("result.json", state)

    gold_text = {letter: text for letter, text in zip(letters, texts, strict=True)}
    probes = {}
    for case in spec:
        if case["id"] not in PROBES:
            continue
        gold = case["doc"]
        questions = questions_by_letter[gold]
        passage = passages[case["id"]]
        probes[case["id"]] = {
            "gold": gold,
            "in_gold_text": probe_map(gold_text[gold], PROBES[case["id"]]),
            "in_gold_questions": probe_map("\n".join(questions), PROBES[case["id"]]),
            "in_query2doc_passage": probe_map(passage, PROBES[case["id"]]),
        }
    state["probes"] = probes
    state["n_describe_calls"] = n_describe_calls
    state["external_connections"] = [entry for entry in audit_log if not entry["allowed"]]
    dump("result.json", state)

    print("\n=== hårda fall, tokenprober (frågans ord, inte handlingstext) ===", flush=True)
    for case_id, row in probes.items():
        print(f"{case_id} gold={row['gold']}", flush=True)
        print(f"  i facittext {row['in_gold_text']}", flush=True)
        print(f"  i doc2query  {row['in_gold_questions']}", flush=True)
        print(f"  i query2doc  {row['in_query2doc_passage']}", flush=True)

    print(
        f"\nBM25  före {state['bm25_baseline']['hits']}/11  "
        f"doc2query {state['bm25_doc2query']['hits']}/11  "
        f"query2doc {state['bm25_query2doc']['hits']}/11",
        flush=True,
    )
    print(
        f"desc  före {state['desc_baseline']['hits']}/11  "
        f"query2doc {state['desc_query2doc']['hits']}/11",
        flush=True,
    )
    print(
        f"index tokens {growth['tokens_before']} → {growth['tokens_after']} "
        f"(+{growth['tokens_added']})",
        flush=True,
    )

    if n_describe_calls:
        raise SystemExit(f"beskrivningar skrevs om under mätningen: {n_describe_calls}")
    if state["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
