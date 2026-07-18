"""Pin the refusal-bucket classification in scripts/reality/refusal_buckets.py
— word-index containment (Bucket 1), chunk-string garble metrics (Bucket 2),
and the pure `classify` decision tree that picks between retrieval_miss /
extraction_garble / citation_emission. Synthetic fixtures only (PageData/Word/
Chunk built directly, plus one small in-memory table PDF via
tests/pdf_fixtures.py for the multi-span construction test) — no real corpus,
matching this folder's existing reality-script test convention (see
test_annual_reports.py, test_reality_fragment_facts.py).
"""

from __future__ import annotations

from app.answer import ask
from app.llm import FakeLLM
from app.schemas import Chunk, PageData, Word
from app.store import Store
from scripts.reality import common
from scripts.reality.refusal_buckets import (
    GARBLE_DISTANCE_TOKENS,
    GARBLE_INTERLEAVE_FOREIGN,
    chunk_contains_occurrence,
    classify,
    construct_multispan_fragments,
    garble_metrics,
    is_garbled,
    is_value_token,
    label_row_occurrences,
)
from tests.pdf_fixtures import build_pdf


def _word(text: str, x0: float, y0: float, x1: float, y1: float, *, block: int = 1, line: int = 1) -> Word:
    return Word(text=text, x0=x0, y0=y0, x1=x1, y1=y1, block=block, line=line)


def _chunk(doc_id: str, page: int, word_start: int, word_end: int, text: str) -> Chunk:
    return Chunk(
        id=f"{doc_id}:p{page}:{word_start}-{word_end}",
        document_id=doc_id,
        page=page,
        word_start=word_start,
        word_end=word_end,
        text=text,
    )


class TestIsValueToken:
    def test_digit_bearing_tokens_detected_generically(self):
        assert is_value_token("45") is True
        assert is_value_token("12,5") is True
        assert is_value_token("18%") is True
        assert is_value_token("-45") is True

    def test_non_digit_tokens_not_value(self):
        assert is_value_token("kr") is False
        assert is_value_token("räntekostnader") is False


