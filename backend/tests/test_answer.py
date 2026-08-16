"""Orchestration tests: gates, verification, refusal paths.

Mostly FakeLLM; TestEnvelopeTruncation additionally uses OpenAICompatProvider
with a monkeypatched httpx transport (fixed scripted responses only, no live
model — same pattern as test_llm.py:138-159)."""

import json

import httpx
import pytest

import app.answer as answer_mod
from app.answer import ask
from app.llm import FakeLLM, LLMError, OpenAICompatProvider
from app.schemas import PageData, Settings, Word
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

    def test_coded_table_row_gets_same_document_legend_as_citable_support(self, tmp_path):
        legend = [
            (
                'Kolumnen "utföres av" har markerats med ett "A" för Leverantören '
                'och med ett "B" för Beställaren.',
                72,
                100,
            ),
        ]
        row = [("A2.31.01 Upprättande av årsredovisning A JA", 72, 100)]
        st = Store(data_dir=tmp_path)
        st.add_document("Ansvarsbilaga.pdf", build_pdf([legend, row]))
        st.update_settings(Settings(minRelevance=0.0, topK=1))
        fake = FakeLLM(
            [
                {
                    "answer": "Leverantören ansvarar för att upprätta årsredovisningen.",
                    "citations": [
                        {"chunk_id": "K1", "quote": "A2.31.01 Upprättande av årsredovisning A JA"},
                        {
                            "chunk_id": "K2",
                            "quote": 'Kolumnen "utföres av" har markerats med ett "A" för Leverantören',
                        },
                    ],
                    "insufficient_data": False,
                }
            ]
        )

        resp = ask(st, "Vem ansvarar för att upprätta årsredovisningen?", provider=fake)

        assert not resp.refusal, resp.refusal_reason
        assert len(resp.retrieval) == 2
        assert resp.retrieval[0].page == 2
        assert resp.retrieval[1].page == 1
        assert resp.retrieval[1].score == 0.0
        assert len(resp.citations) == 2
        assert {citation.page for citation in resp.citations} == {1, 2}
        assert '[K2]' in fake.calls[0]["user"]


def _line_words(texts: list[str], *, y0: float = 100.0, block: int = 1, line: int = 1) -> list[Word]:
    """A single visual line of words, left to right, non-overlapping
    (matches tests/test_ocr_ingestion.py's helper)."""
    words = []
    x = 72.0
    for t in texts:
        w = 8.0 * len(t) + 4.0
        words.append(Word(text=t, x0=x, y0=y0, x1=x + w, y1=y0 + 14.0, block=block, line=line))
        x += w + 6.0
    return words


