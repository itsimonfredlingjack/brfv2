"""Enrichment is applied at index-rebuild time (real Store path), and the frozen
display/citation surface is untouched. Synthetic table PDF only (data discipline)."""

from __future__ import annotations

from app.store import Store
from tests.pdf_fixtures import build_pdf


def _table_pdf() -> bytes:
    # Heading FIRST (block/word index 0 -> the single chunk inherits it), taller
    # (fontsize 18) so the height detector fires; year line LAST so "2025" is
    # never adjacent to the heading in the extracted word stream.
    return build_pdf([[
        ("Resultaträkning", 72, 100, 18),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Årsredovisning 2025 räkenskapsåret 2025", 72, 180),
    ]])


class TestStoreEnrichment:
    def test_search_text_set_and_display_text_frozen(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)
        # enriched search string carries year + section heading...
        assert row.search_text is not None
        assert "2025" in row.search_text and "Resultaträkning" in row.search_text
        # ...but the frozen text is unchanged and is what retrieval returns.
        assert row.search_text.endswith(row.text)
        hits = store.index.search("Räntekostnader", weight=0.5, candidates=50,
                                  top_k=10, min_confidence=0.0)
        hit = next(h for h in hits if h.chunk_id == row.id)
        assert hit.text == row.text  # frozen, no enrichment leak

    def test_document_name_is_searchable_but_never_citable(self, tmp_path):
        """Which HANDLING a passage belongs to is usually not written in the
        passage — the clause says "Parterna", not which contract it is. A
        board's archive holds several of the same kind, so without the name
        in the index the ranking cannot tell them apart. Measured on a real
        archive: the top hit came from the wrong document in 10 of 11
        questions, and a search for a word that exists only in a filename
        landed in an unrelated document.

        The name goes into the index only. It must never reach the model or
        a citation, because it is not text on the page and could not be
        verified against `PageData.words`.
        """
        store = Store(data_dir=tmp_path)
        meta = store.add_document("Snoerojningsavtal_Vinterservice_2024.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)

        # Non-vacuity: the word must exist ONLY in the name, or the search
        # below would succeed with no enrichment at all.
        assert "Vinterservice" not in row.text
        assert "Vinterservice" in (row.search_text or "")
        # Separators become spaces, so the name contributes words a board types.
        assert "Snoerojningsavtal Vinterservice 2024" in (row.search_text or "")
        assert ".pdf" not in (row.search_text or "")

        hits = store.index.search("Vinterservice", weight=0.5, candidates=50,
                                  top_k=5, min_confidence=0.0)
        assert hits and hits[0].document_id == meta.id, "namnet nådde aldrig indexet"
        assert "Vinterservice" not in hits[0].text, "namnet läckte till det citerbara utdraget"

    def test_disabled_toggle_leaves_search_text_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRF_ENRICH", "0")
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)
        assert row.search_text is None
