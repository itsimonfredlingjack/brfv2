from app.enrich import document_year, document_headings, heading_for, is_heading_line
from app.schemas import PageData, Word


def _w(text: str, y0: float = 100.0) -> Word:
    return Word(text=text, x0=72.0, y0=y0, x1=120.0, y1=y0 + 11.0, block=1, line=1)


def _page(n: int, tokens: list[str]) -> PageData:
    return PageData(number=n, width=595, height=842, words=[_w(t, 100 + 12 * i) for i, t in enumerate(tokens)])


def _line(text: str, *, y0: float, h: float, block: int, line: int, x0: float = 72.0) -> Word:
    return Word(text=text, x0=x0, y0=y0, x1=x0 + 40, y1=y0 + h, block=block, line=line)


class TestDocumentYear:
    def test_most_frequent_20xx_token_wins(self):
        pages = [_page(1, ["Årsredovisning", "2025", "för", "räkenskapsåret", "2025"])]
        assert document_year(pages) == "2025"

    def test_stray_single_occurrence_rejected(self):
        # "2072." appears once (a stray amount); real year "2024" appears twice.
        pages = [_page(1, ["2072.", "verksamhetsåret", "2024", "resultat", "2024"])]
        assert document_year(pages) == "2024"

    def test_no_year_returns_none(self):
        pages = [_page(1, ["Föreningen", "förvaltar", "fastigheten"])]
        assert document_year(pages) is None

    def test_only_scans_first_pages(self):
        pages = [_page(1, ["ingen", "siffra", "här"]), _page(2, ["2019", "2019"])]
        assert document_year(pages, scan_pages=1) is None


class TestHeadingDetection:
    def test_tall_short_digitfree_line_is_heading(self):
        # median body height 10; a 16-high one-word line stands out.
        body = [_line("löpande", y0=200, h=10, block=2, line=1)]
        heading = [_line("Resultaträkning", y0=100, h=16, block=1, line=1)]
        page = PageData(number=1, width=595, height=842, words=heading + body)
        med = 10.0
        assert is_heading_line(heading, med) is True
        assert is_heading_line(body, med) is False

    def test_line_with_digits_is_not_heading(self):
        # "Not 8 Räntekostnader" carries a digit -> excluded (deferred tier).
        words = [_line("Not", y0=100, h=16, block=1, line=1),
                 _line("8", y0=100, h=16, block=1, line=1, x0=120)]
        assert is_heading_line(words, 10.0) is False

    def test_long_line_is_not_heading(self):
        words = [_line(f"ord{i}", y0=100, h=16, block=1, line=1, x0=72 + 30 * i) for i in range(8)]
        assert is_heading_line(words, 10.0) is False

    def test_headings_carry_forward_across_pages(self):
        p1 = PageData(number=1, width=595, height=842, words=[
            _line("Resultaträkning", y0=100, h=16, block=1, line=1),
            _line("intäkter", y0=200, h=10, block=2, line=1),
        ])
        p2 = PageData(number=2, width=595, height=842, words=[
            _line("kostnad", y0=100, h=10, block=1, line=1),  # no heading here
        ])
        headings = document_headings([p1, p2])
        assert [h[2] for h in headings] == ["Resultaträkning"]
        # a chunk starting on page 2 inherits the last heading seen
        assert heading_for(headings, page=2, word_start=0) == "Resultaträkning"
        # a chunk before the heading gets nothing
        assert heading_for(headings, page=1, word_start=0) == "Resultaträkning"

    def test_heading_words_joined_in_reading_order(self):
        p = PageData(number=1, width=595, height=842, words=[
            _line("Eget", y0=100, h=16, block=1, line=1, x0=72),
            _line("kapital", y0=100, h=16, block=1, line=1, x0=110),
            _line("är", y0=200, h=10, block=2, line=2),
            _line("viktigt", y0=210, h=10, block=2, line=3),
        ])
        headings = document_headings([p])
        assert headings[0][2] == "Eget kapital"
