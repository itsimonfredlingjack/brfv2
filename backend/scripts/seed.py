"""Deterministic demo corpus seeder + golden-set builder.

Usage:
    uv run python -m scripts.seed --reset     # wipe, reseed, rebuild golden.json
    uv run python -m scripts.seed             # seed into empty store + golden.json
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import Store  # noqa: E402
from scripts.seed_content import DOCUMENTS, FOOTER, GOLDEN_ANSWERABLE, GOLDEN_UNANSWERABLE  # noqa: E402

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN_X = 72.0
BODY_TOP = 72.0
FOOTER_Y = 812.0
_META = {
    "creationDate": "D:20260101000000",
    "modDate": "D:20260101000000",
    "producer": "brf-seed",
    "creator": "brf-seed",
    "title": "",
    "author": "",
    "subject": "",
    "keywords": "",
}


def render_pdf(doc_def: dict) -> bytes:
    doc = fitz.open()
    for page_paras in doc_def["pages"]:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        y = BODY_TOP
        for para in page_paras:
            heading = para.startswith("# ")
            text = para[2:] if heading else para
            fontsize = 12.5 if heading else 10.0
            fontname = "hebo" if heading else "helv"
            wrap_width = 70 if heading else 92
            for hard_line in text.split("\n"):
                for line in textwrap.wrap(hard_line, width=wrap_width) or [""]:
                    page.insert_text(fitz.Point(MARGIN_X, y), line, fontsize=fontsize, fontname=fontname)
                    y += fontsize * 1.38
            y += 7.0
        if y > FOOTER_Y - 20:
            raise AssertionError(f"Sidan överfull i {doc_def['name']} (y={y:.0f}) — dela upp innehållet.")
        page.insert_text(fitz.Point(MARGIN_X, FOOTER_Y), FOOTER, fontsize=8, fontname="helv", color=(0.45, 0.45, 0.45))
    doc.set_metadata(_META)
    data = doc.tobytes(deflate=True, no_new_id=True)
    doc.close()
    return data


def seed_store(store: Store) -> int:
    for d in DOCUMENTS:
        store.add_document(d["name"], render_pdf(d))
    return len(DOCUMENTS)


def build_golden(store: Store) -> dict:
    """Locate every golden passage independently of the citation pipeline
    (fitz search_for) and fail loudly if any passage is unfindable."""
    by_name: dict[str, str] = {m.name: m.id for m in store.documents.values()}
    answerable = []
    problems = []
    for i, qa in enumerate(GOLDEN_ANSWERABLE):
        doc_id = by_name.get(qa["document"])
        if doc_id is None:
            problems.append(f"[{i}] okänt dokument: {qa['document']}")
            continue
        pdf = fitz.open(stream=store.get_pdf_bytes(doc_id), filetype="pdf")
        found = None
        for page in pdf:
            rects = page.search_for(qa["passage"])
            if rects:
                found = {
                    "id": f"g{i:02d}",
                    "question": qa["question"],
                    "document": qa["document"],
                    "page": page.number + 1,
                    "passage": qa["passage"],
                    "rects": [[round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)] for r in rects],
                }
                break
        pdf.close()
        if found is None:
            problems.append(f"[{i}] passage hittas inte: {qa['passage'][:60]!r} i {qa['document']}")
        else:
            answerable.append(found)
    if problems:
        raise AssertionError("Golden-passager kunde inte verifieras:\n" + "\n".join(problems))
    return {
        "corpus": [m.name for m in store.documents.values()],
        "answerable": answerable,
        "unanswerable": [
            {"id": f"u{i:02d}", "question": q} for i, q in enumerate(GOLDEN_UNANSWERABLE)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe existing documents first")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    store = Store(data_dir=args.data_dir)
    if args.reset:
        store.wipe()
    if store.documents:
        print(f"Store innehåller redan {len(store.documents)} dokument — kör med --reset för att börja om.")
    n = seed_store(store)
    golden = build_golden(store)
    golden_path = Path(__file__).resolve().parent.parent / "eval" / "golden.json"
    golden_path.parent.mkdir(exist_ok=True)
    golden_path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), "utf-8")
    print(f"Seedade {n} dokument ({sum(m.pages for m in store.documents.values())} sidor, "
          f"{len(store.chunks)} chunks).")
    print(f"Golden set: {len(golden['answerable'])} besvarbara + {len(golden['unanswerable'])} obesvarbara "
          f"→ {golden_path}")


if __name__ == "__main__":
    main()
