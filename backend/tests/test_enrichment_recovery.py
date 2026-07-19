"""Pin the deterministic rank finder: it must report the rank of the retrieved
chunk that CONTAINS the answer-bearing row (word-index containment), not merely
a chunk on the right page. Synthetic table PDF only."""

from __future__ import annotations

from app.store import Store
from scripts.reality.enrichment_recovery import true_row_rank
from tests.pdf_fixtures import build_pdf


def _doc() -> bytes:
    # Two rows in one small table; only the räntekostnader row is answer-bearing
    # for the interest question.
    return build_pdf([[
        ("Resultaträkning", 72, 100),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Driftskostnader 2 000 000", 72, 180),
    ]])


def _decoy_doc() -> bytes:
    # Page 1 is a DECOY: the query's label word repeated with no numeric
    # value on any line, so it scores highly for the query (term frequency)
    # but is NOT answer-bearing (no adjacent number) and must be skipped by
    # the rank-finding loop. Page 2 holds the real answer-bearing row. Chunks
    # never cross page boundaries, so this is guaranteed to be >= 2 chunks —
    # the decoy must out-rank the real row for this test to be non-tautological
    # (it pins the loop actually walking past a non-containing hit, rather
    # than a stub like `return 1 if occ else None` also passing).
    return build_pdf([
        [("Räntekostnader räntekostnader räntekostnader räntekostnader räntekostnader", 72, 100)],
        [
            ("Resultaträkning", 72, 100, 18),
            ("Räntekostnader 1 234 567", 72, 140),
        ],
    ])


class TestTrueRowRank:
    def test_finds_rank_of_containing_chunk(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        meta = store.add_document("ar.pdf", _doc())
        rank = true_row_rank(store, meta.id,
                             "Hur stora var föreningens räntekostnader under året?",
                             ["räntekostnader"])
        assert rank == 1  # single chunk contains the answer-bearing row

    def test_none_when_no_answer_bearing_row(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _doc())
        rank = true_row_rank(store, meta.id, "Vilken är soliditeten?", ["soliditet"])
        assert rank is None

    def test_skips_decoy_chunk_to_find_answer_bearing_rank(self, tmp_path):
        # Non-tautological: exercises the rank-finding loop actually walking
        # past a higher-ranked, non-containing chunk (the label-only decoy on
        # page 1) to land on the answer-bearing chunk (page 2). Observed rank
        # is 2 out of 2 chunks (one chunk per page; chunks never cross page
        # boundaries) — the decoy's repeated label word out-ranks the real
        # row for this query, as intended.
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        meta = store.add_document("ar.pdf", _decoy_doc())
        rank = true_row_rank(store, meta.id,
                             "Hur stora var föreningens räntekostnader under året?",
                             ["räntekostnader"])
        assert rank == 2  # pinned observed value
        # Anti-tautology guard: fails if true_row_rank degenerated into
        # `return 1 if occ else None` (i.e. stopped actually finding rank).
        assert rank >= 2

    def test_none_when_label_present_without_adjacent_value(self, tmp_path):
        # Covers the answer_bearing=False filter branch: the label word
        # appears, but with no numeric value on its own visual line, so
        # label_row_occurrences finds an occurrence that _answer_bearing_
        # occurrences filters OUT. This differs from
        # test_none_when_no_answer_bearing_row, where the label is absent
        # from the document entirely.
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        prose_doc = build_pdf([[
            ("Föreningens soliditet diskuteras i förvaltningsberättelsen", 72, 100),
        ]])
        meta = store.add_document("ar.pdf", prose_doc)
        rank = true_row_rank(store, meta.id,
                             "Hur stor är föreningens soliditet i procent?",
                             ["soliditet"])
        assert rank is None
