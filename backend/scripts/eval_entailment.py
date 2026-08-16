"""Eval diagnostic: LettuceDetect on captured answers. Not a product path.

    uv run python -m scripts.eval_entailment

Requires extra `entailment` and `BRF_ENTAILMENT=1`. Scores the already
captured document-path BRF-1 answers. Does not call ask(). Does not refuse.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

backend = Path(__file__).resolve().parent.parent
os.chdir(backend)
sys.path.insert(0, str(backend))

os.environ["BRF_ENTAILMENT"] = "1"
os.environ["BRF_ENTAILMENT_DEVICE"] = "cpu"
os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ["BRF_PREFIX_WARMUP"] = "0"

from app.entailment import (  # noqa: E402
    DEFAULT_MODEL,
    check_entailment,
    claim_sentences,
    model_name,
)

ANSWERS = backend / "out" / "brf1-doc-path-desc" / "answers.json"
OUT = backend / "out" / "brf1-entailment"

ANSWERS_QUESTION = {"R2", "R3", "R4", "R5", "R6", "R7", "R8", "R5b"}
WRONG_DOC = {"R3b", "R7b"}
INCOMPLETE_GOLD = {"R1"}


def german_control() -> dict:
    result = check_entailment(
        "Die Hauptstadt von Frankreich ist Paris. Die Bevölkerung Frankreichs beträgt 69 Millionen.",
        [
            "Frankreich ist ein Land in Europa. Die Hauptstadt von Frankreich ist Paris. "
            "Die Bevölkerung Frankreichs beträgt 67 Millionen."
        ],
        "Was ist die Hauptstadt von Frankreich? Wie groß ist die Bevölkerung Frankreichs?",
    )
    return {
        "ok": result.ok,
        "skipped": result.skipped,
        "reason": result.reason,
        "n_unsupported": len(result.unsupported),
        "sentences": [c.sentence for c in result.unsupported],
        "caught_population_lie": any("69" in c.sentence or "69" in " ".join(c.spans) for c in result.unsupported)
        or any("69" in s for c in result.unsupported for s in c.spans),
        "clean_supported_sentence": not any("Paris" in c.sentence and "69" not in c.sentence for c in result.unsupported),
    }


def score_row(row: dict) -> dict:
    quotes = [q for c in row.get("cited") or [] for q in c.get("quotes") or []]
    t0 = time.perf_counter()
    result = check_entailment(row["answer"], quotes, row["question"])
    elapsed = time.perf_counter() - t0
    return {
        "id": row["id"],
        "gold": row["gold"],
        "manual": (
            "besvarar"
            if row["id"] in ANSWERS_QUESTION
            else "ofullstandigt"
            if row["id"] in INCOMPLETE_GOLD
            else "fel_handling"
        ),
        "ok": result.ok,
        "skipped": result.skipped,
        "reason": result.reason,
        "flagged": not result.ok and not result.skipped,
        "n_sentences": len(claim_sentences(row["answer"])),
        "n_unsupported": len(result.unsupported),
        "unsupported": [
            {"sentence": c.sentence, "confidence": round(c.confidence, 3), "spans": list(c.spans)}
            for c in result.unsupported
        ],
        "elapsed_s": round(elapsed, 3),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    name = model_name()
    print(f"model {name} (default {DEFAULT_MODEL})", flush=True)
    control = german_control()
    print(f"german_control {control}", flush=True)

    rows = json.loads(ANSWERS.read_text("utf-8"))["rows"]
    scored = [score_row(row) for row in rows]
    for row in scored:
        print(
            f"{row['id']} manual={row['manual']} flagged={row['flagged']} "
            f"n_unsup={row['n_unsupported']} reason={row['reason']} "
            f"elapsed_s={row['elapsed_s']}",
            flush=True,
        )

    eight = [r for r in scored if r["id"] in ANSWERS_QUESTION]
    r1 = next(r for r in scored if r["id"] == "R1")
    summary = {
        "model": name,
        "default_model": DEFAULT_MODEL,
        "device": "cpu",
        "lang": os.environ.get("BRF_ENTAILMENT_LANG", "de"),
        "german_control": control,
        "r1_caught": r1["flagged"],
        "n_eight": len(eight),
        "eight_flagged": sum(1 for r in eight if r["flagged"]),
        "eight_flagged_ids": [r["id"] for r in eight if r["flagged"]],
        "wrong_doc_flagged": [r["id"] for r in scored if r["id"] in WRONG_DOC and r["flagged"]],
        "rows": scored,
    }
    (OUT / "result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\nR1 caught={summary['r1_caught']} "
        f"eight_flagged={summary['eight_flagged']}/{summary['n_eight']} "
        f"{summary['eight_flagged_ids']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    raise SystemExit(main())
