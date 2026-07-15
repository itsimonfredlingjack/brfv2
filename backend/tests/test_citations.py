"""SPEC §2 failure-mode tests: every mode must be *detected*, not just survived."""

import pytest

from app.chunker import chunk_pages
from app.citations import Rejected, Resolved, resolve_quote
from app.extract import extract_pdf
from app.schemas import Chunk, PageData, Word
from tests.pdf_fixtures import build_pdf


def chunk_covering_page(doc_id: str, pages, page_number: int) -> Chunk:
    """One chunk spanning the whole given page."""
    words = pages[page_number - 1].words
    return Chunk(
        id=f"{doc_id}:p{page_number}:0-{len(words) - 1}",
        document_id=doc_id,
        page=page_number,
        word_start=0,
        word_end=len(words) - 1,
        text=" ".join(w.text for w in words),
    )


@pytest.fixture()
def simple_doc():
    pdf = build_pdf(
        [
            [
                ("Föreningens firma är Bostadsrättsföreningen Gjutformen 12.", 72, 100),
                ("Styrelsen har sitt säte i Göteborg och förvaltar fastigheten.", 72, 114),
            ]
        ]
    )
    pages = extract_pdf(pdf)
    return "doc1", pages


class TestHappyPath:
    def test_exact_quote_resolves_with_rects(self, simple_doc):
        doc_id, pages = simple_doc
        chunk = chunk_covering_page(doc_id, pages, 1)
        res = resolve_quote(chunk, "Styrelsen har sitt säte i Göteborg", {doc_id: pages})
        assert isinstance(res, Resolved)
        assert res.page == 1
        assert len(res.rects) == 1
        x0, y0, x1, y1 = res.rects[0]
        assert x1 > x0 and y1 > y0
        assert 0 <= x0 and x1 <= pages[0].width


class Test21QuoteNotFound:
    def test_fabricated_quote_rejected(self, simple_doc):
        doc_id, pages = simple_doc
        chunk = chunk_covering_page(doc_id, pages, 1)
        res = resolve_quote(chunk, "Ordföranden har ensam firmateckningsrätt", {doc_id: pages})
        assert isinstance(res, Rejected)
        assert res.reason == "quote_not_found"

    def test_subtly_altered_quote_rejected(self, simple_doc):
        doc_id, pages = simple_doc
        chunk = chunk_covering_page(doc_id, pages, 1)
        # "säte i Stockholm" — one word altered
        res = resolve_quote(chunk, "Styrelsen har sitt säte i Stockholm", {doc_id: pages})
        assert isinstance(res, Rejected)
        assert res.reason == "quote_not_found"


class Test22SpanCrossesLines:
    def test_two_line_quote_gets_two_rects(self):
        pdf = build_pdf(
            [
                [
                    ("Entreprenören ansvarar för snöröjning av samtliga", 72, 100),
                    ("gemensamma ytor inklusive entréer och gångbanor.", 72, 114),
                ]
            ]
        )
        pages = extract_pdf(pdf)
        chunk = chunk_covering_page("d", pages, 1)
        res = resolve_quote(chunk, "snöröjning av samtliga gemensamma ytor", {"d": pages})
        assert isinstance(res, Resolved)
        assert len(res.rects) == 2
        (r1, r2) = sorted(res.rects, key=lambda r: r[1])
        assert r2[1] > r1[3] - 2  # second rect starts below the first line's band


class Test23SpanCrossesBlocks:
    def test_quote_across_paragraph_gap_matches(self):
        pdf = build_pdf(
            [
                [
                    ("Avtalet gäller till och med 2027.", 72, 100),
                    ("Uppsägning skall ske skriftligen.", 72, 180),  # big gap → new block
                ]
            ]
        )
        pages = extract_pdf(pdf)
        blocks = {w.block for w in pages[0].words}
        assert len(blocks) >= 2, "fixture must span two blocks"
        chunk = chunk_covering_page("d", pages, 1)
        res = resolve_quote(chunk, "med 2027. Uppsägning skall ske", {"d": pages})
        assert isinstance(res, Resolved)
        assert len(res.rects) == 2


