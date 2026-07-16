"""Computational verification of a digital_reality run's highlight rects.

For every citation in the run: collect the embedded-text words whose centers
fall inside the returned rects, canonicalize both sides with the app's own
normalize pipeline, and compare against the cited quote. A highlight 'lands'
when the covered words match the quote tokens (exact or edge spillover).

Usage: uv run python -m scripts.reality.verify_highlights [--run RUN_JSON] [--folder DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz  # noqa: E402

from app.normalize import canonical_stream  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_RUN = BACKEND / "out" / "reality" / "run.json"
DEFAULT_FOLDER = BACKEND.parent / "DONT_PUSH_brf_stuff"


def canon(tokens: list[str]) -> list[str]:
    return [t for t, _ in canonical_stream(tokens)]


def contiguous_subseq(needle: list[str], hay: list[str]) -> bool:
    n, h = len(needle), len(hay)
    if n == 0 or n > h:
        return False
    return any(hay[i : i + n] == needle for i in range(h - n + 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    args = ap.parse_args()

    run = json.loads(args.run.read_text("utf-8"))
    doc = fitz.open(str(args.folder / run["pdf"]))

    rows = []
    for res in run["results"]:
        for ci, c in enumerate(res.get("citations", []), 1):
            page = doc[c["page"] - 1]
            words = page.get_text("words")
            picked: list[str] = []
            for r in c["rects"]:
                rect = fitz.Rect(*r)
                for w in words:
                    if rect.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)):
                        picked.append(w[4])
            rect_tokens = canon(picked)
            quote_tokens = canon(c["quote"].split())
            if rect_tokens == quote_tokens:
                verdict = "exact"
            elif contiguous_subseq(quote_tokens, rect_tokens):
                verdict = "superset(edge-spill)"
            elif contiguous_subseq(rect_tokens, quote_tokens):
                verdict = "subset(missing-words)"
            else:
                inter = len(set(rect_tokens) & set(quote_tokens))
                union = len(set(rect_tokens) | set(quote_tokens)) or 1
                verdict = f"MISMATCH(jaccard={inter/union:.2f})"
            rows.append(
                {
                    "qid": res["qid"],
                    "citation": ci,
                    "page": c["page"],
                    "n_rects": len(c["rects"]),
                    "quote_tokens": len(quote_tokens),
                    "rect_tokens": len(rect_tokens),
                    "verdict": verdict,
                }
            )
    doc.close()

    ok = sum(1 for r in rows if r["verdict"] in ("exact", "superset(edge-spill)"))
    out = {
        "citations_checked": len(rows),
        "landed": ok,
        "landed_rate": round(ok / len(rows), 3) if rows else None,
        "detail": rows,
    }
    (args.run.parent / "highlight_verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
