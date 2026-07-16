"""Eval harness — run after every significant change (SPEC §6).

Usage:
    uv run python -m scripts.eval                    # full eval (real LLM)
    uv run python -m scripts.eval --retrieval-only   # fast, no LLM
    uv run python -m scripts.eval --sweep            # knob sweep (no LLM)
    uv run python -m scripts.eval --settings '{"searchWeighting": 100}'
    uv run python -m scripts.eval --limit 10

Gates (full eval): recall@k ≥ 0.85 · citation_verification ≥ 0.90 ·
highlight_correctness ≥ 0.90 · false_answer_rate = 0.00
Exit code 1 if any gate fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import ask  # noqa: E402
from app.normalize import find_spans  # noqa: E402
from app.schemas import Settings  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.seed import seed_store  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def install_network_audit() -> tuple[list, set]:
    """Instrument every TCP connect from this process. Connections are allowed
    only to loopback and to the configured self-hosted LLM endpoint; anything
    else raises immediately and is recorded. Returns (log, allowed_hosts).

    Scope: audits connect() calls made by this Python process (httpx, sockets).
    System-resolver DNS lookups happen in libc and are not connections to
    document-data endpoints; embeddings load offline (HF_HUB_OFFLINE=1).
    """
    import socket
    import urllib.parse

    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    base = os.environ.get("BRF_LLM_BASE_URL", "")
    if base:
        host = urllib.parse.urlparse(base).hostname
        if host:
            allowed_hosts.add(host)
            try:
                for info in socket.getaddrinfo(host, None):
                    allowed_hosts.add(info[4][0])
            except OSError:
                pass

    log: list[dict] = []
    real_connect = socket.socket.connect

    def audited_connect(self, addr):  # noqa: ANN001
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        port = addr[1] if isinstance(addr, tuple) and len(addr) > 1 else None
        allowed = (
            not isinstance(addr, tuple)  # unix socket — local by definition
            or host in allowed_hosts
            or host.startswith("127.")
        )
        log.append({"host": host, "port": port, "allowed": allowed})
        if not allowed:
            raise AssertionError(f"OTILLÅTEN extern nätverksanslutning: {addr}")
        return real_connect(self, addr)

    socket.socket.connect = audited_connect
    return log, allowed_hosts

GATES = {
    "recall_at_k": 0.85,
    "citation_verification_rate": 0.90,
    "highlight_correctness": 0.90,
    "false_answer_rate": 0.00,
}


def _area(r: list[float]) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _intersection(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)


def rect_match(cit: list[float], gold: list[float]) -> bool:
    """A citation rect 'lands on' the golden passage if it overlaps it
    substantially: IoU ≥ 0.30, or ≥ 60% of the citation rect lies inside the
    golden rect (shorter-but-correct quotes are correct highlights)."""
    inter = _intersection(cit, gold)
    if inter <= 0:
        return False
    iou = inter / (_area(cit) + _area(gold) - inter)
    containment = inter / _area(cit) if _area(cit) > 0 else 0.0
    return iou >= 0.30 or containment >= 0.60


def load_golden() -> dict:
    return json.loads((EVAL_DIR / "golden.json").read_text("utf-8"))


def fresh_store(settings_overrides: dict | None = None) -> Store:
    """Seed a throwaway store so chunk-knob overrides can re-chunk freely."""
    store = Store(data_dir=tempfile.mkdtemp(prefix="brf-eval-"))
    if settings_overrides:
        store.update_settings(Settings(**{**Settings().model_dump(), **settings_overrides}))
    seed_store(store)
    return store


def golden_span(store: Store, qa: dict) -> tuple[str, int, tuple[int, int]] | None:
    """(document_id, page, word_span) of the golden passage, via our own
    extraction pipeline."""
    by_name = {m.name: m.id for m in store.documents.values()}
    doc_id = by_name.get(qa["document"])
    if doc_id is None:
        return None
    page = store.pages[doc_id][qa["page"] - 1]
    spans = find_spans([w.text for w in page.words], qa["passage"])
    return (doc_id, qa["page"], spans[0]) if spans else None


def eval_retrieval(store: Store, golden: dict) -> dict:
    s = store.settings
    hits_at_k = 0
    misses = []
    for qa in golden["answerable"]:
        target = golden_span(store, qa)
        if target is None:
            misses.append((qa["id"], "golden passage unresolvable"))
            continue
        doc_id, page, (w0, w1) = target
        results = store.index.search(
            qa["question"],
            weight=s.searchWeighting / 100.0,
            candidates=s.candidateCount,
            top_k=s.topK,
            min_confidence=0.0,
        )
        hit = any(
            r.document_id == doc_id
            and r.page == page
            and store.chunks[r.chunk_id].word_start <= w1
            and store.chunks[r.chunk_id].word_end >= w0
            for r in results
        )
        if hit:
            hits_at_k += 1
        else:
            misses.append((qa["id"], qa["question"]))
    n = len(golden["answerable"])
    return {"recall_at_k": hits_at_k / n if n else 0.0, "k": s.topK, "n": n, "misses": misses}


def eval_full(store: Store, golden: dict, workers: int = 4, limit: int | None = None) -> dict:
    answerable = golden["answerable"][:limit] if limit is not None else golden["answerable"]
    unanswerable = golden["unanswerable"][: (max(1, limit // 4) if limit is not None else None)]
    by_name = {m.name: m.id for m in store.documents.values()}

    def run_answerable(qa: dict) -> dict:
        resp = ask(store, qa["question"])
        verified = len(resp.citations)
        rejected = len(resp.rejected_citations)
        correct_highlight = False
        cited_correct_doc = False
        for c in resp.citations:
            if c.document_id == by_name.get(qa["document"]):
                cited_correct_doc = True
                if c.page == qa["page"] and any(
                    rect_match(cr, gr) for cr in c.rects for gr in qa["rects"]
                ):
                    correct_highlight = True
        return {
            "id": qa["id"],
            "question": qa["question"],
            "refused": resp.refusal,
            "refusal_reason": resp.refusal_reason,
            "verified": verified,
            "rejected": rejected,
            "correct_highlight": correct_highlight,
            "cited_correct_doc": cited_correct_doc,
        }

    def run_unanswerable(qa: dict) -> dict:
        resp = ask(store, qa["question"])
        return {"id": qa["id"], "question": qa["question"], "refused": resp.refusal, "reason": resp.refusal_reason}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        ans_results = list(pool.map(run_answerable, answerable))
        una_results = list(pool.map(run_unanswerable, unanswerable))

    answered = [r for r in ans_results if not r["refused"]]
    total_citations = sum(r["verified"] + r["rejected"] for r in ans_results)
    verified_citations = sum(r["verified"] for r in ans_results)
    highlight_ok = [r for r in answered if r["correct_highlight"]]
    doc_ok = [r for r in answered if r["cited_correct_doc"]]

    return {
        "n_answerable": len(ans_results),
        "n_unanswerable": len(una_results),
        "answer_rate": len(answered) / len(ans_results) if ans_results else 0.0,
        "citation_verification_rate": (verified_citations / total_citations) if total_citations else 0.0,
        "highlight_correctness": len(highlight_ok) / len(answered) if answered else 0.0,
        "citation_doc_accuracy": len(doc_ok) / len(answered) if answered else 0.0,
        "false_answer_rate": (sum(1 for r in una_results if not r["refused"]) / len(una_results)) if una_results else 0.0,
        "false_refusals": [r for r in ans_results if r["refused"]],
        "false_answers": [r for r in una_results if not r["refused"]],
        "bad_highlights": [r["id"] for r in answered if not r["correct_highlight"]],
    }


def print_report(retrieval: dict, full: dict | None, settings: Settings, provider: str) -> bool:
    print(f"\n### Eval — chunk={settings.chunkStrategy}/{settings.chunkSize}/{settings.chunkOverlap} "
          f"weight={settings.searchWeighting} topK={settings.topK} minRel={settings.minRelevance} "
          f"provider={provider}\n")
    ok = True

    r = retrieval["recall_at_k"]
    gate = GATES["recall_at_k"]
    ok &= r >= gate
    print(f"| metric | value | gate | status |")
    print(f"|---|---|---|---|")
    print(f"| recall@{retrieval['k']} | {r:.3f} ({round(r * retrieval['n'])}/{retrieval['n']}) | ≥ {gate} | {'✅' if r >= gate else '❌'} |")

    if full:
        rows = [
            ("answer_rate (answerable)", full["answer_rate"], None),
            ("citation_verification_rate", full["citation_verification_rate"], GATES["citation_verification_rate"]),
            ("highlight_correctness", full["highlight_correctness"], GATES["highlight_correctness"]),
            ("citation_doc_accuracy", full["citation_doc_accuracy"], None),
            ("false_answer_rate", full["false_answer_rate"], GATES["false_answer_rate"]),
        ]
        for name, value, gate in rows:
            if gate is None:
                print(f"| {name} | {value:.3f} | — | — |")
            elif name == "false_answer_rate":
                passed = value <= gate
                ok &= passed
                print(f"| {name} | {value:.3f} | ≤ {gate} | {'✅' if passed else '❌'} |")
            else:
                passed = value >= gate
                ok &= passed
                print(f"| {name} | {value:.3f} | ≥ {gate} | {'✅' if passed else '❌'} |")
        if full["false_refusals"]:
            print(f"\nFalse refusals: {[(r['id'], r['refusal_reason']) for r in full['false_refusals']]}")
        if full["false_answers"]:
            print(f"False answers: {[r['id'] for r in full['false_answers']]}")
        if full["bad_highlights"]:
            print(f"Highlight misses: {full['bad_highlights']}")
    if retrieval["misses"]:
        print(f"\nRetrieval misses: {retrieval['misses']}")
    return ok


def run_sweep(golden: dict) -> None:
    base = Settings().model_dump()
    grid: list[tuple[str, list]] = [
        ("searchWeighting", [0, 50, 100]),
        ("topK", [1, 3, 6, 10]),
        ("chunkSize", [80, 220, 500]),
        ("chunkStrategy", ["fixed", "sentence", "recursive"]),
    ]
    print("\n### Knob sweep (retrieval-only) — proof that settings are wired\n")
    print("| knob | value | recall@k | chunks |")
    print("|---|---|---|---|")
    for knob, values in grid:
        for v in values:
            overrides = {**base, knob: v}
            store = fresh_store(overrides)
            res = eval_retrieval(store, golden)
            marker = " (default)" if v == base[knob] else ""
            print(f"| {knob} | {v}{marker} | {res['recall_at_k']:.3f} | {len(store.chunks)} |")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--settings", default=None, help="JSON settings overrides")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--network-audit",
        action="store_true",
        help="hard-fail on any TCP connect outside loopback/BRF_LLM_BASE_URL; write eval/network_audit.json",
    )
    args = parser.parse_args()

    audit_log = None
    if args.network_audit:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # embeddings must load from cache
        audit_log, allowed = install_network_audit()
        print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}")

    golden = load_golden()

    if args.sweep:
        run_sweep(golden)
        return

    overrides = json.loads(args.settings) if args.settings else None
    store = fresh_store(overrides)

    t0 = time.time()
    retrieval = eval_retrieval(store, golden)
    full = None
    provider = "—"
    if not args.retrieval_only:
        from app.llm import pick_provider

        provider = pick_provider().name
        full = eval_full(store, golden, workers=args.workers, limit=args.limit)
    ok = print_report(retrieval, full, store.settings, provider)
    elapsed = time.time() - t0
    print(f"\nKlart på {elapsed:.0f}s.")

    if audit_log is not None:
        external = [e for e in audit_log if not e["allowed"]]
        hosts = sorted({f"{e['host']}:{e['port']}" for e in audit_log})
        (EVAL_DIR / "network_audit.json").write_text(
            json.dumps(
                {
                    "provider": provider,
                    "llm_base_url": os.environ.get("BRF_LLM_BASE_URL", ""),
                    "total_connections": len(audit_log),
                    "distinct_endpoints": hosts,
                    "external_connections": external,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        print(f"Nätverksrevision: {len(audit_log)} anslutningar, {len(external)} externa "
              f"→ eval/network_audit.json")
        ok &= not external

    (EVAL_DIR / "last_run.json").write_text(
        json.dumps(
            {
                "settings": store.settings.model_dump(),
                "provider": provider,
                "retrieval": {k: v for k, v in retrieval.items() if k != "misses"},
                "retrieval_misses": retrieval["misses"],
                "full": full,
                "elapsed_s": round(elapsed, 1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
