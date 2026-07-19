import pytest
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

    def test_weighting_knob_changes_scores(self):
        # weight=0 must rank purely by BM25, weight=1 purely by dense — the
        # fused scores of the same chunks must differ between the two runs.
        # (The system-level proof that the knob shifts ranking/recall lives in
        # scripts/eval.py --sweep; unit-crafted "flip" corpora kept becoming
        # obsolete as query expansion got more robust.)
        idx = build_index()
        q = "Vem fastställer årsavgiften?"
        w0 = {h.chunk_id: h.score for h in idx.search(q, weight=0.0, candidates=10, top_k=5, min_confidence=0.0)}
        w1 = {h.chunk_id: h.score for h in idx.search(q, weight=1.0, candidates=10, top_k=5, min_confidence=0.0)}
        assert w0 != w1
        hit = idx.search(q, weight=0.0, candidates=10, top_k=1, min_confidence=0.0)[0]
        assert hit.score == pytest.approx(1.0)  # pure-BM25 top hit is the BM25 max

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


class TestSearchTextDrivesRankingButNotDisplay:
    def test_search_text_used_for_ranking_display_text_frozen(self):
        # A chunk whose FROZEN text is a bare row, but whose search_text carries
        # a distinctive enrichment term. A query for that term must retrieve it,
        # yet the returned hit.text must be the frozen text (no enrichment leak).
        frozen = "1 234 567"
        chunks = [
            Chunk(id="d1:p1:c0", document_id="d1", page=1, word_start=0, word_end=2,
                  text=frozen, search_text="Zorblecksynized 2099 " + frozen),
            Chunk(id="d1:p1:c1", document_id="d1", page=1, word_start=3, word_end=8,
                  text="föreningen har ett fint hus här", search_text=None),
        ]
        idx = HybridIndex(HashedNgramEmbedder())
        idx.build(chunks, {"d1": "Doc"})
        hits = idx.search("Zorblecksynized", weight=0.5, candidates=10, top_k=1, min_confidence=0.0)
        assert hits[0].chunk_id == "d1:p1:c0"
        assert hits[0].text == frozen  # frozen text returned, NOT the search_text
        assert hits[0].bm25 > 0  # BM25-fit used search_text: the term is absent from the frozen text


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
        assert expanded["vad"] == (set(), set()) and expanded["är"] == (set(), set())

    def test_unrelated_long_word_still_unmatched(self):
        idx = build_index()
        strong, fuzzy = idx._expand_query(["kvantfysikens"])["kvantfysikens"]
        assert strong == set() and fuzzy == set()

    def test_fuzzy_tier_catches_vowel_elision(self):
        # "fönstren" (fönstr-en) vs "fönsterbyte" — neither prefix nor
        # substring, but trigram-similar → fuzzy match, gate-only.
        idx = build_index()
        strong, fuzzy = idx._expand_query(["fönstren"])["fönstren"]
        assert "fönsterbyte" in fuzzy
        assert "fönsterbyte" not in strong
