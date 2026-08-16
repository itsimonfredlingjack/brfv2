"""Inspect packed prompts for BRF-1 R5, R7, R7b document-path refusals.

    uv run python -m scripts.eval_brf1_refusal_prompt

Calls ask() once per case with the product path. Records selected
documents, whether gold-page chunks are in the packed excerpts, and the
refusal. Does not change defaults. Writes letters and presence flags, not
archive prose.
"""

from __future__ import annotations

import json
import os
import sys
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
from app.document_ask import catalog_entries  # noqa: E402
from app.full_corpus import live_corpus_runtime, server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402
from scripts.eval_brf1_variance import letters_for  # noqa: E402
from scripts.measure_nctx_cost import wait_n_ctx  # noqa: E402

STORE_DIR = Path("/tmp/brf1-store")
CASES = Path("/tmp/brf1-cases/eleven.json")
OUT = backend / "out" / "brf1-refusal-prompt"
N_CTX = 65536
TARGET_IDS = ("R5", "R7", "R7b")
MARKERS = {
    "R5": ("administrationskostnad", "494"),
    "R7": ("varsko", "prisjustering"),
    "R7b": ("varsko", "prisjustering"),
}


def main() -> int:
    spec = {c["id"]: c for c in json.loads(CASES.read_text("utf-8"))["cases"]}
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    if not wait_n_ctx(origin, N_CTX, timeout_s=5):
        raise SystemExit(f"/props n_ctx is not {N_CTX}")
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)

    store = Store(data_dir=STORE_DIR)
    # Live store descriptions (product path). Do not inject the eval cache:
    # ask() → ensure_descriptions would rewrite them if the fingerprint is fake.
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    runtime = live_corpus_runtime()
    if runtime is None:
        raise SystemExit("no runtime")
    letters = letters_for(store)
    id_by_letter = {letter: doc_id for doc_id, letter in letters.items()}
    catalog = {meta.id: letter for letter, meta in catalog_entries(store.documents)}

    captured: list[dict] = []
    original_complete = provider.complete

    def wrapped(system: str, user: str, *, max_tokens: int, model: str) -> str:
        captured.append(
            {
                "is_describe": "Du beskriver vad en föreningshandling reglerar" in system,
                "is_selection": "Du väljer vilka handlingar" in system,
                "is_judge": system.startswith("Du är en domare."),
                "user": user,
            }
        )
        raw = original_complete(system, user, max_tokens=max_tokens, model=model)
        captured[-1]["raw"] = raw[:200]
        return raw

    provider.complete = wrapped  # type: ignore[method-assign]

    rows = []
    for cid in TARGET_IDS:
        case = spec[cid]
        captured.clear()
        gold_letter = case["doc"]
        gold_page = case["truth"][0][1]
        gold_id = id_by_letter[gold_letter]
        gold_chunks = [
            chunk
            for chunk in store.chunks.values()
            if chunk.document_id == gold_id and chunk.page == gold_page
        ]

        resp = ask(store, case["question"], provider=provider, corpus_runtime=runtime)
        synthesis = [
            c
            for c in captured
            if not c["is_selection"] and not c["is_judge"] and not c["is_describe"]
        ]
        describes = [c for c in captured if c["is_describe"]]
        selections = [c for c in captured if c["is_selection"]]
        excerpts = synthesis[0]["user"] if synthesis else ""

        packed: list[str] = []
        for hit in resp.retrieval:
            letter = letters.get(hit.document_id, "?")
            if letter not in packed:
                packed.append(letter)
        packed_catalog = [catalog.get(id_by_letter[letter], "?") for letter in packed if letter in id_by_letter]

        n_gold_chunks = len(gold_chunks)
        n_in_excerpts = sum(1 for chunk in gold_chunks if chunk.text in excerpts)
        markers = MARKERS[cid]
        folded = excerpts.casefold()
        marker_in_excerpts = [m for m in markers if m.casefold() in folded]

        row = {
            "id": cid,
            "gold": gold_letter,
            "gold_page": gold_page,
            "packed_name_letters": packed,
            "packed_catalog_letters": packed_catalog,
            "gold_in_pack": gold_letter in packed,
            "gold_page_chunks": n_gold_chunks,
            "gold_page_chunks_in_excerpts": n_in_excerpts,
            "gold_page_text_in_prompt": n_gold_chunks > 0 and n_in_excerpts == n_gold_chunks,
            "markers_in_excerpts": marker_in_excerpts,
            "refusal": bool(resp.refusal),
            "refusal_reason": resp.refusal_reason,
            "cited": [letters.get(c.document_id, "?") for c in resp.citations],
            "n_describe_calls": len(describes),
            "n_selection_calls": len(selections),
            "n_synthesis_calls": len(synthesis),
            "selection_raw": selections[-1]["raw"] if selections else None,
            "excerpt_chars": len(excerpts),
        }
        rows.append(row)
        print(
            f"{cid} packed={packed} gold_in_pack={row['gold_in_pack']} "
            f"page_chunks={n_in_excerpts}/{n_gold_chunks} markers={marker_in_excerpts} "
            f"describe={len(describes)} reason={resp.refusal_reason}",
            flush=True,
        )

    payload = {
        "rows": rows,
        "external_connections": [e for e in audit_log if not e["allowed"]],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if payload["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