class TestLabelRowOccurrences:
    def test_answer_bearing_row_captures_value_indices(self):
        words = [
            _word("Räntekostnader", 72, 100, 160, 112),
            _word("45", 165, 100, 185, 112),
            _word("000", 190, 100, 220, 112),
            _word("kr", 225, 100, 245, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)

        out = label_row_occurrences([page], "räntekostnader")

        assert len(out) == 1
        occ = out[0]
        assert occ["label_indices"] == [0]
        assert occ["value_indices"] == [1, 2]
        assert occ["answer_bearing"] is True

    def test_label_without_adjacent_value_not_answer_bearing(self):
        # A prose mention of the label term with no numeric value anywhere on
        # its own visual row — the "missing-row" (Bucket-1) shape at the
        # occurrence level: the label exists, but no fact is attached here.
        words = [
            _word("Räntekostnader", 72, 100, 160, 112),
            _word("regleras", 165, 100, 210, 112),
            _word("separat.", 215, 100, 260, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)

        out = label_row_occurrences([page], "räntekostnader")

        assert out[0]["answer_bearing"] is False
        assert out[0]["value_indices"] == []

    def test_value_in_a_different_block_same_y_band_still_counted(self):
        # Column-major extraction: the label lives in block 1, its value in
        # a SEPARATE block (2), sharing only the visual y-band — exactly the
        # layout that later produces Bucket-2 garbling once both land in one
        # retrieved chunk. Row scanning is over ALL page words by y-band, not
        # restricted to the label's own (block, line), so the value must
        # still be found.
        words = [
            _word("Soliditet", 72, 100, 140, 112, block=1, line=1),
            _word("62%", 400, 100, 430, 112, block=2, line=1),
        ]
        page = PageData(number=1, width=595, height=842, words=words)

        out = label_row_occurrences([page], "soliditet")

        assert out[0]["value_indices"] == [1]
        assert out[0]["answer_bearing"] is True


class TestChunkContainsOccurrence:
    def test_label_and_value_both_inside_chunk_range(self):
        chunk = _chunk("d1", 1, 0, 3, "x")
        occ = {"page": 1, "label_indices": [0], "value_indices": [2]}
        assert chunk_contains_occurrence(chunk, occ) is True

    def test_label_row_straddling_chunk_boundary_not_contained(self):
        # The label's OWN words span page-indices [3, 4] but the chunk only
        # covers up to word_end=3 — half the label sits outside the
        # retrieved chunk. Containment requires EVERY label word (not just
        # some) inside the chunk's own range.
        chunk = _chunk("d1", 1, 0, 3, "x")
        occ = {"page": 1, "label_indices": [3, 4], "value_indices": [3]}
        assert chunk_contains_occurrence(chunk, occ) is False

    def test_value_straddling_chunk_boundary_still_contained_if_another_value_is_inside(self):
        chunk = _chunk("d1", 1, 0, 3, "x")
        occ = {"page": 1, "label_indices": [0], "value_indices": [3, 4]}
        assert chunk_contains_occurrence(chunk, occ) is True

    def test_different_page_never_contains(self):
        chunk = _chunk("d1", 2, 0, 3, "x")
        occ = {"page": 1, "label_indices": [0], "value_indices": [1]}
        assert chunk_contains_occurrence(chunk, occ) is False

    def test_no_value_indices_never_contains(self):
        chunk = _chunk("d1", 1, 0, 3, "x")
        occ = {"page": 1, "label_indices": [0], "value_indices": []}
        assert chunk_contains_occurrence(chunk, occ) is False


class TestGarbleMetrics:
    def _row_page(self, texts: list[str]) -> PageData:
        words = []
        x = 72.0
        for t in texts:
            words.append(_word(t, x, 100, x + 20, 112))
            x += 25
        return PageData(number=1, width=595, height=842, words=words)

    def test_clean_adjacent_row_not_garbled(self):
        # label at 0, a couple of filler words, value run at [3, 4]: low
        # token distance, no foreign-row interleave, no split -> the
        # Bucket-3 (citation_emission) shape.
        page = self._row_page(["Räntekostnader", "för", "verksamhetsåret", "45", "000", "kr"])
        chunk = _chunk("d1", 1, 0, 5, " ".join(w.text for w in page.words))
        occ = label_row_occurrences([page], "räntekostnader")[0]

        metrics = garble_metrics(chunk, page, occ)

        assert metrics["token_distance"] <= GARBLE_DISTANCE_TOKENS
        assert metrics["interleave_foreign_count"] == 0
        assert metrics["value_split"] is False
        assert is_garbled(metrics) is False

    def test_column_major_interleave_is_garbled(self):
        # This row's own label (index 0) and value (last index) sit far apart
        # in word-index/token order because many OTHER rows' words (a
        # different y-band -> "foreign" by word-index provenance) sit between
        # them in the chunk's own text — the column-major extraction garble.
        row_label = _word("Soliditet", 72, 100, 140, 112, block=1, line=1)
        other_rows = [
            _word(f"Rad{i}", 72, 200 + i * 12, 140, 212 + i * 12, block=1, line=2 + i) for i in range(10)
        ]
        row_value = _word("62%", 400, 100, 430, 112, block=2, line=1)
        page = PageData(number=1, width=595, height=842, words=[row_label, *other_rows, row_value])
        chunk_text = " ".join(w.text for w in page.words)
        chunk = _chunk("d1", 1, 0, len(page.words) - 1, chunk_text)
        occ = label_row_occurrences([page], "soliditet")[0]

        metrics = garble_metrics(chunk, page, occ)

        assert metrics["interleave_foreign_count"] > GARBLE_INTERLEAVE_FOREIGN
        assert is_garbled(metrics) is True

    def test_value_token_split_is_garbled(self):
        # A value Word whose own extracted text already contains embedded
        # whitespace (an extraction quirk) does not survive as ONE token in
        # the chunk's plain-text string -> value_split flags it regardless
        # of how close it sits.
        label = _word("Årsavgift", 72, 100, 140, 112)
        value = _word("1 234", 145, 100, 200, 112)  # one Word, internal space
        page = PageData(number=1, width=595, height=842, words=[label, value])
        chunk = _chunk("d1", 1, 0, 1, " ".join(w.text for w in [label, value]))
        occ = label_row_occurrences([page], "årsavgift")[0]

        metrics = garble_metrics(chunk, page, occ)

        assert metrics["value_split"] is True
        assert is_garbled(metrics) is True


class TestClassify:
    """The pure bucket-decision tree, exercised with synthetic occurrences
    and a synthetic retrieved-chunk list — no Store, no retrieval call."""

    def test_missing_row_anywhere_is_bucket_1(self):
        words = [_word("Räntekostnader", 72, 100, 160, 112)]  # no adjacent value anywhere
        page = PageData(number=1, width=595, height=842, words=words)
        retrieved = [_chunk("d1", 1, 0, 0, "Räntekostnader")]

        result = classify([page], retrieved, ["räntekostnader"])

        assert result["bucket"] == 1
        assert result["bucket_label"] == "retrieval_miss"

    def test_answer_bearing_row_never_retrieved_is_bucket_1(self):
        words = [_word("Räntekostnader", 72, 100, 160, 112), _word("45", 165, 100, 185, 112)]
        page = PageData(number=1, width=595, height=842, words=words)
        # Retrieved chunk is a DIFFERENT page entirely.
        retrieved = [_chunk("d1", 2, 0, 5, "något annat")]

        result = classify([page], retrieved, ["räntekostnader"])

        assert result["bucket"] == 1
        assert result["answer_bearing_pages"] == [1]
        assert result["retrieved_pages"] == [2]

    def test_clean_contained_row_is_bucket_3(self):
        words = [
            _word("Räntekostnader", 72, 100, 160, 112),
            _word("45", 165, 100, 185, 112),
            _word("000", 190, 100, 220, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)
        retrieved = [_chunk("d1", 1, 0, 2, "Räntekostnader 45 000")]

        result = classify([page], retrieved, ["räntekostnader"])

        assert result["bucket"] == 3
        assert result["bucket_label"] == "citation_emission"

    def test_garbled_contained_row_is_bucket_2(self):
        label = _word("Årsavgift", 72, 100, 140, 112)
        value = _word("1 234", 145, 100, 200, 112)  # value-token split
        page = PageData(number=1, width=595, height=842, words=[label, value])
        retrieved = [_chunk("d1", 1, 0, 1, "Årsavgift 1 234")]

        result = classify([page], retrieved, ["årsavgift"])

        assert result["bucket"] == 2
        assert result["bucket_label"] == "extraction_garble"


class TestMultiSpanProbeConstruction:
    """End-to-end: a synthetic table chunk, hand-constructed [label, value]
    fragments, a scripted FakeLLM citing them on the correctly-retrieved
    alias -> Resolved, >=2 rects (one per fragment's own bounding box)."""

    def test_construction_resolves_with_two_rects(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        pdf = build_pdf([[("Räntekostnader för verksamhetsåret 45 000 kr", 72, 100)]])
        meta = store.add_document("Arsredovisning.pdf", pdf)
        assert meta.source == "digital"

        pages = store.pages[meta.id]
        page = pages[0]
        occ = label_row_occurrences([page], "räntekostnader")[0]
        assert occ["answer_bearing"] is True

        chunk = next(c for c in store.chunks.values() if c.document_id == meta.id)
        assert chunk_contains_occurrence(chunk, occ)
        metrics = garble_metrics(chunk, page, occ)
        assert is_garbled(metrics) is False  # clean fixture, sanity check

        fragments = construct_multispan_fragments(page, chunk, occ, metrics)
        assert fragments is not None
        label_frag, value_frag = fragments
        assert label_frag == "Räntekostnader"
        assert value_frag == "45 000"

        question = "Hur stora var föreningens räntekostnader under året?"
        alias, _hits = common.alias_for_chunk(store, question, chunk.id)
        assert alias is not None

        fake = FakeLLM(
            [{"answer": "Se citerade fragment.", "citations": [{"chunk_id": alias, "quotes": [label_frag, value_frag]}], "insufficient_data": False}]
        )
        resp = ask(store, question, provider=fake)

        assert not resp.refusal
        assert len(resp.citations) == 1
        cit = resp.citations[0]
        assert cit.quotes == [label_frag, value_frag]
        assert len(cit.rects) >= 2

    def test_construction_impossible_when_value_run_crosses_chunk_boundary(self):
        # The value's own word index sits OUTSIDE the chunk's word range —
        # construction must report impossible, not silently fabricate.
        words = [
            _word("Räntekostnader", 72, 100, 160, 112),
            _word("45", 165, 100, 185, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)
        occ = label_row_occurrences([page], "räntekostnader")[0]
        chunk = _chunk("d1", 1, 0, 0, "Räntekostnader")  # excludes word index 1 (the value)
        metrics = garble_metrics(_chunk("d1", 1, 0, 1, "Räntekostnader 45"), page, occ)

        fragments = construct_multispan_fragments(page, chunk, occ, metrics)

        assert fragments is None
