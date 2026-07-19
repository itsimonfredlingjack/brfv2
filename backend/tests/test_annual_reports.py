"""Pin the deterministic row-landing check in scripts/reality/annual_reports.py
— the geometric heart of the annual-report table validation: does a verified
citation's highlight actually sit on the SAME table row as the label term the
question asked about, not merely somewhere on the right page. Synthetic
fixtures only (PageData/Word built directly, plus one small in-memory table
PDF via tests/pdf_fixtures.py) — no real corpus, matching this folder's
existing reality-script test convention (see test_reality_common.py,
test_reality_fragment_facts.py) of never touching real documents from the
offline test suite.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from app.answer import ask
from app.llm import FakeLLM
from app.schemas import PageData, Word
from app.store import Store
from scripts.reality import common
from scripts.reality.annual_reports import (
    _process_document,
    doc_slug,
    enforce_no_external_connections,
    find_label_line_occurrences,
    row_landing_verdict,
)
from tests.pdf_fixtures import build_pdf


def _word(text: str, x0: float, y0: float, x1: float, y1: float, *, block: int = 1, line: int = 1) -> Word:
    return Word(text=text, x0=x0, y0=y0, x1=x1, y1=y1, block=block, line=line)


class TestFindLabelLineOccurrences:
    def test_multi_word_label_matched_across_adjacent_words_on_one_line(self):
        # A table row: label words in one (block, line) group, a value word
        # further along the same visual line (different x, same block/line).
        words = [
            _word("Avsättning", 72, 100, 130, 112),
            _word("yttre", 135, 100, 168, 112),
            _word("underhåll", 172, 100, 240, 112),
            _word("500", 320, 100, 340, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)

        out = find_label_line_occurrences([page], "yttre underhåll")

        assert len(out) == 1
        assert out[0]["page"] == 1
        assert out[0]["y0"] == 100
        assert out[0]["y1"] == 112

    def test_diacritic_and_case_folding(self):
        # Page word is capitalized/accented; the label query is lowercase —
        # app.normalize.norm_token must fold both to the same canonical form.
        words = [_word("Årsavgift", 72, 100, 150, 112)]
        page = PageData(number=1, width=595, height=842, words=words)

        out = find_label_line_occurrences([page], "årsavgift")

        assert len(out) == 1

    def test_no_occurrence_when_label_absent(self):
        words = [_word("Föreningen", 72, 100, 150, 112)]
        page = PageData(number=1, width=595, height=842, words=words)

        assert find_label_line_occurrences([page], "soliditet") == []

    def test_words_not_adjacent_on_the_line_do_not_match(self):
        # "yttre" and "underhåll" appear on the SAME line but with an
        # unrelated word wedged between them — not a genuine multi-word
        # label occurrence.
        words = [
            _word("yttre", 72, 100, 105, 112),
            _word("och", 110, 100, 130, 112),
            _word("inre", 135, 100, 165, 112),
            _word("underhåll", 170, 100, 240, 112),
        ]
        page = PageData(number=1, width=595, height=842, words=words)

        assert find_label_line_occurrences([page], "yttre underhåll") == []

    def test_occurrences_on_multiple_pages_all_returned(self):
        p1 = PageData(number=1, width=595, height=842, words=[_word("Soliditet", 72, 100, 150, 112)])
        p2 = PageData(number=2, width=595, height=842, words=[_word("Soliditet", 72, 200, 150, 212)])

        out = find_label_line_occurrences([p1, p2], "soliditet")

        assert sorted(o["page"] for o in out) == [1, 2]


class TestRowLandingVerdict:
    def test_rect_overlapping_the_label_row_lands_true(self):
        words = [_word("Räntekostnader", 72, 100, 160, 112)]
        pages = [PageData(number=1, width=595, height=842, words=words)]
        rect = [80.0, 102.0, 300.0, 111.0]  # inside the label's own row band

        verdict = row_landing_verdict(pages, ["räntekostnader"], cited_page=1, rects=[rect])

        assert verdict == {"lands_on_label_row": True, "label_pages": [1], "cited_page": 1}

    def test_rect_on_a_different_row_lands_false(self):
        words = [_word("Räntekostnader", 72, 100, 160, 112)]
        pages = [PageData(number=1, width=595, height=842, words=words)]
        rect = [80.0, 300.0, 300.0, 312.0]  # far below the label's row, well outside tolerance

        verdict = row_landing_verdict(pages, ["räntekostnader"], cited_page=1, rects=[rect])

        assert verdict["lands_on_label_row"] is False
        assert verdict["label_pages"] == [1]

    def test_rect_just_within_half_line_tolerance_lands_true(self):
        # Row height 12pt -> tolerance = 6pt. A rect starting exactly at the
        # padded lower edge of the band must still count as landing.
        words = [_word("Soliditet", 72, 100, 140, 112)]
        pages = [PageData(number=1, width=595, height=842, words=words)]
        rect = [80.0, 117.0, 300.0, 125.0]  # y0=117 <= band upper edge (118)

        verdict = row_landing_verdict(pages, ["soliditet"], cited_page=1, rects=[rect])

        assert verdict["lands_on_label_row"] is True

    def test_label_on_a_different_page_lands_false(self):
        words = [_word("Räntekostnader", 72, 100, 160, 112)]
        pages = [
            PageData(number=1, width=595, height=842, words=[]),
            PageData(number=2, width=595, height=842, words=words),
        ]
        rect = [80.0, 102.0, 300.0, 111.0]

        # Cited page 1 (no label occurrence there); the label only occurs
        # on page 2 — must not land, but label_pages must still report [2]
        # so a reader can tell "wrong page" from "wrong row".
        verdict = row_landing_verdict(pages, ["räntekostnader"], cited_page=1, rects=[rect])

        assert verdict["lands_on_label_row"] is False
        assert verdict["label_pages"] == [2]

    def test_any_of_multiple_labels_can_land(self):
        words = [_word("Fastighetslån", 72, 200, 160, 212)]
        pages = [PageData(number=1, width=595, height=842, words=words)]
        rect = [80.0, 202.0, 300.0, 211.0]

        verdict = row_landing_verdict(
            pages, ["kreditinstitut", "fastighetslån"], cited_page=1, rects=[rect]
        )

        assert verdict["lands_on_label_row"] is True
        assert verdict["label_pages"] == [1]

    def test_no_occurrences_anywhere_lands_false_with_empty_label_pages(self):
        pages = [PageData(number=1, width=595, height=842, words=[])]
        rect = [80.0, 102.0, 300.0, 111.0]

        verdict = row_landing_verdict(pages, ["soliditet"], cited_page=1, rects=[rect])

        assert verdict == {"lands_on_label_row": False, "label_pages": [], "cited_page": 1}


class TestDocSlug:
    def test_folder_relative_path_becomes_metric_safe_slug(self):
        assert doc_slug("hsb-perrongen/2024_hsb.pdf") == "hsb-perrongen_2024_hsb"
        assert doc_slug("rb-lycksaligheten/2025.pdf") == "rb-lycksaligheten_2025"

    def test_bare_filename_without_parent_dir(self):
        assert doc_slug("2025.pdf") == "2025"


class TestEnforceNoExternalConnections:
    def test_empty_log_does_not_raise(self):
        assert enforce_no_external_connections([]) is None

    def test_allowed_only_log_does_not_raise(self):
        # A real LLM-endpoint connection is expected and allowed here —
        # unlike common.assert_zero_connections, a nonzero allowed total
        # must NOT hard-fail this script.
        log = [{"host": "127.0.0.1", "port": 11434, "allowed": True}]
        assert enforce_no_external_connections(log) is None

    def test_external_connection_hard_fails(self):
        log = [
            {"host": "127.0.0.1", "port": 11434, "allowed": True},
            {"host": "evil.example.com", "port": 443, "allowed": False},
        ]
        with pytest.raises(SystemExit, match="evil.example.com:443"):
            enforce_no_external_connections(log)


class TestEndToEndRowLanding:
    """A synthetic table PDF, a scripted FakeLLM citation quoting the
    CORRECT row -> verified + lands_on_label_row True; the same store with a
    citation quoting a DIFFERENT row of the same chunk -> verified but
    lands_on_label_row False. Proves the check discriminates, not just
    confirms."""

    def _store(self, tmp_path) -> Store:
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        return store

    def _ingest_table_doc(self, store):
        pdf = build_pdf(
            [
                [
                    ("Räntekostnader 45 000 kr", 72, 100),
                    ("Driftskostnader 90 000 kr", 72, 130),
                ]
            ]
        )
        meta = store.add_document("Arsredovisning.pdf", pdf)
        assert meta.source == "digital"
        chunk = next(c for c in store.chunks.values() if c.document_id == meta.id)
        return meta, chunk

    def test_citation_on_the_labeled_row_lands_true(self, tmp_path):
        store = self._store(tmp_path)
        meta, chunk = self._ingest_table_doc(store)
        question = "Hur stora var föreningens räntekostnader under året?"
        alias, hits = common.alias_for_chunk(store, question, chunk.id)
        assert alias is not None

        fake = FakeLLM(
            [{"answer": "Se citerat utdrag.", "citations": [{"chunk_id": alias, "quote": "Räntekostnader 45 000 kr"}], "insufficient_data": False}]
        )
        resp = ask(store, question, provider=fake)

        assert not resp.refusal
        assert len(resp.citations) == 1
        cit = resp.citations[0]
        pages = store.pages[meta.id]
        verdict = row_landing_verdict(pages, ["räntekostnader"], cit.page, cit.rects)
        assert verdict["lands_on_label_row"] is True

    def test_citation_on_a_different_row_lands_false(self, tmp_path):
        store = self._store(tmp_path)
        meta, chunk = self._ingest_table_doc(store)
        question = "Hur stora var föreningens räntekostnader under året?"
        alias, hits = common.alias_for_chunk(store, question, chunk.id)
        assert alias is not None

        # The chunk covers both lines (a tiny doc = one chunk); the model
        # cites a REAL, verbatim, verifiable span — but the WRONG row.
        fake = FakeLLM(
            [{"answer": "Se citerat utdrag.", "citations": [{"chunk_id": alias, "quote": "Driftskostnader 90 000 kr"}], "insufficient_data": False}]
        )
        resp = ask(store, question, provider=fake)

        assert not resp.refusal
        assert len(resp.citations) == 1
        cit = resp.citations[0]
        pages = store.pages[meta.id]
        verdict = row_landing_verdict(pages, ["räntekostnader"], cit.page, cit.rects)
        assert verdict["lands_on_label_row"] is False
        # The label DOES occur on this page (proving the miss is row-level,
        # not page-level).
        assert verdict["label_pages"] == [cit.page]


class TestRerankFlagWiring:
    """`--rerank` must flip the temp store's own `Settings.rerankEnabled`
    to True before any question is asked; the default run must leave it
    untouched (False). No LLM call needed — an empty question list proves
    the wiring without asking anything."""

    def _spy_temp_store(self, monkeypatch) -> list[Store]:
        captured: list[Store] = []
        real_temp_store = common.temp_store

        @contextlib.contextmanager
        def spy():
            with real_temp_store() as store:
                captured.append(store)
                yield store

        monkeypatch.setattr(common, "temp_store", spy)
        return captured

    def _pdf_path(self, tmp_path) -> Path:
        pdf_path = Path(tmp_path) / "doc.pdf"
        pdf_path.write_bytes(build_pdf([[("Räntekostnader 45 000 kr", 72, 100)]]))
        return pdf_path

    def test_rerank_flag_enables_rerank_setting_before_asking(self, tmp_path, monkeypatch):
        captured = self._spy_temp_store(monkeypatch)
        hl_dir = tmp_path / "hl"
        hl_dir.mkdir()

        _process_document(self._pdf_path(tmp_path), "doc.pdf", "doc", [], hl_dir, rerank=True)

        assert len(captured) == 1
        assert captured[0].settings.rerankEnabled is True
        assert captured[0].settings.rerankCandidates == 40  # unchanged default, per task brief

    def test_without_rerank_flag_setting_stays_disabled(self, tmp_path, monkeypatch):
        captured = self._spy_temp_store(monkeypatch)
        hl_dir = tmp_path / "hl"
        hl_dir.mkdir()

        _process_document(self._pdf_path(tmp_path), "doc.pdf", "doc", [], hl_dir)  # rerank defaults to False

        assert len(captured) == 1
        assert captured[0].settings.rerankEnabled is False
