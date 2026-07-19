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
