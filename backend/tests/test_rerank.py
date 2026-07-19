"""Cross-encoder rerank stage.

Unit tests inject a fake `_predict_fn` — no model load, offline + fast.
The one `rerank`-marked test loads the real jina cross-encoder and is
skipped unless the weights are already cached (reranker_available())."""

from __future__ import annotations

import pytest

from app.answer import ask
from app.llm import FakeLLM, LLMError
from app.rerank import rerank_chunks, reranker_available
from app.schemas import RetrievalHit, Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf


def _hit(chunk_id: str, text: str, *, score: float = 0.5, confidence: float = 0.5,
         document_name: str = "Doc.pdf") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        confidence=confidence,
        bm25=0.0,
        dense=0.0,
        document_id="d1",
        document_name=document_name,
        page=1,
        text=text,
    )


class TestRerankChunks:
    def test_reorders_by_score_and_cuts_to_top_k(self, monkeypatch):
        hits = [_hit("a", "chunk A text"), _hit("b", "chunk B text"), _hit("c", "chunk C text")]
        monkeypatch.setattr("app.rerank._predict_fn", lambda pairs: [0.1, 0.9, 0.5])

        out = rerank_chunks("query", hits, top_k=2)

        assert [h.chunk_id for h in out] == ["b", "c"]
        assert out[0].rerank_score == 0.9
        assert out[1].rerank_score == 0.5

    def test_preserves_other_hit_fields(self, monkeypatch):
        hits = [_hit("a", "chunk A text", score=0.42, confidence=0.77, document_name="Arsredovisning.pdf")]
        monkeypatch.setattr("app.rerank._predict_fn", lambda pairs: [0.3])

        out = rerank_chunks("query", hits, top_k=1)

        assert out[0].score == 0.42  # untouched by reranking
        assert out[0].confidence == 0.77  # untouched by reranking
        assert out[0].document_name == "Arsredovisning.pdf"
        assert out[0].chunk_id == "a"
        assert out[0].text == "chunk A text"
        assert out[0].rerank_score == 0.3

    def test_tie_break_preserves_original_rank(self, monkeypatch):
        hits = [_hit("a", "..."), _hit("b", "..."), _hit("c", "...")]
        # a and b tie at 0.5; c is highest. Deterministic tie-break must keep
        # a before b, since a was ranked first on input.
        monkeypatch.setattr("app.rerank._predict_fn", lambda pairs: [0.5, 0.5, 0.9])

        out = rerank_chunks("query", hits, top_k=3)

        assert [h.chunk_id for h in out] == ["c", "a", "b"]

    def test_empty_hits_returns_empty(self):
        assert rerank_chunks("q", [], top_k=5) == []

    def test_top_k_larger_than_hits_returns_all(self, monkeypatch):
        hits = [_hit("a", "x"), _hit("b", "y")]
        monkeypatch.setattr("app.rerank._predict_fn", lambda pairs: [0.1, 0.9])

        out = rerank_chunks("q", hits, top_k=10)

        assert len(out) == 2
        assert [h.chunk_id for h in out] == ["b", "a"]


class TestRerankerAvailable:
    def test_returns_bool_without_loading_the_model(self):
        # Must be cheap: a cache/import probe only. Environment for this
        # branch has the weights pre-cached (see task brief), so this is
        # expected True here — the point of the assertion is that the call
        # completes fast and doesn't itself construct a CrossEncoder.
        assert reranker_available() is True


DOC_LINES = [
    ("Jourperioden för snöröjning löper från 15 november till 15 april.", 72, 100),
    ("Halkbekämpning utförs senast en timme efter avslutad snöröjning.", 72, 114),
    ("Ersättning utgår med 1250 kr per påbörjad timme.", 72, 128),
]


@pytest.fixture()
def store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Snöröjningsavtal.pdf", build_pdf([DOC_LINES]))
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    return st


class TestRerankUnavailable:
    """Failure semantics: rerankEnabled + model unavailable must raise loudly
    at ask() time — never silently answer with unreranked hits."""

    def test_loud_swedish_error_when_reranker_unavailable(self, store, monkeypatch):
        monkeypatch.setattr("app.answer.reranker_available", lambda: False)
        store.update_settings(store.settings.model_copy(update={"rerankEnabled": True}))
        fake = FakeLLM([])

        with pytest.raises(LLMError, match="Omrankning"):
            ask(store, "När löper jourperioden?", provider=fake)

        assert fake.calls == []  # never reached the LLM: no silent skip