class TestApproximateHighlight:
    """Reality report condition 3: OCR bbox fidelity on scans is ~73-91%
    (clipped, never misplaced) vs 100% on born-digital PDFs. CitationOut.approximate
    flags citations resolved against a scanned-source document so the UI can mark
    the highlight as approximate — verification itself is unchanged either way."""

    def test_scanned_source_citation_marked_approximate(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr(
            "app.store.ocr_pdf",
            lambda data, **kw: [
                PageData(
                    number=1,
                    width=595.0,
                    height=842.0,
                    rotation=0,
                    words=_line_words(["Jourperioden", "löper", "till", "15", "april."]),
                )
            ],
        )
        st = Store(data_dir=tmp_path)
        st.add_document("Skannat.pdf", build_pdf([[]]))
        st.update_settings(Settings(minRelevance=0.0))
        chunk_id = next(iter(st.chunks))
        fake = FakeLLM(
            [
                {
                    "answer": "Jourperioden löper till 15 april.",
                    "citations": [{"chunk_id": chunk_id, "quote": "Jourperioden löper till 15 april"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(st, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        assert resp.citations[0].approximate is True

    def test_digital_source_citation_not_approximate(self, store):
        fake = FakeLLM([good_response(store)])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        assert resp.citations[0].approximate is False


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
        # max_tokens is the envelope budget: maxResponseLength (the user-facing
        # answer budget) plus fixed citation headroom (punch-list #5).
        assert fake.calls[0]["max_tokens"] == 777 + answer_mod._CITATION_HEADROOM_TOKENS


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


ENVELOPE_DOC_LINES = [
    ("Ersättningen för snöröjning regleras i föreningens avtal.", 72, 100),
    ("Ersättning utgår med 1250 kr per påbörjad timme.", 72, 114),
    ("Organisationsnummer", 72, 128),
    ("769600-1234", 72, 142),
]


@pytest.fixture()
def envelope_store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Ersattningsavtal.pdf", build_pdf([ENVELOPE_DOC_LINES]))
    st.update_settings(Settings(minRelevance=0.0, topK=3, maxResponseLength=400))
    return st


class TestEnvelopeTruncation:
    """Regression for punch-list #5 (docs/evidence/reality-report.md:163-165):
    maxResponseLength bounds the ANSWER, not the whole answer+citations JSON
    envelope. A quote-dense response (long answer text + a multi-quote
    citation set) can need more tokens than maxResponseLength alone but fewer
    than maxResponseLength + the citation headroom — that used to truncate
    and refuse with a generic provider_error; it must now succeed."""

    @staticmethod
    def _payload(chunk_id: str, filler_repeat: int) -> dict:
        filler = (
            "Ersättningen för snöröjning regleras i föreningens avtal och beskrivs närmare nedan. "
            * filler_repeat
        ).strip()
        return {
            "answer": filler,
            "citations": [
                {"chunk_id": chunk_id, "quote": "Ersättning utgår med 1250 kr per påbörjad timme"},
                {"chunk_id": chunk_id, "quotes": ["Organisationsnummer", "769600-1234"]},
            ],
            "insufficient_data": False,
        }

    def _provider(self, envelope_store, monkeypatch, filler_repeat: int):
        monkeypatch.setenv("BRF_LLM_BASE_URL", "http://selfhost.local/v1")
        monkeypatch.setenv("BRF_LLM_MODEL", "gemma4:e4b")
        chunk_id = first_chunk_id(envelope_store)
        full_content = json.dumps(self._payload(chunk_id, filler_repeat), ensure_ascii=False)
        # Token need computed deterministically from the full (untruncated)
        # envelope — mirrors a real server's token accounting closely enough
        # to exercise the budget boundary.
        tokens_needed = len(full_content) // 4
        seen_max_tokens: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen_max_tokens.append(body["max_tokens"])
            if body["max_tokens"] < tokens_needed:
                truncated = full_content[: body["max_tokens"] * 4]
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": truncated}, "finish_reason": "length"}]},
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": full_content}, "finish_reason": "stop"}]},
            )

        provider = OpenAICompatProvider(transport=httpx.MockTransport(handler))
        return provider, tokens_needed, seen_max_tokens

    def test_quote_dense_envelope_needs_headroom_beyond_maxResponseLength(self, envelope_store, monkeypatch):
        provider, tokens_needed, seen_max_tokens = self._provider(envelope_store, monkeypatch, filler_repeat=30)
        s = envelope_store.settings

        # Proves this is the previously-failing case: needs more than the bare
        # answer budget, but fits inside answer budget + citation headroom.
        assert s.maxResponseLength < tokens_needed < s.maxResponseLength + answer_mod._CITATION_HEADROOM_TOKENS

        # OLD semantics (max_tokens == maxResponseLength) truncate — independent
        # of the fix, this documents the regression this test guards against.
        with pytest.raises(LLMError, match="trunkerades"):
            provider.complete("sys", "user", max_tokens=s.maxResponseLength, model="m")

        # NEW semantics via ask(): the envelope gets citation headroom, so the
        # full JSON arrives, both citations verify, and the answer is returned
        # — no refusal.
        resp = ask(envelope_store, "Vad gäller ersättningen och organisationsnumret?", provider=provider)
        assert not resp.refusal, f"unexpected refusal: {resp.refusal_reason}"
        assert resp.answer.startswith("Ersättningen för snöröjning")
        assert len(resp.citations) == 2
        assert {tuple(c.quotes) for c in resp.citations} == {
            ("Ersättning utgår med 1250 kr per påbörjad timme",),
            ("Organisationsnummer", "769600-1234"),
        }
        assert seen_max_tokens[-1] == s.maxResponseLength + answer_mod._CITATION_HEADROOM_TOKENS

    def test_still_refuses_honestly_when_envelope_budget_also_exceeded(self, envelope_store, monkeypatch):
        # A genuinely oversized reply — the fix adds headroom, it doesn't
        # remove the ceiling. filler_repeat chosen with a large margin so this
        # holds even if the headroom constant changes later.
        provider, tokens_needed, _ = self._provider(envelope_store, monkeypatch, filler_repeat=60)
        s = envelope_store.settings
        assert tokens_needed > s.maxResponseLength + answer_mod._CITATION_HEADROOM_TOKENS + 100

        resp = ask(envelope_store, "Vad gäller ersättningen och organisationsnumret?", provider=provider)
        assert resp.refusal and resp.refusal_reason == "provider_error"


NUMERIC_LINES = [
    ("Ekonomisk analys för underhållsplanen.", 72, 100),
    ("Total utgift 15 659 566 kr", 72, 114),
    ("Investering 8 773 000 kr", 72, 128),
    ("Avgift per m² 151 kr per m² och år", 72, 142),
    ("Antal lägenheter: 56 lägenheter", 72, 156),
    ("Rekommenderad avsättning 8,5 %", 72, 170),
    ("Planen gäller år 2032", 72, 184),
]


@pytest.fixture()
def numeric_store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Underhallsplan.pdf", build_pdf([NUMERIC_LINES]))
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    return st


def numeric_chunk_id(store: Store) -> str:
    return next(iter(store.chunks))


class TestNumericGroundingGate:
    """Production-defect regression (SPEC §2.10): a citation quote can verify
    verbatim — proving that text really is in the document — while the
    model's own free-text `answer` asserts a DIFFERENT number alongside it.
    app/citations.py has no visibility into `answer` at all, so this was
    previously invisible to every existing gate. app/numeric_grounding.py
    closes exactly that hole; these tests exercise it through the full ask()
    pipeline (see tests/test_numeric_grounding.py for the pure-function unit
    tests of the gate itself)."""

    # ---- must fail or refuse ----

    def test_transposed_digits_refused_not_silently_accepted(self, numeric_store):
        """The exact reported production defect: verified quote says
        '15 659 566 kr', model answer says '1 565 956 kr'. The repair
        attempt (scripted here to repeat the same mistake) also fails —
        final result must be a safe refusal, never the unsupported number."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Den totala utgiften är 1 565 956 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"
        assert "1 565 956" not in resp.answer
        assert len(fake.calls) == 2  # exactly one repair attempt — not unbounded

    def test_wrong_investment_figure_refused(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Investeringen är 8 737 000 kr.",
            "citations": [{"chunk_id": cid, "quote": "Investering 8 773 000 kr"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Vad är investeringen?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_wrong_per_sqm_fee_refused(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Avgiften är 115 kr per m² och år.",
            "citations": [{"chunk_id": cid, "quote": "Avgift per m² 151 kr per m² och år"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Vad är avgiften per kvadratmeter?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_wrong_apartment_count_refused(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Föreningen har 65 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter finns det?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_number_present_only_outside_verified_quote_refused(self, numeric_store):
        """A number must not be treated as supported merely because it
        appears somewhere near the citation (filename, page metadata, a
        neighboring sentence) — support comes ONLY from the accepted
        citation's own verified quote text. Here the claimed number (42)
        appears nowhere in the corpus at all — including not in the quote —
        which is the cleanest proof that quote text is the only source of
        support the gate consults."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Kostnaden uppgår till 42 kr.",
            "citations": [{"chunk_id": cid, "quote": "Ekonomisk analys för underhållsplanen"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Vad kostar det?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    # ---- must pass ----

    def test_exact_value_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Den totala utgiften är 15 659 566 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        assert not resp.refusal
        assert len(fake.calls) == 1  # no repair needed

    def test_equivalent_whitespace_separators_pass(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            # NBSP-grouped in the answer vs regular-space in the quote.
            "answer": "Den totala utgiften är 15 659 566 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        assert not resp.refusal

    def test_exact_percentage_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Den rekommenderade avsättningen är 8,5 %.",
            "citations": [{"chunk_id": cid, "quote": "Rekommenderad avsättning 8,5 %"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur stor är avsättningen?", provider=fake)
        assert not resp.refusal

    def test_exact_year_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Planen gäller år 2032.",
            "citations": [{"chunk_id": cid, "quote": "Planen gäller år 2032"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Vilket år gäller planen?", provider=fake)
        assert not resp.refusal

    def test_multiple_claims_each_supported_by_a_different_citation_pass(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Föreningen har 56 lägenheter och betalar 151 kr per m² och år.",
            "citations": [
                {"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"},
                {"chunk_id": cid, "quote": "Avgift per m² 151 kr per m² och år"},
            ],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter och vad kostar det per kvm?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 2

    def test_ordinary_non_numeric_answer_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Dokumentet beskriver föreningens ekonomiska analys.",
            "citations": [{"chunk_id": cid, "quote": "Ekonomisk analys för underhållsplanen"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Vad handlar dokumentet om?", provider=fake)
        assert not resp.refusal
        assert len(fake.calls) == 1

    def test_safe_refusal_with_no_asserted_claims_untouched_by_gate(self, numeric_store):
        fake = FakeLLM([{"answer": "Uppgift saknas.", "citations": [], "insufficient_data": True}])
        resp = ask(numeric_store, "Vad kostar det icke-existerande garaget?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "insufficient_data"
        assert len(fake.calls) == 1  # refusal never enters the numeric-repair loop

    # ---- repair behavior ----

    def test_repair_attempt_with_corrected_number_succeeds(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Den totala utgiften är 1 565 956 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        good = {
            "answer": "Den totala utgiften är 15 659 566 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, good])
        resp = ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        assert not resp.refusal
        assert "15 659 566" in resp.answer
        assert len(fake.calls) == 2
        # The repair prompt must describe the specific mismatch, not just
        # generically ask the model to try again.
        assert "1 565 956" in fake.calls[1]["system"]

    def test_both_attempts_fail_yields_safe_refusal_not_unsupported_answer(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        first = {
            "answer": "Den totala utgiften är 1 565 956 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        second = {
            "answer": "Den totala utgiften är 15 995 656 kr.",  # a different wrong number
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([first, second])
        resp = ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"
        assert "1 565 956" not in resp.answer and "15 995 656" not in resp.answer
        assert len(fake.calls) == 2  # bounded — no third attempt

    def test_base_prompt_instructs_copying_numbers_exactly(self, numeric_store):
        fake = FakeLLM([{"answer": "x", "citations": [], "insufficient_data": True}])
        ask(numeric_store, "Vad är den totala utgiften?", provider=fake)
        system = fake.calls[0]["system"].lower()
        assert "siffr" in system or "tal" in system


class TestNumericIdentifierExemption:
    """SPEC 2.10 follow-up: a digit that is part of a verified ENTITY NAME
    (the tenant's own registered name, an accepted citation's document
    title) is not a factual claim and must not trigger numeric_grounding_failed.
    Reproduces the real pilot false refusal ("BRF GJUTFORMEN 12" refused
    solely because of the identifier 12 — see docs/evidence/numeric-grounding.md)
    through the full ask() pipeline, with trusted_names passed exactly as
    main.py's /ask route now passes it (sourced from auth.get_tenant())."""

    TENANT = "Brf Gjutformen 12"

    # ---- the regression itself: proves the false refusal, then the fix ----

    def test_tenant_name_with_identifier_passes_when_all_other_claims_supported(self, numeric_store):
        """The exact confirmed defect: an answer that repeats the tenant's
        own registered name (containing the digit 12) alongside a genuinely
        supported claim must NOT be refused. Before the fix (no trusted_names
        parameter existed on ask()/check_numeric_grounding at all), this
        scenario refused with numeric_grounding_failed solely because "12"
        had no citation support — even though "12" was never a claim."""
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "BRF GJUTFORMEN 12 har sitt säte i Göteborg och har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter har föreningen?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason
        assert len(fake.calls) == 1  # no repair needed — nothing was ever unsupported

    def test_without_trusted_names_the_same_answer_is_refused(self, numeric_store):
        """Control case: omitting trusted_names (the pre-fix default for
        every existing call site) reproduces the false refusal exactly —
        proves the exemption is doing the work, not some unrelated change."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "BRF GJUTFORMEN 12 har sitt säte i Göteborg och har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter har föreningen?", provider=fake)  # no trusted_names
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_casefolded_tenant_name_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "brf gjutformen 12 har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason

    def test_nbsp_and_narrow_nbsp_variants_in_tenant_mention_pass(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": f"BRF{chr(0x00A0)}GJUTFORMEN{chr(0x202F)}12 har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason

    def test_punctuation_around_the_exact_name_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Föreningen (Brf Gjutformen 12) har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason

    def test_repeated_exact_name_mentions_pass(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Brf Gjutformen 12 har 56 lägenheter. Brf Gjutformen 12 grundades för länge sedan.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason

    # ---- must NOT be exempted ----

    def test_partial_tenant_name_match_does_not_exempt_the_number(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Gjutformen 12 har 56 lägenheter.",  # missing "Brf" — not the exact span
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_fabricated_tenant_name_does_not_exempt_the_number(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Falska Föreningen 99 har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_wrong_number_in_tenant_name_does_not_pass(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Brf Gjutformen 13 har 56 lägenheter.",  # 13, not the real 12
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_same_number_outside_the_exact_span_remains_unsupported(self, numeric_store):
        """"12" legitimately appears inside the trusted tenant name AND,
        separately, as an unrelated bare claim later in the sentence — the
        second occurrence is a distinct claim and must still be refused."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Brf Gjutformen 12 har haft 12 stämmor de senaste åren.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många stämmor har hållits?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_tenant_name_plus_a_separate_unsupported_quantity_still_fails(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Brf Gjutformen 12 har 65 lägenheter.",  # wrong count: 65, not 56
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_tenant_name_plus_a_supported_quantity_passes(self, numeric_store):
        cid = numeric_chunk_id(numeric_store)
        fake = FakeLLM([{
            "answer": "Brf Gjutformen 12 har 56 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=[self.TENANT])
        assert not resp.refusal, resp.refusal_reason

    def test_arbitrary_numbers_from_the_question_are_never_trusted(self, numeric_store):
        """The question text itself must never become a trusted span — only
        auth.get_tenant()'s registered name and accepted citation titles
        may. Asking a question containing a number close to the fabricated
        claim must not launder it into "support"."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Föreningen har 999 lägenheter.",
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(
            numeric_store, "Har föreningen 999 lägenheter?", provider=fake, trusted_names=[self.TENANT]
        )
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_rejected_citation_never_contributes_a_trusted_title(self, numeric_store):
        """RejectedCitation (schemas.py) carries no document_name at all — a
        rejected citation structurally cannot ever seed a trusted span. Two
        citations here: one genuinely verifies (supports "56"), the other's
        quote text is not present in the chunk and is rejected; "77" is
        asserted only near the rejected citation and must stay unsupported."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Föreningen har 56 lägenheter och kostar 77 kr per kvadratmeter.",
            "citations": [
                {"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"},
                {"chunk_id": cid, "quote": "Det här citatet finns inte alls i dokumentet någonstans"},
            ],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(numeric_store, "Vad kostar det per kvm?", provider=fake, trusted_names=[self.TENANT])
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"

    def test_generator_trusted_names_is_not_exhausted_before_the_repair_check(self, numeric_store):
        """trusted_names is consulted twice — once for the initial response,
        once for a possible repair — so a one-shot generator must not be
        silently exhausted after the first use. Without materializing it
        once up front, the repair's own numeric check would see an empty
        trusted-names set and wrongly flag the tenant name's "12" as
        unsupported even though it was correctly exempt on the first pass."""
        cid = numeric_chunk_id(numeric_store)
        bad = {
            "answer": "Brf Gjutformen 12 har 65 lägenheter.",  # wrong count -> triggers repair
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        good = {
            "answer": "Brf Gjutformen 12 har 56 lägenheter.",  # corrected, tenant name repeated
            "citations": [{"chunk_id": cid, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, good])
        trusted_names_generator = (n for n in [self.TENANT])
        resp = ask(numeric_store, "Hur många lägenheter?", provider=fake, trusted_names=trusted_names_generator)
        assert not resp.refusal, resp.refusal_reason
        assert "56" in resp.answer
        assert len(fake.calls) == 2  # repair happened, and the tenant name was still exempt on it


TITLED_LINES = [
    ("Underhållsplanen beskriver kommande åtgärder.", 72, 100),
    ("Total utgift 15 659 566 kr", 72, 114),
]


@pytest.fixture()
def titled_store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Underhallsplan-2026-2036.pdf", build_pdf([TITLED_LINES]))
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    return st


class TestAcceptedCitationTitleAsTrustedSpan:
    """Optional narrower half of the identifier fix: an ACCEPTED citation's
    exact full document title may itself be mentioned in the answer without
    its embedded numbers (e.g. a year in the filename) being treated as
    unsupported claims. Conservative by construction: only the citation's
    OWN document_name counts, and only when that citation actually verified."""

    def test_exact_title_mention_with_embedded_year_passes(self, titled_store):
        cid = next(iter(titled_store.chunks))
        fake = FakeLLM([{
            "answer": "Enligt Underhallsplan-2026-2036.pdf är den totala utgiften 15 659 566 kr.",
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }])
        resp = ask(titled_store, "Vad är den totala utgiften?", provider=fake)
        assert not resp.refusal, resp.refusal_reason

    def test_year_outside_the_exact_title_span_still_requires_quote_support(self, titled_store):
        """The SAME year (2026) restated as an independent claim outside the
        title string is a distinct assertion and must still be refused when
        unsupported — title-exemption must not blanket-exempt the value."""
        cid = next(iter(titled_store.chunks))
        bad = {
            "answer": (
                "Enligt Underhallsplan-2026-2036.pdf är den totala utgiften 15 659 566 kr. "
                "Planen antogs av styrelsen år 2026."
            ),
            "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        resp = ask(titled_store, "Vad är den totala utgiften?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "numeric_grounding_failed"


class TestEntailmentWarning:
    """LettuceDetect runs after citations are verified and drawn. It warns.
    It does not refuse, and it does not replace citation or numeric gates."""

    def test_flags_unsupported_claim_without_refusing(self, store, monkeypatch):
        monkeypatch.setenv("BRF_ENTAILMENT", "1")

        def fake_spans(quotes, question, answer, min_confidence):
            assert quotes
            return [{"start": 0, "end": len(answer), "confidence": 0.88, "text": answer}]

        monkeypatch.setattr("app.entailment._predict_spans", fake_spans)
        fake = FakeLLM([good_response(store)])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert resp.citations
        assert resp.warning
        assert "citerade källorna" in resp.warning

    def test_does_not_warn_when_detector_finds_no_spans(self, store, monkeypatch):
        monkeypatch.setenv("BRF_ENTAILMENT", "1")
        monkeypatch.setattr("app.entailment._predict_spans", lambda *_a, **_k: [])
        fake = FakeLLM([good_response(store)])
        resp = ask(store, "När löper jourperioden?", provider=fake)
        assert not resp.refusal
        assert resp.citations
        assert resp.warning is None

    def test_does_not_replace_citation_refusal(self, store, monkeypatch):
        monkeypatch.setenv("BRF_ENTAILMENT", "1")

        def boom(*_a, **_k):
            raise AssertionError("entailment must not run on a citation refusal")

        monkeypatch.setattr("app.entailment._predict_spans", boom)
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
