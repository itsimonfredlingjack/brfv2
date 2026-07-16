"""Orchestration tests: gates, verification, refusal paths — FakeLLM only."""

import pytest

from app.answer import ask
from app.llm import FakeLLM
from app.schemas import Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf

DOC_LINES = [
    ("Jourperioden för snöröjning löper från 15 november till 15 april.", 72, 100),
    ("Halkbekämpning utförs senast en timme efter avslutad snöröjning.", 72, 114),
    ("Ersättning utgår med 1250 kr per påbörjad timme.", 72, 128),
]


@pytest.fixture()
def store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Snöröjningsavtal.pdf", build_pdf([DOC_LINES]))
    st.update_settings(Settings(minRelevance=0.15, topK=3))
    return st


def first_chunk_id(store: Store) -> str:
    return next(iter(store.chunks))


def good_response(store: Store) -> dict:
    return {
        "answer": "Jourperioden löper från 15 november till 15 april.",
        "citations": [{"chunk_id": first_chunk_id(store), "quote": "löper från 15 november till 15 april"}],
        "insufficient_data": False,
    }


class TestGates:
    def test_empty_store_refuses_without_llm(self, tmp_path):
        st = Store(data_dir=tmp_path)
        fake = FakeLLM([])
        resp = ask(st, "Vad gäller?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "no_documents"
        assert fake.calls == []

    def test_low_relevance_refuses_before_llm(self, store):
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.99}))
        fake = FakeLLM([])
        resp = ask(store, "Hur fungerar kvantdatorer?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "low_relevance"
        assert fake.calls == []
        assert resp.retrieval  # retrieval shown for transparency

    def test_llm_insufficient_data_refuses(self, store):
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))  # isolate the LLM gate
        fake = FakeLLM([{"answer": "Uppgift saknas.", "citations": [], "insufficient_data": True}])
        resp = ask(store, "Vad kostar garaget?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "insufficient_data"

    def test_warn_mode_answers_with_warning_instead_of_refusing(self, store):
        store.update_settings(
            store.settings.model_copy(update={"insufficientDataBehavior": "warn", "minRelevance": 0.0})
        )
        fake = FakeLLM([{"answer": "Osäkert svar.", "citations": [], "insufficient_data": True}])
        resp = ask(store, "Vad kostar garaget?", provider=fake)
        assert not resp.refusal
        assert resp.warning


class TestGrounding:
    def test_verified_citation_returned_with_rects(self, store):
        fake = FakeLLM([good_response(store)])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        cit = resp.citations[0]
        assert cit.page == 1
        assert cit.rects and all(len(r) == 4 for r in cit.rects)
        assert cit.document_name == "Snöröjningsavtal.pdf"

    def test_fabricated_quote_rejected_and_refused_when_all_fail(self, store):
        fake = FakeLLM(
            [
                {
                    "answer": "Hittat på.",
                    "citations": [{"chunk_id": first_chunk_id(store), "quote": "Jouren pågår hela året utan uppehåll"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "grounding_failed"
        assert resp.rejected_citations[0].reason == "quote_not_found"

    def test_unknown_chunk_id_rejected(self, store):
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        fake = FakeLLM(
            [
                {
                    "answer": "Svar.",
                    "citations": [
                        {"chunk_id": "finns:inte:0-1", "quote": "spelar ingen roll"},
                        {"chunk_id": first_chunk_id(store), "quote": "1250 kr per påbörjad timme"},
                    ],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "Vad är ersättningen?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        assert resp.rejected_citations[0].reason == "unknown_chunk"
        assert resp.warning

    def test_answer_without_citations_refused_when_sources_required(self, store):
        fake = FakeLLM([{"answer": "Bara text utan källor.", "citations": [], "insufficient_data": False}])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "grounding_failed"

    def test_requireSources_off_allows_uncited_answer(self, store):
        store.update_settings(store.settings.model_copy(update={"requireSources": False}))
        fake = FakeLLM([{"answer": "Bara text.", "citations": [], "insufficient_data": False}])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal


class TestRobustness:
    def test_unparseable_llm_output_retried_once_then_ok(self, store):
        fake = FakeLLM(["inte json alls", good_response(store)])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert len(fake.calls) == 2
        assert "VIKTIGT" in fake.calls[1]["system"]

    def test_llm_prompt_contains_chunks_and_contract(self, store):
        fake = FakeLLM([good_response(store)])
        ask(store, "När löper jourperioden?", provider=fake)
        call = fake.calls[0]
        assert "ORDAGRANT" in call["system"]
        assert "[K1] (Snöröjningsavtal.pdf, sida 1)" in call["user"]
        assert "UTDRAG" in call["user"]

    def test_settings_model_and_max_tokens_passed_through(self, store):
        store.update_settings(store.settings.model_copy(update={"aiModel": "claude-opus-4-8", "maxResponseLength": 777}))
        fake = FakeLLM([good_response(store)])
        ask(store, "När löper jourperioden?", provider=fake)
        assert fake.calls[0]["model"] == "claude-opus-4-8"
        assert fake.calls[0]["max_tokens"] == 777


class TestChunkAliases:
    def test_alias_citation_resolves(self, store):
        real_id = first_chunk_id(store)
        # The excerpt list is deterministic; K1 = top retrieval hit. Use a
        # question whose top hit is the document's only chunk on page 1.
        fake = FakeLLM(
            [
                {
                    "answer": "Jourperioden löper från 15 november till 15 april.",
                    "citations": [{"chunk_id": "K1", "quote": "löper från 15 november till 15 april"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert not resp.refusal
        assert resp.citations[0].chunk_id == real_id

    def test_bracketed_alias_tolerated(self, store):
        fake = FakeLLM(
            [
                {
                    "answer": "Svar.",
                    "citations": [{"chunk_id": "[K1]", "quote": "löper från 15 november till 15 april"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert not resp.refusal

    def test_truncated_unknown_id_still_rejected(self, store):
        fake = FakeLLM(
            [
                {
                    "answer": "Svar.",
                    "citations": [{"chunk_id": "K99", "quote": "löper från 15 november till 15 april"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "grounding_failed"
        assert resp.rejected_citations[0].reason == "unknown_chunk"

    def test_prompt_uses_aliases(self, store):
        fake = FakeLLM([good_response(store)])
        ask(store, "När löper jourperioden?", provider=fake)
        assert "[K1]" in fake.calls[0]["user"]


class TestProviderFailures:
    def test_provider_exception_is_provider_error_without_detail(self, store):
        class Boom:
            name = "boom"

            def complete(self, system, user, *, max_tokens, model):
                raise RuntimeError("hemlig intern detalj /Users/nagon/nyckel")

        resp = ask(store, "När löper jourperioden?", provider=Boom())
        assert resp.refusal and resp.refusal_reason == "provider_error"
        assert "hemlig" not in resp.answer and "/Users/" not in resp.answer


class TestWarnModeGrounding:
    def _warn_store(self, store):
        store.update_settings(
            store.settings.model_copy(update={"insufficientDataBehavior": "warn", "minRelevance": 0.0})
        )
        return store

    def test_warn_mode_still_verifies_citations(self, store):
        store = self._warn_store(store)
        fake = FakeLLM(
            [
                {
                    "answer": "Osäkert: jouren verkar starta 15 november.",
                    "citations": [{"chunk_id": "K1", "quote": "löper från 15 november till 15 april"}],
                    "insufficient_data": True,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert not resp.refusal
        assert resp.warning
        assert len(resp.citations) == 1 and resp.citations[0].rects

    def test_warn_mode_fabricated_citations_still_refuse(self, store):
        store = self._warn_store(store)
        fake = FakeLLM(
            [
                {
                    "answer": "Osäkert svar.",
                    "citations": [{"chunk_id": "K1", "quote": "helt påhittat citat utan täckning"}],
                    "insufficient_data": True,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "grounding_failed"


class TestCitationScopeRestriction:
    def test_raw_id_of_unretrieved_chunk_rejected(self, store):
        """The model may only cite excerpts it was shown: a real chunk id that
        was not among the retrieved excerpts must be rejected, not resolved."""
        store.add_document(
            "Underhållsplan.pdf",
            build_pdf([[("Fasadmålning planeras till sommaren 2027 enligt underhållsplanen.", 72, 100)]]),
        )
        store.update_settings(store.settings.model_copy(update={"topK": 1, "minRelevance": 0.0}))
        other_id = next(
            cid for cid, c in store.chunks.items()
            if store.documents[c.document_id].name == "Underhållsplan.pdf"
        )
        fake = FakeLLM(
            [
                {
                    "answer": "Svar.",
                    "citations": [{"chunk_id": other_id, "quote": "Fasadmålning planeras till sommaren 2027"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(store, "När löper jourperioden för snöröjning?", provider=fake)
        assert resp.retrieval and all(h.document_name == "Snöröjningsavtal.pdf" for h in resp.retrieval)
        assert resp.rejected_citations and resp.rejected_citations[0].reason == "unknown_chunk"
        assert resp.refusal and resp.refusal_reason == "grounding_failed"


class TestMultiSpanCitations:
    """Fragment-fact citations through the full orchestrator. The invariant:
    a claim reaches the user only if EVERY span verified; otherwise rejected
    exactly like a fabricated single quote."""

    def test_multispan_citation_accepted_with_union_rects(self, store):
        cid = first_chunk_id(store)
        fake = FakeLLM([
            {
                "answer": "Jouren gäller vintersäsongen och ersätts per timme.",
                "citations": [{
                    "chunk_id": cid,
                    "quotes": ["Jourperioden för snöröjning", "1250 kr per påbörjad timme"],
                }],
                "insufficient_data": False,
            }
        ])
        resp = ask(store, "Vad gäller för jouren och ersättningen?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        c = resp.citations[0]
        assert c.quotes == ["Jourperioden för snöröjning", "1250 kr per påbörjad timme"]
        # Display string carries both fragments.
        assert "Jourperioden" in c.quote and "1250 kr" in c.quote
        # Union: the two spans sit on different lines → at least two rects.
        assert len(c.rects) >= 2
        assert resp.rejected_citations == []

    def test_invariant_one_bad_span_rejects_whole_citation(self, store):
        cid = first_chunk_id(store)
        fake = FakeLLM([
            {
                "answer": "Svar med delvis påhittad källa.",
                "citations": [{
                    "chunk_id": cid,
                    "quotes": ["Jourperioden för snöröjning", "helt påhittat fragment"],
                }],
                "insufficient_data": False,
            }
        ])
        resp = ask(store, "Vad gäller för jourperioden vid snöröjning?", provider=fake)
        # requireSources default: all citations failed → refusal, nothing shown.
        assert resp.refusal and resp.refusal_reason == "grounding_failed"
        assert resp.citations == []
        assert len(resp.rejected_citations) == 1
        rej = resp.rejected_citations[0]
        assert rej.reason == "quote_not_found"
        assert "påhittat" in rej.quote  # the failing span is the observable one

    def test_mixed_good_single_and_bad_multi(self, store):
        cid = first_chunk_id(store)
        fake = FakeLLM([
            {
                "answer": "Jourperioden löper 15 november till 15 april.",
                "citations": [
                    {"chunk_id": cid, "quote": "löper från 15 november till 15 april"},
                    {"chunk_id": cid, "quotes": ["Halkbekämpning utförs", "fragment som inte finns"]},
                ],
                "insufficient_data": False,
            }
        ])
        resp = ask(store, "När är jourperioden?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1 and resp.citations[0].quotes == ["löper från 15 november till 15 april"]
        assert len(resp.rejected_citations) == 1
        assert resp.warning and "verifieras" in resp.warning

    def test_multispan_with_alias_chunk_id(self, store):
        fake = FakeLLM([
            {
                "answer": "Halkbekämpning sker efter snöröjning.",
                "citations": [{
                    "chunk_id": "K1",
                    "quotes": ["Halkbekämpning utförs", "efter avslutad snöröjning"],
                }],
                "insufficient_data": False,
            }
        ])
        resp = ask(store, "När sker halkbekämpning?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        assert len(resp.citations[0].quotes) == 2

    def test_prompt_documents_multispan_contract(self, store):
        fake = FakeLLM([
            {"answer": "x", "citations": [], "insufficient_data": True}
        ])
        ask(store, "Vad gäller för snöröjningen?", provider=fake)
        system = fake.calls[0]["system"]
        assert '"quotes"' in system  # the contract explains the multi-span form
