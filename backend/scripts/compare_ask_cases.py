"""Per-(document, question) before→after table for ask() runs.

Headline number is verified→refused. Totals can stay flat while cases swap.

Usage (from backend/):
    uv run python -m scripts.compare_ask_cases --before before.json --after after.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _cases(run: dict) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    documents = run.get("documents") or {}
    for doc, payload in documents.items():
        for row in payload.get("questions") or []:
            qid = row.get("qid")
            if qid is None:
                continue
            out[(str(doc), str(qid))] = row
    return out


def _verified(row: dict | None) -> bool:
    if row is None or row.get("error"):
        return False
    return not bool(row.get("refused"))


def compare_runs(before: dict, after: dict) -> dict:
    left = _cases(before)
    right = _cases(after)
    keys = sorted(set(left) | set(right))
    rows = []
    verified_to_refused = 0
    refused_to_verified = 0
    for doc, qid in keys:
        b = left.get((doc, qid))
        a = right.get((doc, qid))
        b_ok = _verified(b)
        a_ok = _verified(a)
        if b_ok and not a_ok:
            verified_to_refused += 1
        if (not b_ok) and a_ok:
            refused_to_verified += 1
        rows.append(
            {
                "doc": doc,
                "qid": qid,
                "before_refused": None if b is None else bool(b.get("refused")),
                "after_refused": None if a is None else bool(a.get("refused")),
                "before_refusal_reason": None if b is None else b.get("refusal_reason"),
                "after_refusal_reason": None if a is None else a.get("refusal_reason"),
                "before_n_citations": None if b is None else b.get("n_citations"),
                "after_n_citations": None if a is None else a.get("n_citations"),
                "before_elapsed_s": None if b is None else b.get("elapsed_s"),
                "after_elapsed_s": None if a is None else a.get("elapsed_s"),
            }
        )
    return {
        "verified_to_refused": verified_to_refused,
        "refused_to_verified": refused_to_verified,
        "rows": rows,
    }


def format_table(result: dict) -> str:
    lines = [
        "doc qid before_refused after_refused before_reason after_reason before_cites after_cites before_s after_s"
    ]
    for row in result["rows"]:
        lines.append(
            f"{row['doc']} {row['qid']} {row['before_refused']} {row['after_refused']} "
            f"{row['before_refusal_reason']} {row['after_refusal_reason']} "
            f"{row['before_n_citations']} {row['after_n_citations']} "
            f"{row['before_elapsed_s']} {row['after_elapsed_s']}"
        )
    lines.append(f"verified_to_refused={result['verified_to_refused']}")
    lines.append(f"refused_to_verified={result['refused_to_verified']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    args = ap.parse_args()
    before = json.loads(args.before.read_text("utf-8"))
    after = json.loads(args.after.read_text("utf-8"))
    result = compare_runs(before, after)
    print(format_table(result), flush=True)


if __name__ == "__main__":
    main()
