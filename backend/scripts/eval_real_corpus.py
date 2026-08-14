"""Karakteriserar en VERKLIG förenings arkiv: läsbarhet efter OCR, och glapp.

Två frågor, båda om villkor C i docs/evidence/fan-out-mvp-beslut.md.

**1. Är läsbarheten fortfarande den bindande gränsen?** Mätningen 2026-08-12
(`d32e606`) räknade textlager och fann att sju av nio handlingar saknade ett,
och drog slutsatsen att OCR — inte sökstrategin — var det som stod i vägen.
OCR-vägen kopplades in efter den mätningen (`app/store.py` → `app/ocr.py`).
`--volym` kör den RIKTIGA ingestionsvägen och mäter vad som faktiskt kommer ut.

**2. Finns ordförrådsglappet i arkivet?** `--glapp` tar en markdown-tabell med
källbelagda par *styrelsens ord → dokumentets ord* och mäter, per par, vad
vardera sidan hämtar ur arkivet.

`--glapp` är en SCREENING, inte villkor C. Villkoret kräver att vinsten
reproduceras på verkliga fall, och ett fall kräver ett utpekat svarsstycke —
alltså att någon läser handlingarna. Screeningen **underdetekterar dessutom
systematiskt**: r01:s verkliga skada var att en distraktor matchade frågans ord
perfekt utan att besvara den, och ett confidence-mått kan inte skilja det från
en träff. Ett högt värde i `s-konf` är därför inte bevis för att rätt stycke
hittades. Negativa utfall här är svaga; de positiva är kandidater.

Skriver ENBART SIFFROR. Ingen text ur arkivet, inga filnamn — handlingarna
identifieras med en bokstav i namnordning. Arkivet får aldrig committas, och
sökvägen är därför ett argument, aldrig inbakad.

    uv run python -m scripts.eval_real_corpus --archive /sökväg/till/arkivet --volym
    uv run python -m scripts.eval_real_corpus --archive /sökväg --glapp par.md
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # noqa: E402

from app.schemas import Settings  # noqa: E402
from app.store import Store  # noqa: E402

# Tokens som räknas som "ordlika": bokstäver, eventuellt med bindestreck. Måttet
# är grovt med flit — det skiljer läsbar text från OCR-grums, inte bra svenska
# från dålig. Jämför alltid mot de DIGITALA handlingarnas egen andel i samma
# körning; en textlagerandel är den enda rimliga baslinjen för vad "bra" är.
WORD_RE = re.compile(r"^[A-Za-zÅÄÖåäöÉé][A-Za-zÅÄÖåäöÉé\-]*$")


def load_pairs(path: Path) -> list[tuple[str, str]]:
    """Par ur en markdown-tabell: kolumn 1 = styrelsens ord, 2 = dokumentets."""
    pairs = []
    for line in path.read_text("utf-8").splitlines():
        if not line.startswith("| **"):
            continue
        cols = [re.sub(r"\*+", "", c).strip() for c in line.strip("|").split("|")]
        if len(cols) >= 2 and cols[0] and cols[1] and not cols[0].startswith(":"):
            pairs.append((cols[0], cols[1]))
    return pairs


def build(archive: Path, data_dir: Path) -> tuple[Store, dict[str, str]]:
    store = Store(data_dir=data_dir)
    store.update_settings(Settings())
    for path in sorted(archive.glob("*.pdf")):
        store.add_document(path.name, path.read_bytes())
    letters = {
        m.id: chr(ord("A") + i)
        for i, m in enumerate(sorted(store.documents.values(), key=lambda m: m.name))
    }
    return store, letters


def volume(archive: Path) -> None:
    pdfs = sorted(archive.glob("*.pdf"))
    print(f"\n### Läsbarhet — {len(pdfs)} handlingar\n")
    print("| dok | sidor | ord i textlager | ord efter ingestion | ord/sida | ordlika | sek | källa |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for i, path in enumerate(pdfs):
        letter = chr(ord("A") + i)
        data = path.read_bytes()
        doc = fitz.open(stream=data, filetype="pdf")
        pages = doc.page_count
        digital = sum(len(p.get_text("words")) for p in doc)

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(data_dir=Path(tmp))
            store.update_settings(Settings())
            t0 = time.time()
            try:
                meta = store.add_document(path.name, data)
            except Exception as exc:  # noqa: BLE001
                print(f"| {letter} | {pages} | {digital} | FEL | | | {time.time()-t0:.0f} | "
                      f"{type(exc).__name__} |")
                continue
            elapsed = time.time() - t0
            tokens = [t for c in store.chunks.values() for t in c.text.split()]
            wordlike = sum(1 for t in tokens if WORD_RE.match(t.strip(".,;:()[]§")))
            print(f"| {letter} | {pages} | {digital} | {len(tokens)} | "
                  f"{len(tokens)/max(pages,1):.0f} | {wordlike/max(len(tokens),1):.0%} | "
                  f"{elapsed:.0f} | {getattr(meta, 'source', '?')} |")


def gap(archive: Path, pairs_md: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store, letters = build(archive, Path(tmp))
        s = store.settings

        def top(q: str) -> tuple[float, str]:
            hits = store.index.search(q, weight=s.searchWeighting / 100.0,
                                      candidates=s.candidateCount, top_k=1, min_confidence=0.0)
            return (hits[0].confidence, letters.get(hits[0].document_id, "?")) if hits else (0.0, "-")

        pairs = load_pairs(pairs_md)
        if not pairs:
            print(f"inga par lästa ur {pairs_md} — kontrollera tabellformatet", file=sys.stderr)
            return
        print(f"\n### Ordförrådsglapp — screening, {len(store.documents)} handlingar, "
              f"{len(store.chunks)} chunkar, minRelevance={s.minRelevance}\n")
        print("| # | s-konf | d-konf | dok | r01-mönster | styrelsens ord |")
        print("|---:|---:|---:|---|---|---|")
        gaps = 0
        for i, (board, doc) in enumerate(pairs, 1):
            sc, sd = top(board)
            dc, dd = top(doc)
            is_gap = sc < s.minRelevance <= dc
            gaps += is_gap
            print(f"| {i} | {sc:.3f} | {dc:.3f} | {sd}/{dd} | {'**JA**' if is_gap else ''} | {board[:46]} |")
        print(f"\n**{gaps} av {len(pairs)}** par visar r01:s mönster (styrelsens ord under "
              f"tröskeln, dokumentets över). Se modulens varning: screeningen underdetekterar.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Karakterisera ett verkligt arkiv (villkor C).")
    ap.add_argument("--archive", required=True, type=Path, help="katalog med PDF:er; committas aldrig")
    ap.add_argument("--volym", action="store_true", help="läsbarhet efter ingestion/OCR")
    ap.add_argument("--glapp", type=Path, metavar="PAR.md", help="markdown-tabell med ordpar")
    args = ap.parse_args()
    if not args.archive.is_dir():
        print(f"saknar katalogen {args.archive}", file=sys.stderr)
        return 2
    if not args.volym and not args.glapp:
        ap.error("välj --volym och/eller --glapp")
    if args.volym:
        volume(args.archive)
    if args.glapp:
        gap(args.archive, args.glapp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
