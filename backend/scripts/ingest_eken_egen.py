"""Ingest Eken's own public PDFs into a copy of the BRF-1 nine-doc store.

    uv run python -m scripts.ingest_eken_egen

Copies /tmp/brf1-store → /tmp/brf1-store-eken, then Store.add_document for the
five public files (OCR where there is no text layer). Writes a numeric ingest
report under backend/out/; never commits PDFs.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
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

from app.document_describe import freeze_descriptions, snapshot_description_lock  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval_brf1_variance import letters_for  # noqa: E402

SRC_STORE = Path("/tmp/brf1-store")
DST_STORE = Path("/tmp/brf1-store-eken")
PDF_DIR = backend.parent / "DONT_PUSH_brf_stuff" / "eken-egen"
OUT = backend / "out" / "brf1-eken-ingest"

# Store names: keep BRF-1 A–I letters if possible. EkonomiskPlan would sort
# into the Avtal-block and shift G/E, so prefix with Å/S/R where needed.
FILES = [
    ("2025-Arsredovisning.pdf", "Årsredovisning 2025.pdf"),
    ("2025-Revisionsberattelse.pdf", "Revisionsberättelse 2025.pdf"),
    ("Stadgar-Brf-Eken-i-Goteborg-digital.pdf", "Stadgar Brf Eken i Göteborg.pdf"),
    ("EkonomiskPlan.pdf", "Ekonomisk plan.pdf"),
    ("eken-broschyr.pdf", "Bofaktablad.pdf"),
]


def document_kind(name: str) -> str:
    n = name.casefold()
    if "stadgar" in n:
        return "stadgar"
    if "årsred" in n or "arsred" in n:
        return "annual_report"
    if "revision" in n:
        return "auditor_report"
    if "ekonomisk plan" in n:
        return "economic_plan"
    if "bofaktablad" in n or "broschyr" in n:
        return "brochure"
    return "other"


def main() -> int:
    if not SRC_STORE.exists():
        raise SystemExit(f"saknar {SRC_STORE}")
    if DST_STORE.exists():
        shutil.rmtree(DST_STORE)
    shutil.copytree(SRC_STORE, DST_STORE)
    OUT.mkdir(parents=True, exist_ok=True)

    store = Store(data_dir=DST_STORE)
    before = {m.id: m.name for m in store.documents.values()}
    added: list[dict] = []
    for src_name, store_name in FILES:
        path = PDF_DIR / src_name
        if not path.exists():
            raise SystemExit(f"saknar {path}")
        t0 = time.perf_counter()
        meta = store.add_document(store_name, path.read_bytes())
        elapsed = round(time.perf_counter() - t0, 3)
        row = {
            "id": meta.id,
            "name": meta.name,
            "kind": document_kind(meta.name),
            "source": meta.source,
            "pages": meta.pages,
            "words": meta.words,
            "chunks": meta.chunks,
            "thin": meta.thin,
            "thin_pages": meta.thin_pages,
            "has_description": bool(meta.description),
            "ingest_s": elapsed,
        }
        added.append(row)
        print(
            f"ingested kind={row['kind']} source={row['source']} "
            f"pages={row['pages']} words={row['words']} {elapsed}s",
            flush=True,
        )

    letters = letters_for(store)
    version = freeze_descriptions(store)
    lock = snapshot_description_lock(store)
    (OUT / "lock.json").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = {
        "n_before": len(before),
        "n_after": len(store.documents),
        "description_version": version,
        "added": added,
        "letters": {letters[i]: store.documents[i].name for i in sorted(letters, key=letters.get)},
        "kinds": {
            letters[m.id]: {"kind": document_kind(m.name), "source": m.source, "pages": m.pages, "words": m.words}
            for m in store.documents.values()
        },
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"n={report['n_after']} version={version}", flush=True)
    for letter, name in sorted(report["letters"].items()):
        meta = next(m for m in store.documents.values() if m.name == name)
        print(f"  {letter} {meta.source:8} {document_kind(name):16} p={meta.pages} w={meta.words}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