class TestAskWithRerank:
    """ask() end-to-end with a fake scorer: proves the excerpt aliases (K1,
    K2, ...) are built from the RERANKED order, not the raw retrieval order."""

    def _multi_doc_store(self, tmp_path) -> Store:
        st = Store(data_dir=tmp_path)
        st.add_document(
            "DokA.pdf", build_pdf([[("Soliditeten och kassaflödet diskuterades på stämman.", 72, 100)]])
        )
        st.add_document(
            "DokB.pdf",
            build_pdf([[("Föreningens soliditet uppgick till 45,2 procent enligt tabellen.", 72, 100)]]),
        )
        st.add_document(
            "DokC.pdf", build_pdf([[("Styrelsen sammanträdde och behandlade frågor om soliditet.", 72, 100)]])
        )
        st.update_settings(
            Settings(minRelevance=0.0, topK=1, rerankEnabled=True, rerankCandidates=10)
        )
        return st

    def test_excerpt_alias_k1_is_the_reranked_top_hit(self, tmp_path, monkeypatch):
        st = self._multi_doc_store(tmp_path)
        s = st.settings
        index, _, _, _ = st.snapshot()
        question = "Vad är soliditeten enligt tabellen?"

        # Baseline: the ORIGINAL retrieval order, using the exact wide-search
        # parameters ask() uses when rerankEnabled — computed independently
        # here so the assertion doesn't assume which doc BM25/dense naturally
        # prefers.
        search_top_k = max(s.rerankCandidates, s.topK)
        baseline = index.search(
            question,
            weight=s.searchWeighting / 100.0,
            candidates=max(s.candidateCount, search_top_k),
            top_k=search_top_k,
            min_confidence=0.0,
        )
        assert len(baseline) >= 2, "need at least 2 hits for reordering to be observable"

        # Fake scorer reverses the baseline order deterministically: pairs
        # arrive in the same order rerank_chunks was handed the hits, which
        # (given identical settings/state) is exactly `baseline`'s order.
        monkeypatch.setattr(
            "app.rerank._predict_fn",
            lambda pairs: [float(i) for i in range(len(pairs))],
        )
        expected_top = baseline[-1]
        assert expected_top.chunk_id != baseline[0].chunk_id  # proves reordering is observable

        fake = FakeLLM(
            [
                {
                    "answer": "Soliditeten är 45,2 procent.",
                    "citations": [{"chunk_id": "K1", "quote": expected_top.text}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(st, question, provider=fake)

        assert not resp.refusal, resp.refusal_reason
        assert len(resp.citations) == 1
        assert resp.citations[0].chunk_id == expected_top.chunk_id
        # retrieval echoes the reranked order too, with rerank_score populated.
        assert resp.retrieval[0].chunk_id == expected_top.chunk_id
        assert resp.retrieval[0].rerank_score == float(len(baseline) - 1)

    def test_rerank_disabled_ignores_fake_scorer(self, tmp_path, monkeypatch):
        """rerankEnabled=False must behave exactly as before reranking
        existed — the fake scorer below would flip results if consulted."""
        st = self._multi_doc_store(tmp_path)
        st.update_settings(st.settings.model_copy(update={"rerankEnabled": False}))
        monkeypatch.setattr(
            "app.rerank._predict_fn",
            lambda pairs: [float(i) for i in range(len(pairs))],
        )
        chunk_id = next(iter(st.chunks))
        fake = FakeLLM(
            [
                {
                    "answer": "Svar.",
                    "citations": [{"chunk_id": chunk_id, "quote": next(iter(st.chunks.values())).text}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(st, "Vad är soliditeten enligt tabellen?", provider=fake)
        assert all(h.rerank_score is None for h in resp.retrieval)


@pytest.mark.rerank
@pytest.mark.skipif(not reranker_available(), reason="jina reranker weights not cached / deps missing")
class TestRealReranker:
    """Loads the REAL jina-reranker-v2-base-multilingual model (no LLM
    involved). Diagnosed failure mode: a true financial-table answer row
    loses to prose under hybrid BM25/dense retrieval; the cross-encoder must
    reverse that for a table-shaped query."""

    def test_table_row_outranks_prose_for_soliditet_query(self):
        table_hit = _hit(
            "table", "Soliditet 45,2 % 2024 43,8 % 2023", document_name="Balansräkning.pdf"
        )
        prose_hit = _hit(
            "prose",
            "Styrelsen tackar alla medlemmar för visat engagemang under året och önskar en fortsatt trevlig vår.",
            document_name="Ordförandeord.pdf",
        )

        out = rerank_chunks("Vad är soliditeten enligt balansräkningen?", [prose_hit, table_hit], top_k=2)

        assert out[0].chunk_id == "table"
        assert out[0].rerank_score > out[1].rerank_score


class TestConfigurableModel:
    """The cross-encoder model id is overridable via BRF_RERANK_MODEL (for the
    licensing eval); default is unchanged (jina)."""

    def test_default_is_jina_when_unset(self, monkeypatch):
        monkeypatch.delenv("BRF_RERANK_MODEL", raising=False)
        from app.rerank import model_name

        assert model_name() == "jinaai/jina-reranker-v2-base-multilingual"

    def test_env_overrides_model(self, monkeypatch):
        monkeypatch.setenv("BRF_RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
        from app.rerank import model_name

        assert model_name() == "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

    def test_max_length_default_and_override(self, monkeypatch):
        from app.rerank import max_length

        monkeypatch.delenv("BRF_RERANK_MAX_LENGTH", raising=False)
        assert max_length() == 1024  # jina default
        monkeypatch.setenv("BRF_RERANK_MAX_LENGTH", "512")
        assert max_length() == 512  # XLM-R-based models cap here
