from app.chunker import chunk_pages
from app.schemas import PageData, Word


def fake_page(blocks: list[str], number: int = 1) -> PageData:
    """Fabricate a PageData: each string is one block, one line, words laid
    out left-to-right."""
    words: list[Word] = []
    for b, text in enumerate(blocks):
        for i, tok in enumerate(text.split()):
            x = 72 + i * 30
            y = 72 + b * 40
            words.append(Word(text=tok, x0=x, y0=y, x1=x + 25, y1=y + 11, block=b, line=0))
    return PageData(number=number, width=595, height=842, words=words)


def joined(page: PageData, start: int, end: int) -> str:
    return " ".join(w.text for w in page.words[start : end + 1])


LONG_TEXT = " ".join(f"ord{i}" for i in range(120))


class TestFixed:
    def test_sliding_window_ranges(self):
        page = fake_page([LONG_TEXT])
        chunks = chunk_pages("d1", [page], strategy="fixed", size=50, overlap=10)
        assert [(c.word_start, c.word_end) for c in chunks] == [(0, 49), (40, 89), (80, 119)]

    def test_zero_overlap_disjoint(self):
        page = fake_page([LONG_TEXT])
        chunks = chunk_pages("d1", [page], strategy="fixed", size=40, overlap=0)
        assert [(c.word_start, c.word_end) for c in chunks] == [(0, 39), (40, 79), (80, 119)]

    def test_text_matches_word_range(self):
        page = fake_page([LONG_TEXT])
        for c in chunk_pages("d1", [page], strategy="fixed", size=50, overlap=10):
            assert c.text == joined(page, c.word_start, c.word_end)


class TestSentence:
    BLOCK = (
        "Styrelsen beslutade att godkänna budgeten. Beslutet var enhälligt. "
        "Nästa möte hålls i april. Ordföranden avslutade mötet."
    )

    def test_chunks_end_at_sentence_boundaries(self):
        page = fake_page([self.BLOCK])
        chunks = chunk_pages("d1", [page], strategy="sentence", size=8, overlap=0)
        assert len(chunks) >= 2
        for c in chunks:
            assert c.text.rstrip().endswith(".")

    def test_all_words_covered(self):
        page = fake_page([self.BLOCK])
        chunks = chunk_pages("d1", [page], strategy="sentence", size=8, overlap=0)
        covered = set()
        for c in chunks:
            covered.update(range(c.word_start, c.word_end + 1))
        assert covered == set(range(len(page.words)))


class TestRecursive:
    def test_small_blocks_pack_together(self):
        page = fake_page(["Första stycket är kort.", "Andra stycket är också kort."])
        chunks = chunk_pages("d1", [page], strategy="recursive", size=100, overlap=0)
        assert len(chunks) == 1
        assert chunks[0].word_start == 0
        assert chunks[0].word_end == len(page.words) - 1

    def test_block_boundary_respected_when_full(self):
        page = fake_page(["ett två tre fyra fem", "sex sju åtta nio tio"])
        chunks = chunk_pages("d1", [page], strategy="recursive", size=6, overlap=0)
        assert [(c.word_start, c.word_end) for c in chunks] == [(0, 4), (5, 9)]

    def test_oversized_block_is_split(self):
        page = fake_page([LONG_TEXT])
        chunks = chunk_pages("d1", [page], strategy="recursive", size=50, overlap=0)
        assert len(chunks) >= 2
        assert all((c.word_end - c.word_start + 1) <= 50 for c in chunks)


class TestInvariants:
    def test_chunks_never_cross_pages(self):
        pages = [fake_page([LONG_TEXT], number=1), fake_page([LONG_TEXT], number=2)]
        chunks = chunk_pages("d1", pages, strategy="fixed", size=200, overlap=0)
        assert {c.page for c in chunks} == {1, 2}
        for c in chunks:
            page = pages[c.page - 1]
            assert 0 <= c.word_start <= c.word_end < len(page.words)

    def test_chunk_ids_unique_and_stable(self):
        page = fake_page([LONG_TEXT])
        a = chunk_pages("d1", [page], strategy="fixed", size=50, overlap=10)
        b = chunk_pages("d1", [page], strategy="fixed", size=50, overlap=10)
        assert [c.id for c in a] == [c.id for c in b]
        assert len({c.id for c in a}) == len(a)

    def test_size_knob_changes_chunk_count(self):
        page = fake_page([LONG_TEXT])
        small = chunk_pages("d1", [page], strategy="fixed", size=30, overlap=0)
        large = chunk_pages("d1", [page], strategy="fixed", size=100, overlap=0)
        assert len(small) > len(large)

    def test_overlap_knob_creates_overlap(self):
        page = fake_page([LONG_TEXT])
        chunks = chunk_pages("d1", [page], strategy="fixed", size=50, overlap=20)
        assert chunks[1].word_start < chunks[0].word_end

    def test_empty_page_produces_no_chunks(self):
        page = PageData(number=1, width=595, height=842, words=[])
        assert chunk_pages("d1", [page], strategy="recursive", size=100, overlap=10) == []
