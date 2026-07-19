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


# Demo accounts (printed at seed time; local demo only — rotate for any
# deployment that leaves this machine).
DEMO_USERS = [
    ("anna@gjutformen12.se", "gjutformen-demo-2026", "Anna Andersson", [("gjutformen-12", "admin")]),
    ("bo@gjutformen12.se", "gjutformen-medlem-2026", "Bo Bergström", [("gjutformen-12", "member")]),
    ("stina@sjoutsikten7.se", "sjoutsikten-demo-2026", "Stina Sjöberg", [("sjoutsikten-7", "admin")]),
    ("max@demo.se", "max-demo-2026", "Max Demo", [("gjutformen-12", "admin"), ("sjoutsikten-7", "member")]),
]


def seed_demo(registry, auth) -> dict:
    """Seed the two-tenant demo: corpus A (Gjutformen 12), corpus B
    (Sjöutsikten 7, when seed_content_b exists) and the demo accounts."""
    from app.auth import AuthError

    tenants: dict[str, int] = {}
    try:
        a = registry.create("Brf Gjutformen 12", "synthetic", "gjutformen-12")
    except AuthError:
        a = "gjutformen-12"
    store_a = registry.get(a)
    if store_a is not None and not store_a.documents:
        tenants[a] = seed_store(store_a)

    try:
        from scripts.seed_content_b import DOCUMENTS_B
    except ImportError:
        DOCUMENTS_B = None
    if DOCUMENTS_B:
        try:
            b = registry.create("Brf Sjöutsikten 7", "synthetic", "sjoutsikten-7")
        except AuthError:
            b = "sjoutsikten-7"
        store_b = registry.get(b)
        if store_b is not None and not store_b.documents:
            for d in DOCUMENTS_B:
                store_b.add_document(d["name"], render_pdf(d))
            tenants[b] = len(DOCUMENTS_B)

    users = 0
    for email, password, name, mems in DEMO_USERS:
        try:
            uid = auth.create_user(email, password, name)
            users += 1
        except AuthError:
            continue  # already present
        for brf_id, role in mems:
            if auth.get_tenant(brf_id) is not None:
                auth.add_membership(uid, brf_id, role)
    return {"tenants": tenants, "users": users}


def build_golden(store: Store, answerable_src: list | None = None, unanswerable_src: list | None = None) -> dict:
    """Locate every golden passage independently of the citation pipeline
    (fitz search_for) and fail loudly if any passage is unfindable."""
    if answerable_src is None:
        answerable_src = GOLDEN_ANSWERABLE
    if unanswerable_src is None:
        unanswerable_src = GOLDEN_UNANSWERABLE
    by_name: dict[str, str] = {m.name: m.id for m in store.documents.values()}
    answerable = []
    problems = []
    for i, qa in enumerate(answerable_src):
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
            {"id": f"u{i:02d}", "question": q} for i, q in enumerate(unanswerable_src)
        ],
    }


def _clean_legacy_layout(root: Path) -> None:
    """Remove the pre-tenant single-store layout under backend/data/."""
    import shutil

    for name in ("docs", "extract"):
        shutil.rmtree(root / name, ignore_errors=True)
    for name in ("documents.json", "settings.json"):
        (root / name).unlink(missing_ok=True)


def main() -> None:
    from app.auth import AuthStore
    from app.registry import TenantRegistry

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe all tenants and reseed")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    root = Path(args.data_root) if args.data_root else Path(__file__).resolve().parent.parent / "data"
    auth = AuthStore(root / "auth.db")
    registry = TenantRegistry(root, auth)

    if args.reset:
        for t in registry.list():
            registry.delete(t["brf_id"])
        _clean_legacy_layout(root)
    if registry.list():
        print(f"Det finns redan {len(registry.list())} föreningar — kör med --reset för att börja om.")
        sys.exit(1)

    seeded = seed_demo(registry, auth)
    eval_dir = Path(__file__).resolve().parent.parent / "eval"
    eval_dir.mkdir(exist_ok=True)

    store_a = registry.get("gjutformen-12")
    golden = build_golden(store_a)
    (eval_dir / "golden.json").write_text(json.dumps(golden, ensure_ascii=False, indent=2), "utf-8")
    print(f"Brf Gjutformen 12: {len(store_a.documents)} dokument, {len(store_a.chunks)} chunks; "
          f"golden {len(golden['answerable'])}+{len(golden['unanswerable'])} → eval/golden.json")

    store_b = registry.get("sjoutsikten-7")
    if store_b is not None:
        from scripts.seed_content_b import GOLDEN_ANSWERABLE_B, GOLDEN_UNANSWERABLE_B

        golden_b = build_golden(store_b, GOLDEN_ANSWERABLE_B, GOLDEN_UNANSWERABLE_B)
        (eval_dir / "golden_b.json").write_text(json.dumps(golden_b, ensure_ascii=False, indent=2), "utf-8")
        print(f"Brf Sjöutsikten 7: {len(store_b.documents)} dokument, {len(store_b.chunks)} chunks; "
              f"golden {len(golden_b['answerable'])}+{len(golden_b['unanswerable'])} → eval/golden_b.json")

    print(f"\nDemokonton ({seeded['users']} skapade):")
    for email, password, name, mems in DEMO_USERS:
        roles = ", ".join(f"{b}:{r}" for b, r in mems)
        print(f"  {email} / {password}  ({name}; {roles})")


if __name__ == "__main__":
    main()
