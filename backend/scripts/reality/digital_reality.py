"""Born-digital reality run: a REAL BRF PDF through the full pipeline, offline.

Discovers the first born-digital PDF (embedded text layer) in a local,
gitignored corpus folder, ingests it through the same code path as the API,
asks board-style questions against the local self-hosted LLM, and renders each
citation's highlight for review. A network audit hard-fails on any
non-loopback connection. Outputs go ONLY to gitignored/temp locations.

Usage: uv run python -m scripts.reality.digital_reality [--folder DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("BRF_LLM", "selfhosted")
os.environ.setdefault("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
os.environ.setdefault("BRF_LLM_MODEL", "gemma4:e12b")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.eval import install_network_audit  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_FOLDER = BACKEND.parent / "DONT_PUSH_brf_stuff"
DEFAULT_OUT = BACKEND / "out" / "reality"

# Board-style questions for a financial/technical management contract corpus.
# Adjust freely — the point is questions a real board member would ask.
QUESTIONS = [
    ("q01", "Vad ingår i den ekonomiska förvaltningen enligt avtalet?"),
    ("q02", "Vilken uppsägningstid gäller för avtalet?"),
    ("q03", "Vem ansvarar för att upprätta årsredovisningen?"),
    ("q04", "Vilket arvode ska föreningen betala för den ekonomiska förvaltningen?"),
    ("q05", "Ingår momsregistrering av lokaler i uppdraget?"),
    ("q06", "Vad gäller kring nya hyresavtal?"),
    ("q07", "Hur ska föreningens arkiv och nycklar hanteras?"),
    ("q08", "När träder avtalet i kraft och hur länge gäller det?"),
    ("q09", "Vilket organisationsnummer har bostadsrättsföreningen?"),
    ("q10", "Hur hanteras avisering av avgifter och hyror?"),
    # Unanswerable control — must refuse, not guess.
    ("q11", "Vad kostar snöröjningen per säsong enligt avtalet?"),
]


def first_born_digital(folder: Path):
    import fitz

    for p in sorted(folder.glob("*.pdf")):
        doc = fitz.open(str(p))
        chars = sum(len(pg.get_text().strip()) for pg in doc)
        n = len(doc)
        doc.close()
        if chars > 100 * n:
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--rerank",
        action="store_true",
        help="enable the cross-encoder rerank stage (Settings.rerankEnabled=True; rerankCandidates default 40)",
    )
    args = ap.parse_args()

    audit_log, allowed = install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna värdar: {sorted(allowed)}", flush=True)

    import fitz

    from app.answer import ask
    from app.store import Store

    pdf = first_born_digital(args.folder)
    if pdf is None:
        raise SystemExit(f"Ingen digital PDF (textlager) hittades i {args.folder}")
    hl_dir = args.out / "highlights"
    hl_dir.mkdir(parents=True, exist_ok=True)

    # Corpus-isolation guard (CI2/CI3): this ingests a REAL customer document
    # from the local gitignored corpus (DONT_PUSH_brf_stuff) — the temp
    # tenant must declare origin explicitly as "customer" (non-val naming),
    # not fall through Store's bare-construction migration default of
    # "synthetic" (the gap CI2's review flagged; see
    # docs/evidence/corpus-isolation.md).
    store = Store(data_dir=tempfile.mkdtemp(prefix="brf-reality-"), corpus_origin="customer")
    meta = store.add_document(pdf.name, pdf.read_bytes())
    print(f"Ingested: pages={meta.pages} words={meta.words} chunks={meta.chunks}", flush=True)

    if args.rerank:
        store.update_settings(store.settings.model_copy(update={"rerankEnabled": True}))

    src = fitz.open(str(pdf))
    results = []
    for qid, q in QUESTIONS:
        try:
            resp = ask(store, q)
        except Exception as exc:  # the failure IS a finding — keep going
            results.append({"qid": qid, "question": q, "error": repr(exc)})
            print(f"{qid}: ERROR {exc!r}", flush=True)
            continue
        results.append(
            {
                "qid": qid,
                "question": q,
                "refusal": resp.refusal,
                "refusal_reason": resp.refusal_reason,
                "answer": resp.answer,
                "citations": [
                    {
                        "page": c.page,
                        "quote": c.quote,
                        "quotes": c.quotes,
                        "n_spans": len(c.quotes),
                        "n_rects": len(c.rects),
                        "rects": c.rects,
                    }
                    for c in resp.citations
                ],
                "rejected": [{"reason": r.reason, "quote": r.quote[:120]} for r in resp.rejected_citations],
                "top_retrieval_pages": [h.page for h in resp.retrieval[:6]],
            }
        )
        print(
            f"{qid}: refusal={resp.refusal} citations={len(resp.citations)} rejected={len(resp.rejected_citations)}",
            flush=True,
        )
        for ci, c in enumerate(resp.citations, 1):
            page = src[c.page - 1]
            rects = [fitz.Rect(*r) for r in c.rects]
            shape = page.new_shape()
            for r in rects:
                shape.draw_rect(r)
            shape.finish(color=(1, 0, 0), width=1.2)
            shape.commit()
            union = rects[0]
            for r in rects[1:]:
                union |= r
            clip = fitz.Rect(0, max(0, union.y0 - 90), page.rect.x1, min(page.rect.y1, union.y1 + 90))
            page.get_pixmap(dpi=150, clip=clip).save(str(hl_dir / f"{qid}_c{ci}.png"))
    src.close()

    external = [e for e in audit_log if not e["allowed"]]
    summary = {
        "pdf": pdf.name,
        "rerank_enabled": args.rerank,
        "pages": meta.pages,
        "words": meta.words,
        "chunks": meta.chunks,
        "network_audit": {
            "total_connections": len(audit_log),
            "distinct_endpoints": sorted({f"{e['host']}:{e['port']}" for e in audit_log}),
            "external_connections": external,
        },
        "results": results,
    }
    (args.out / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print(f"DONE. connections={len(audit_log)} external={len(external)} → {args.out/'run.json'}", flush=True)


if __name__ == "__main__":
    main()
