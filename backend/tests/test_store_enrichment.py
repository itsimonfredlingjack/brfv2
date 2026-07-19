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

    def test_disabled_toggle_leaves_search_text_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRF_ENRICH", "0")
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)
        assert row.search_text is None
