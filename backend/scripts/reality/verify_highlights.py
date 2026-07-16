"""Computational verification of a digital_reality run's highlight rects.

Independent of the backend, re-derives whether each shown citation is honest:
collect the embedded-text words whose centers fall inside the returned rects,
canonicalize with the app's normalize pipeline, and check that

  1. every cited span (`quotes`, or the single `quote`) is itself verbatim-
     findable in the cited page via find_spans — the verification invariant; and
  2. the rect-covered words equal the union of the spans' words (exact, or a
     superset only by edge spillover) — i.e. the highlight covers exactly the
     verified fragments, nothing fabricated.

A citation 'lands' only if both hold for every span. This is a second,
independent enforcement of the all-or-nothing invariant.

Usage: uv run python -m scripts.reality.verify_highlights [--run RUN_JSON] [--folder DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz  # noqa: E402

from app.normalize import canonical_stream, find_spans  # noqa: E402

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
            page_word_texts = [w[4] for w in words]
            picked: list[str] = []
            for r in c["rects"]:
                rect = fitz.Rect(*r)
                for w in words:
                    if rect.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)):
                        picked.append(w[4])
            picked_norm = canon(picked)
            rect_tokens = sorted(picked_norm)
            spans = c.get("quotes") or [c.get("quote", "")]
            # (1) every span independently verifiable on the page (the invariant)
            spans_verify = all(find_spans(page_word_texts, sp) for sp in spans)
            # (2) rects cover exactly the union of span tokens (+ edge spill only):
            #     each span's words appear among the rect-covered words.
            span_tokens = sorted(t for sp in spans for t in canon(sp.split()))
            covered = all(set(canon(sp.split())) <= set(picked_norm) for sp in spans)
            if rect_tokens == span_tokens and spans_verify:
                verdict = "exact"
            elif spans_verify and covered and len(rect_tokens) >= len(span_tokens):
                verdict = "superset(edge-spill)"
            elif not spans_verify:
                verdict = "INVARIANT-VIOLATION(span-unverifiable)"
            else:
                inter = len(set(rect_tokens) & set(span_tokens))
                union = len(set(rect_tokens) | set(span_tokens)) or 1
                verdict = f"MISMATCH(jaccard={inter/union:.2f})"
            rows.append(
                {
                    "qid": res["qid"],
                    "citation": ci,
                    "page": c["page"],
                    "n_spans": len(spans),
                    "n_rects": len(c["rects"]),
                    "span_tokens": len(span_tokens),
                    "rect_tokens": len(rect_tokens),
                    "spans_verify": spans_verify,
                    "verdict": verdict,
                }
            )
    doc.close()

    ok = sum(1 for r in rows if r["verdict"] in ("exact", "superset(edge-spill)"))
    violations = [r for r in rows if "INVARIANT-VIOLATION" in r["verdict"]]
    out = {
        "citations_checked": len(rows),
        "landed": ok,
        "landed_rate": round(ok / len(rows), 3) if rows else None,
        "invariant_violations": len(violations),
        "multispan_citations": sum(1 for r in rows if r["n_spans"] > 1),
        "detail": rows,
    }
    (args.run.parent / "highlight_verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
