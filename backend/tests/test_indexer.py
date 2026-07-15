from app.embeddings import HashedNgramEmbedder
from app.indexer import HybridIndex, tokenize
from app.schemas import Chunk


def mk_chunk(i: int, text: str, doc: str = "d1", page: int = 1) -> Chunk:
    return Chunk(id=f"{doc}:p{page}:c{i}", document_id=doc, page=page, word_start=0, word_end=max(0, len(text.split()) - 1), text=text)


CORPUS = [
    mk_chunk(0, "Snöröjning och halkbekämpning utförs av entreprenören under jourperioden"),
    mk_chunk(1, "Årsavgiften fastställs av styrelsen och fördelas efter andelstal"),
    mk_chunk(2, "Styrelsen beslutade att godkänna budgeten för fasadmålning"),
    mk_chunk(3, "Medlemskap kan sökas av fysisk eller juridisk person som förvärvat bostadsrätt"),
    mk_chunk(4, "Underhållsplanen omfattar stammbyte takrenovering och fönsterbyte"),
]


def build_index(chunks=None) -> HybridIndex:
    idx = HybridIndex(HashedNgramEmbedder())
    idx.build(chunks or CORPUS, {"d1": "Testdok"})
    return idx


class TestTokenize:
    def test_normalizes_and_splits(self):
        assert tokenize("Snöröjning, utförs.") == ["snöröjning", "utförs"]


class TestSearch:
    def test_exact_term_query_ranks_correct_chunk_first_bm25(self):
        idx = build_index()
        hits = idx.search("Vem fastställer årsavgiften?", weight=0.0, candidates=10, top_k=3, min_confidence=0.0)
        assert hits[0].chunk_id == CORPUS[1].id

    def test_weighting_knob_changes_ranking(self):
        # A: exact token match ("protokoll") → BM25 favors A.
        # B: suffix-side compound variants that prefix expansion does NOT
        #    match ("mötesprotokollen" etc.), but whose char n-grams overlap
        #    heavily → the dense signal favors B.
        a = mk_chunk(10, "protokoll undertecknades av ordföranden efteråt")
        b = mk_chunk(11, "mötesprotokollen kvartalsprotokollen extraprotokollen samlas")
        idx = build_index([a, b])
        bm25_first = idx.search("protokoll", weight=0.0, candidates=10, top_k=2, min_confidence=0.0)
        dense_first = idx.search("protokoll", weight=1.0, candidates=10, top_k=2, min_confidence=0.0)
        assert bm25_first[0].chunk_id == a.id
        assert dense_first[0].chunk_id != bm25_first[0].chunk_id

    def test_top_k_respected(self):
        idx = build_index()
        assert len(idx.search("styrelsen", weight=0.5, candidates=10, top_k=2, min_confidence=0.0)) == 2

    def test_min_confidence_filters_unrelated_query(self):
        idx = build_index()
        hits = idx.search("kvantfysikens grundläggande postulat", weight=0.5, candidates=10, top_k=5, min_confidence=0.5)
        assert hits == []

    def test_answerable_query_confidence_beats_unanswerable(self):
        idx = build_index()
        good = idx.search("Vem fastställer årsavgiften?", weight=0.5, candidates=10, top_k=1, min_confidence=0.0)
        bad = idx.search("Vad kostar en parkeringsplats i garaget?", weight=0.5, candidates=10, top_k=1, min_confidence=0.0)
        assert good[0].confidence > bad[0].confidence

    def test_candidate_count_limits_pool(self):
        idx = build_index()
        few = idx.search("styrelsen budgeten medlemskap", weight=0.0, candidates=1, top_k=5, min_confidence=0.0)
        many = idx.search("styrelsen budgeten medlemskap", weight=0.0, candidates=5, top_k=5, min_confidence=0.0)
        assert len(many) > len(few) >= 1

    def test_empty_index_returns_empty(self):
        idx = HybridIndex(HashedNgramEmbedder())
        idx.build([], {})
        assert idx.search("något", weight=0.5, candidates=10, top_k=3, min_confidence=0.0) == []

    def test_hits_carry_document_metadata(self):
        idx = build_index()
        hit = idx.search("årsavgiften", weight=0.0, candidates=10, top_k=1, min_confidence=0.0)[0]
        assert hit.document_name == "Testdok"
        assert hit.page == 1
        assert hit.text == CORPUS[1].text


class TestCompoundExpansion:
    """Swedish compounds: query terms must match corpus terms via prefix."""

    def test_compound_query_finds_base_word_chunk(self):
        idx = build_index()
        hits = idx.search("När startar snöröjningsjouren?", weight=0.0, candidates=10, top_k=1, min_confidence=0.0)
        assert hits[0].chunk_id == CORPUS[0].id  # snöröjning chunk
        assert hits[0].confidence > 0.2

    def test_inflected_form_matches(self):
        idx = build_index()
        hits = idx.search("underhållsplanens omfattning", weight=0.0, candidates=10, top_k=1, min_confidence=0.0)
        assert hits[0].chunk_id == CORPUS[4].id  # "Underhållsplanen omfattar ..."

    def test_short_tokens_do_not_expand(self):
        idx = build_index()
        expanded = idx._expand_query(["vad", "är"])
        assert expanded["vad"] == set() and expanded["är"] == set()

    def test_unrelated_long_word_still_unmatched(self):
        idx = build_index()
        expanded = idx._expand_query(["kvantfysikens"])
        assert expanded["kvantfysikens"] == set()
