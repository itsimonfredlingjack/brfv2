"""Pin the deterministic logic in scripts/reality/common.py: payload-window
derivation, chunk sampling, span corruption, retrieval-order alias mapping,
and the independent rect-vs-quote verdict. Synthetic fixtures only — no real
corpus, matching the reality-script convention (see ocr_reality.py, digital_
reality.py) of never touching real documents from the offline test suite.
"""

from __future__ import annotations

from app.schemas import Word
from app.store import Store
from scripts.reality.common import (
    alias_for_chunk,
    corrupt_span,
    independent_rect_verdict,
    multi_span_payload,
    sample_chunks,
    single_span_payload,
)
from tests.pdf_fixtures import build_pdf


class TestSingleSpanPayload:
    def test_too_short_chunk_yields_none(self):
        assert single_span_payload("ett två tre fyra fem") is None  # 5 words < min 6

    def test_exact_minimum_uses_the_whole_chunk(self):
        text = "ett två tre fyra fem sex"  # exactly 6 words
        assert single_span_payload(text) == text

    def test_long_chunk_caps_at_sixteen_words(self):
        words = [f"ord{i}" for i in range(1, 21)]  # 20 words
        payload = single_span_payload(" ".join(words))
        assert payload == " ".join(words[:16])
        assert len(payload.split()) == 16


class TestMultiSpanPayload:
    def test_too_short_chunk_yields_none(self):
        # needs span_len*2 + gap = 4+3+4 = 11 words minimum
        assert multi_span_payload(" ".join(f"w{i}" for i in range(10))) is None

    def test_exact_minimum_splits_into_two_disjoint_windows(self):
        words = [f"w{i}" for i in range(11)]  # exactly enough
        result = multi_span_payload(" ".join(words))
        assert result == ("w0 w1 w2 w3", "w7 w8 w9 w10")

    def test_spans_are_disjoint_with_a_real_gap(self):
        words = [f"w{i}" for i in range(20)]
        first, second = multi_span_payload(" ".join(words))
        first_idxs = {int(w[1:]) for w in first.split()}
        second_idxs = {int(w[1:]) for w in second.split()}
        assert first_idxs.isdisjoint(second_idxs)
        assert min(second_idxs) - max(first_idxs) >= 4  # >= gap(3) + 1


class TestSampleChunks:
    def test_fewer_than_n_returns_all(self):
        chunks = list(range(5))
        assert sample_chunks(chunks, n=10) == chunks

    def test_more_than_n_returns_n_evenly_spaced_unique(self):
        chunks = list(range(23))
        sampled = sample_chunks(chunks, n=10)
        assert len(sampled) == 10
        assert sampled == sorted(set(sampled))  # unique and in order
        assert sampled[0] == 0  # deterministic: starts at the first chunk

    def test_deterministic_across_calls(self):
        chunks = list(range(37))
        assert sample_chunks(chunks, n=7) == sample_chunks(chunks, n=7)


class TestCorruptSpan:
    def test_flips_one_alphabetic_character(self):
        original = "Årsavgiften fastställs"
        corrupted = corrupt_span(original)
        assert corrupted != original
        assert len(corrupted) == len(original)

    def test_idempotent_shape_on_repeated_calls_differs_from_original(self):
        # corrupting twice must not accidentally restore the original
        original = "styrelsen sammanträder"
        once = corrupt_span(original)
        twice = corrupt_span(once)
        assert twice != original

    def test_falls_back_to_truncation_when_no_letters(self):
        assert corrupt_span("12345") == "1234"

    def test_single_char_non_letter_appends_marker(self):
        assert corrupt_span("5") == "5#"


class TestIndependentRectVerdict:
    def _words(self, texts: list[str], y0=100.0) -> list[Word]:
        out = []
        x = 0.0
        for t in texts:
            w = 10.0 * len(t)
            out.append(Word(text=t, x0=x, y0=y0, x1=x + w, y1=y0 + 12.0, block=1, line=1))
            x += w + 5.0
        return out

    def test_exact_match_when_rect_covers_exactly_the_span_words(self):
        words = self._words(["Årsavgiften", "fastställs", "till", "500", "kr"])
        rect = [words[0].x0, words[0].y0, words[-1].x1, words[-1].y1]
        verdict = independent_rect_verdict(words, [rect], ["Årsavgiften fastställs till 500 kr"])
        assert verdict == "exact"

    def test_invariant_violation_when_span_not_verbatim_on_page(self):
        words = self._words(["Årsavgiften", "fastställs", "till", "500", "kr"])
        rect = [words[0].x0, words[0].y0, words[-1].x1, words[-1].y1]
        verdict = independent_rect_verdict(words, [rect], ["Årsavgiften är gratis"])
        assert verdict.startswith("INVARIANT-VIOLATION")

    def test_superset_when_rect_spills_over_one_extra_word(self):
        words = self._words(["Årsavgiften", "fastställs", "till", "500", "kr"])
        rect = [words[0].x0, words[0].y0, words[-1].x1, words[-1].y1]  # covers all 5 words
        verdict = independent_rect_verdict(words, [rect], ["Årsavgiften fastställs till"])
        assert verdict == "superset(edge-spill)"


class TestAliasForChunk:
    def _store(self, tmp_path) -> Store:
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        return store

    def test_sole_chunk_gets_k1(self, tmp_path):
        store = self._store(tmp_path)
        pdf = build_pdf([[("Styrelsen sammanträder varje månad i februari.", 72, 100)]])
        meta = store.add_document("A.pdf", pdf)
        chunk = next(c for c in store.chunks.values() if c.document_id == meta.id)

        alias, hits = alias_for_chunk(store, chunk.text, chunk.id)
        assert alias == "K1"
        assert hits and hits[0].chunk_id == chunk.id

    def test_unknown_chunk_id_is_a_retrieval_miss(self, tmp_path):
        store = self._store(tmp_path)
        pdf = build_pdf([[("Styrelsen sammanträder varje månad.", 72, 100)]])
        store.add_document("A.pdf", pdf)

        alias, hits = alias_for_chunk(store, "Styrelsen sammanträder varje månad", "no-such-chunk-id")
        assert alias is None
        assert hits  # retrieval still ran; the target just isn't among the hits

    def test_outranked_chunk_is_a_genuine_retrieval_miss_under_narrow_topk(self, tmp_path):
        store = self._store(tmp_path)
        pdf_a = build_pdf([[("Parkeringsavgiften är femhundra kronor för medlemmar med bil.", 72, 100)]])
        pdf_b = build_pdf([[("Sophanteringen sker varje tisdag och fredag under sommaren.", 72, 100)]])
        meta_a = store.add_document("A.pdf", pdf_a)
        meta_b = store.add_document("B.pdf", pdf_b)
        chunk_a = next(c for c in store.chunks.values() if c.document_id == meta_a.id)
        chunk_b = next(c for c in store.chunks.values() if c.document_id == meta_b.id)
        # Narrow the field to exactly one hit so an outranked chunk is
        # provably absent from it, not just low-ranked.
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0, "topK": 1}))

        query = chunk_a.text  # an exact match for A's own chunk
        alias_a, hits_a = alias_for_chunk(store, query, chunk_a.id)
        alias_b, _hits_b = alias_for_chunk(store, query, chunk_b.id)

        assert alias_a == "K1"
        assert len(hits_a) == 1
        assert alias_b is None  # B's chunk is outranked, not just absent-by-id
