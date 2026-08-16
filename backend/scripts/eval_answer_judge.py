"""Eval diagnostic: local model as judge over 22 hand-labelled BRF-1 answers.

    uv run python -m scripts.eval_answer_judge

One complete() per answer. No ask(). No gate. Prompt is not tuned against
these 22 — they are the only honest labels. Network stays on loopback.
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

from app.answer_judge import SYSTEM, judge_answer  # noqa: E402
from app.full_corpus import server_origin  # noqa: E402
from app.llm import pick_provider  # noqa: E402
from scripts.eval import install_network_audit  # noqa: E402

DOC_ANSWERS = backend / "out" / "brf1-doc-path-desc" / "answers.json"
RET_ANSWERS = backend / "out" / "brf1-retrieval-answers" / "answers.json"
OUT = backend / "out" / "brf1-answer-judge"

# Hand labels from docs/evidence/brf1-doc-path-desc.md. Not derived from the judge.
DOC_MANUAL = {
    "R1": "ofullstandigt",
    "R2": "besvarar",
    "R3": "besvarar",
    "R4": "besvarar",
    "R5": "besvarar",
    "R6": "besvarar",
    "R7": "besvarar",
    "R8": "besvarar",
    "R3b": "fel_handling",
    "R5b": "besvarar",
    "R7b": "fel_handling",
}
RET_MANUAL = {
    "R1": "fel_handling",
    "R2": "besvarar",
    "R3": "vagrad",
    "R4": "besvarar",
    "R5": "vagrad",
    "R6": "besvarar",
    "R7": "vagrad",
    "R8": "besvarar",
    "R3b": "ofullstandigt",
    "R5b": "vagrad",
    "R7b": "vagrad",
}
RET_REFUSALS = {"R3", "R5", "R7", "R5b", "R7b"}


def quotes_of(row: dict) -> list[str]:
    return [q for c in row.get("cited") or [] for q in c.get("quotes") or []]


def score_row(provider, model: str, path: str, row: dict, manual: str) -> dict:
    t0 = time.perf_counter()
    result = judge_answer(provider, row["question"], quotes_of(row), row["answer"], model=model)
    elapsed = time.perf_counter() - t0
    return {
        "path": path,
        "id": row["id"],
        "gold": row.get("gold"),
        "manual": manual,
        "refusal": bool(row.get("refusal")),
        "refusal_reason": row.get("refusal_reason"),
        "n_quotes": len(quotes_of(row)),
        "outcome": result.outcome,
        "parse": result.reason,
        "raw": result.raw,
        "elapsed_s": round(elapsed, 3),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    origin = server_origin(os.environ["BRF_LLM_BASE_URL"])
    print(f"origin {origin}", flush=True)
    audit_log, allowed = install_network_audit()
    print(f"audit allowed={sorted(allowed)}", flush=True)
    provider = pick_provider()
    model = getattr(provider, "model", "") or os.environ.get("BRF_LLM_MODEL", "")
    print(f"provider={provider.name} model={model}", flush=True)

    doc_rows = json.loads(DOC_ANSWERS.read_text("utf-8"))["rows"]
    ret_rows = json.loads(RET_ANSWERS.read_text("utf-8"))["rows"]
    scored: list[dict] = []
    for row in doc_rows:
        item = score_row(provider, model, "documents", row, DOC_MANUAL[row["id"]])
        scored.append(item)
        print(f"documents {item['id']} manual={item['manual']} outcome={item['outcome']}", flush=True)
    for row in ret_rows:
        item = score_row(provider, model, "retrieval", row, RET_MANUAL[row["id"]])
        scored.append(item)
        print(f"retrieval {item['id']} manual={item['manual']} outcome={item['outcome']}", flush=True)

    doc = [r for r in scored if r["path"] == "documents"]
    ret = [r for r in scored if r["path"] == "retrieval"]
    r1_doc = next(r for r in doc if r["id"] == "R1")
    eight = [r for r in doc if r["manual"] == "besvarar"]
    four = [r for r in ret if r["manual"] == "besvarar"]
    refusals = [r for r in ret if r["id"] in RET_REFUSALS]
    eight_fp = [r["id"] for r in eight if r["outcome"] != "besvarar"]
    four_fp = [r["id"] for r in four if r["outcome"] != "besvarar"]
    r1_caught = r1_doc["outcome"] in {"besvarar_inte", "motsager_citatet"}
    summary = {
        "provider": provider.name,
        "model": model,
        "prompt": SYSTEM,
        "n": len(scored),
        "r1_documents_manual": r1_doc["manual"],
        "r1_documents_outcome": r1_doc["outcome"],
        "r1_caught": r1_caught,
        "documents_besvarar_n": len(eight),
        "documents_false_alarms": eight_fp,
        "documents_false_alarm_n": len(eight_fp),
        "retrieval_besvarar_n": len(four),
        "retrieval_false_alarms": four_fp,
        "retrieval_false_alarm_n": len(four_fp),
        "both_paths_besvarar_n": len(eight) + len(four),
        "both_paths_false_alarm_n": len(eight_fp) + len(four_fp),
        "entailment_false_alarms_on_eight": 2,
        "below_entailment_and_r1_caught": r1_caught and len(eight_fp) < 2,
        "retrieval_refusals": [
            {"id": r["id"], "reason": r["refusal_reason"], "outcome": r["outcome"], "n_quotes": r["n_quotes"]}
            for r in refusals
        ],
        "external_connections": [e for e in audit_log if not e["allowed"]],
        "rows": scored,
    }
    (OUT / "result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\nR1 caught={r1_caught} ({r1_doc['outcome']}) "
        f"doc_fp={len(eight_fp)}/{len(eight)} {eight_fp} "
        f"ret_fp={len(four_fp)}/{len(four)} {four_fp} "
        f"refusals={[r['outcome'] for r in refusals]} "
        f"candidate={summary['below_entailment_and_r1_caught']}",
        flush=True,
    )
    if summary["external_connections"]:
        raise SystemExit("extern nätverkstrafik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