class Test25HyphenationDrift:
    def test_hyphenated_linebreak_matches_and_boxes_cover_both_fragments(self):
        pdf = build_pdf(
            [
                [
                    ("Byrån sköter ekonomisk för-", 72, 100),
                    ("valtning åt föreningen.", 72, 114),
                ]
            ]
        )
        pages = extract_pdf(pdf)
        chunk = chunk_covering_page("d", pages, 1)
        res = resolve_quote(chunk, "ekonomisk förvaltning åt föreningen", {"d": pages})
        assert isinstance(res, Resolved)
        assert len(res.rects) == 2
        frag = next(w for w in pages[0].words if w.text == "för-")
        top_rect = min(res.rects, key=lambda r: r[1])
        assert top_rect[0] <= frag.x0 + 1 and top_rect[2] >= frag.x1 - 1


class Test26DuplicatedBoilerplate:
    FOOTER = "Brf Gjutformen 12 org nr 769600-1234"

    @pytest.fixture()
    def doc(self):
        pdf = build_pdf(
            [
                [("Stadgar för föreningen antogs vid stämman.", 72, 100), (self.FOOTER, 72, 800)],
                [("Årsavgiften fördelas efter andelstal.", 72, 100), (self.FOOTER, 72, 800)],
            ]
        )
        return extract_pdf(pdf)

    def test_footer_cited_from_page2_chunk_lands_on_page2(self, doc):
        chunk = chunk_covering_page("d", doc, 2)
        res = resolve_quote(chunk, self.FOOTER, {"d": doc})
        assert isinstance(res, Resolved)
        assert res.page == 2

    def test_quote_absent_from_cited_chunk_but_elsewhere_is_provenance_mismatch(self, doc):
        # Build a chunk over ONLY the content words of page 1 (footer excluded)
        words = doc[0].words
        footer_start = next(i for i, w in enumerate(words) if w.text == "Brf")
        chunk = Chunk(
            id="d:p1:content",
            document_id="d",
            page=1,
            word_start=0,
            word_end=footer_start - 1,
            text=" ".join(w.text for w in words[:footer_start]),
        )
        # Quote is page-2 content — real text, wrong provenance.
        res = resolve_quote(chunk, "Årsavgiften fördelas efter andelstal", {"d": doc})
        assert isinstance(res, Rejected)
        assert res.reason == "provenance_mismatch"


class Test27OutOfBounds:
    def test_word_with_offpage_bbox_rejected(self):
        page = PageData(
            number=1,
            width=595,
            height=842,
            words=[
                Word(text="Utanför", x0=550, y0=900, x1=700, y1=920, block=0, line=0),
                Word(text="sidan", x0=700, y0=900, x1=780, y1=920, block=0, line=0),
            ],
        )
        chunk = Chunk(id="d:p1:0-1", document_id="d", page=1, word_start=0, word_end=1, text="Utanför sidan")
        res = resolve_quote(chunk, "Utanför sidan", {"d": [page]})
        assert isinstance(res, Rejected)
        assert res.reason == "bbox_out_of_bounds"


class Test28UnicodeDrift:
    def test_quote_with_nbsp_and_typographic_quotes_matches(self, simple_doc):
        doc_id, pages = simple_doc
        chunk = chunk_covering_page(doc_id, pages, 1)
        res = resolve_quote(chunk, "”Styrelsen har sitt säte i Göteborg”", {doc_id: pages})
        assert isinstance(res, Resolved)


class TestChunkBoundaryOverlap:
    def test_quote_overlapping_chunk_end_still_resolves(self, simple_doc):
        """A quote that starts inside the chunk but runs past its end is still
        page-verbatim text at the retrieved location — accepted."""
        doc_id, pages = simple_doc
        words = pages[0].words
        mid = len(words) // 2
        chunk = Chunk(
            id="doc1:p1:head",
            document_id=doc_id,
            page=1,
            word_start=0,
            word_end=mid,
            text=" ".join(w.text for w in words[: mid + 1]),
        )
        tail_quote = " ".join(w.text for w in words[mid - 1 : mid + 3])
        res = resolve_quote(chunk, tail_quote, {doc_id: pages})
        assert isinstance(res, Resolved)
