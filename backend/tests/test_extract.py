import pytest

from app.extract import extract_pdf
from tests.pdf_fixtures import build_pdf


@pytest.fixture()
def two_page_pdf() -> bytes:
    return build_pdf(
        [
            [
                ("Föreningens firma är Bostadsrättsföreningen Gjutformen 12", 72, 100),
                ("Styrelsen har sitt säte i Göteborg", 72, 114),
            ],
            [("Årsavgiften fastställs av styrelsen", 72, 100)],
        ]
    )


def test_page_count_and_dims(two_page_pdf):
    pages = extract_pdf(two_page_pdf)
    assert len(pages) == 2
    assert pages[0].number == 1 and pages[1].number == 2
    assert pages[0].width == pytest.approx(595, abs=1)
    assert pages[0].height == pytest.approx(842, abs=1)
    assert pages[0].rotation == 0


def test_words_extracted_with_swedish_chars(two_page_pdf):
    pages = extract_pdf(two_page_pdf)
    texts = [w.text for w in pages[0].words]
    assert "Föreningens" in texts
    assert "Göteborg" in texts
    assert [w.text for w in pages[1].words] == ["Årsavgiften", "fastställs", "av", "styrelsen"]


def test_bboxes_sane_and_within_page(two_page_pdf):
    pages = extract_pdf(two_page_pdf)
    for page in pages:
        for w in page.words:
            assert w.x1 > w.x0 and w.y1 > w.y0
            assert 0 <= w.x0 and w.x1 <= page.width
            assert 0 <= w.y0 and w.y1 <= page.height


def test_reading_order_top_to_bottom(two_page_pdf):
    pages = extract_pdf(two_page_pdf)
    words = pages[0].words
    first_line_last = next(w for w in words if w.text == "12")
    second_line_first = next(w for w in words if w.text == "Styrelsen")
    assert words.index(second_line_first) > words.index(first_line_last)
    assert second_line_first.y0 > first_line_last.y0
    assert second_line_first.line != first_line_last.line or second_line_first.block != first_line_last.block


def test_empty_pdf_has_no_words():
    pages = extract_pdf(build_pdf([[]]))
    assert len(pages) == 1
    assert pages[0].words == []
