from app.enrich import document_year
from app.schemas import PageData, Word


def _w(text: str, y0: float = 100.0) -> Word:
    return Word(text=text, x0=72.0, y0=y0, x1=120.0, y1=y0 + 11.0, block=1, line=1)


def _page(n: int, tokens: list[str]) -> PageData:
    return PageData(number=n, width=595, height=842, words=[_w(t, 100 + 12 * i) for i, t in enumerate(tokens)])


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
