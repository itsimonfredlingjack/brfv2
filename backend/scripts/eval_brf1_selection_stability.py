"""BRF-1 description selection only, twenty separate processes.

    uv run python -m scripts.eval_brf1_selection_stability

Does not call ask(). Each worker is a fresh process: load store,
select_documents_by_description for the eleven cases, exit. Descriptions
are whatever the store already has (product path). Parent runs workers
one after another (llama.cpp --parallel 1).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

backend = Path(__file__).resolve().parent.parent
RUNS = 20
STORE_DIR = Path("/tmp/brf1-store")
CASES = Path("/tmp/brf1-cases/eleven.json")
OUT = backend / "out" / "brf1-selection-stability"


def name_letters(documents: dict) -> dict[str, str]:
    ordered = sorted(documents.values(), key=lambda m: m.name)
    return {m.id: chr(ord("A") + i) for i, m in enumerate(ordered)}


def worker(out_path: Path) -> int:
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    os.environ.setdefault("BRF_EMBEDDER", "hashed")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("BRF_LLM", "selfhosted")
    os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")
    os.environ["BRF_PREFIX_WARMUP"] = "0"
    os.environ.pop("BRF_PLANNED_ASK", None)

    from app.document_ask import catalog_entries, select_documents_by_description
    from app.llm import pick_provider
    from app.store import Store
    from scripts.eval import install_network_audit

    audit_log, _allowed = install_network_audit()
    store = Store(data_dir=STORE_DIR)
    provider = pick_provider()
    if provider.name in ("fake", "none"):
        raise SystemExit(f"need real model, got {provider.name}")
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    letters = name_letters(store.documents)
    catalog = {meta.id: letter for letter, meta in catalog_entries(store.documents)}
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    rows = []
    for case in spec:
        ids = select_documents_by_description(
            question=case["question"],
            documents=dict(store.documents),
            provider=provider,
            model=model,
        )
        rows.append(
            {
                "id": case["id"],
                "gold": case["doc"],
                "selected_ids": ids,
                "name_letters": [letters.get(i, "?") for i in ids],
                "catalog_letters": [catalog.get(i, "?") for i in ids],
                "gold_selected": case["doc"] in [letters.get(i, "?") for i in ids],
            }
        )
        print(
            f"{case['id']} name={rows[-1]['name_letters']} catalog={rows[-1]['catalog_letters']}",
            flush=True,
        )
    external = [e for e in audit_log if not e["allowed"]]
    payload = {"rows": rows, "external_connections": external, "model": model}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if external:
        raise SystemExit("extern nätverkstrafik")
    return 0


def summarize(run_files: list[Path]) -> dict:
    spec = json.loads(CASES.read_text("utf-8"))["cases"]
    by_case: dict[str, list[tuple[str, ...]]] = {c["id"]: [] for c in spec}
    gold_hits: dict[str, int] = {c["id"]: 0 for c in spec}
    for path in run_files:
        data = json.loads(path.read_text("utf-8"))
        for row in data["rows"]:
            key = tuple(row["name_letters"])
            by_case[row["id"]].append(key)
            if row["gold_selected"]:
                gold_hits[row["id"]] += 1
    cases = []
    n_stable = 0
    for case in spec:
        cid = case["id"]
        counts = Counter(by_case[cid])
        common, n_common = counts.most_common(1)[0]
        n_unique = len(counts)
        stable = n_unique == 1
        if stable:
            n_stable += 1
        cases.append(
            {
                "id": cid,
                "gold": case["doc"],
                "n_runs": len(by_case[cid]),
                "n_unique_sets": n_unique,
                "same_as_mode": n_common,
                "mode": list(common),
                "all": {",".join(k) if k else "∅": v for k, v in counts.most_common()},
                "gold_selected": gold_hits[cid],
                "stable": stable,
            }
        )
    return {
        "runs": len(run_files),
        "n_cases": len(spec),
        "stable_cases": n_stable,
        "cases": cases,
    }


def parent() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    run_files: list[Path] = []
    exe = sys.executable
    for i in range(1, RUNS + 1):
        out = OUT / f"run-{i:02d}.json"
        print(f"\n=== process {i}/{RUNS} ===", flush=True)
        subprocess.run(
            [exe, "-m", "scripts.eval_brf1_selection_stability", "--worker", str(out)],
            cwd=str(backend),
            check=True,
        )
        run_files.append(out)
    summary = summarize(run_files)
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nper fall (samma name-order-handlingar / 20):", flush=True)
    for row in summary["cases"]:
        print(
            f"{row['id']} {row['same_as_mode']}/20 identiska med läget "
            f"{row['mode'] or '∅'} unika={row['n_unique_sets']} "
            f"guld_med={row['gold_selected']}/20",
            flush=True,
        )
    print(f"stabila fall {summary['stable_cases']}/11", flush=True)
    return 0


def main() -> int:
    if "--worker" in sys.argv:
        idx = sys.argv.index("--worker")
        return worker(Path(sys.argv[idx + 1]))
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    return parent()


if __name__ == "__main__":
    raise SystemExit(main())
