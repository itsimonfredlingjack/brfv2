"""Planned cross-document answering (BRF-1): plan → fan-out → pack → verify.

Uses FakeLLM throughout — the planner call and the synthesis call are two
separate `complete()` calls, so a FakeLLM script lists the plan first and the
answer second. Retrieval, citation resolution and the numeric gate are the
real ones.
"""

import pytest

from app.answer import ask
from app.evidence import EvidencePack, expand_context
from app.llm import FakeLLM, LLMError
from app.multihop import MAX_EVIDENCE_CHUNKS, ask_planned
from app.query_plan import MAX_SUBQUERIES, plan_query
from app.schemas import Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf

AVTAL = [
    ("Snöröjningsavtalet gäller från 1 oktober 2025 till 30 september 2026.", 72, 100),
    ("Leverantör är Vinterservice AB med organisationsnummer 556677-8899.", 72, 114),
    ("Ersättning utgår med 1250 kr per påbörjad timme.", 72, 128),
]
PROTOKOLL = [
    ("Styrelsen beslutade att godkänna snöröjningsavtalet vid mötet.", 72, 100),
    ("Beslutet fattades enhälligt av en styrelse på sju ledamöter.", 72, 114),
    ("Ordföranden fick i uppdrag att underteckna handlingen.", 72, 128),
]


@pytest.fixture()
def store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Snöröjningsavtal.pdf", build_pdf([AVTAL]))
    st.add_document("Styrelseprotokoll.pdf", build_pdf([PROTOKOLL]))
    st.update_settings(Settings(minRelevance=0.05, topK=3))
    return st


@pytest.fixture()
def dense_store(tmp_path) -> Store:
    """A page that really does chunk into several neighbours.

    The `store` fixture's documents are short enough to become ONE chunk per
    page, which makes every context-expansion assertion vacuous — a broken
    `expand_context` passed the whole suite until this fixture existed.
    """
    lines = [
        (f"Rad {i}: underhållsplanen beskriver åtgärd nummer {i} med tillhörande kostnad och tidpunkt för utförande.", 72, 90 + 14 * i)
        for i in range(12)
    ]
    st = Store(data_dir=tmp_path)
    st.add_document("Underhållsplan.pdf", build_pdf([lines]))
    st.update_settings(Settings(minRelevance=0.05, topK=2, chunkSize=20, chunkOverlap=0))
    return st


@pytest.fixture()
def wide_store(tmp_path) -> Store:
    """Enough distinct matter that the evidence ceiling actually binds.

    The `store` fixture holds two chunks, so `<= MAX_EVIDENCE_CHUNKS` (10)
    held there no matter what the cap did. Three disjoint vocabularies, seven
    chunks each: a three-subquery fan-out retrieves 3 × PER_QUERY_TOP_K = 12
    distinct excerpts and the ceiling is reached rather than assumed.
    """
    st = Store(data_dir=tmp_path)
    for topic, word in (
        ("Sophantering", "sophämtning"),
        ("Hissunderhåll", "hissmotor"),
        ("Fasadrenovering", "fogbruk"),
    ):
        lines = [
            (f"{word} punkt {i}: bestämmelsen om {word} nummer {i} gäller hela föreningen.", 72, 90 + 14 * i)
            for i in range(14)
        ]
        st.add_document(f"{topic}.pdf", build_pdf([lines]))
    st.update_settings(Settings(minRelevance=0.05, topK=3, chunkSize=20, chunkOverlap=0))
    return st


def chunk_id_containing(store: Store, needle: str) -> str:
    for cid, chunk in store.chunks.items():
        if needle in chunk.text:
            return cid
    raise AssertionError(f"ingen chunk innehåller {needle!r}")


class TestQueryPlan:
    def test_single_is_the_default_shape(self):
        fake = FakeLLM([{"mode": "single", "subqueries": [], "clarification": ""}])
        plan = plan_query("Vad kostar snöröjningen?", fake)
        assert plan.mode == "single"
        assert plan.subqueries == ["Vad kostar snöröjningen?"]
        assert not plan.degraded

    def test_multi_keeps_focused_subqueries(self):
        fake = FakeLLM([{
            "mode": "multi",
            "subqueries": ["snöröjningsavtalets leverantör", "styrelsens beslut om snöröjning"],
            "clarification": "",
        }])
        plan = plan_query("Vem är leverantör och godkände styrelsen avtalet?", fake)
        assert plan.mode == "multi"
        assert len(plan.subqueries) == 2
        assert not plan.truncated

    def test_subquery_budget_is_enforced_by_the_application(self):
        """The cap is code, not a request to the model."""
        fake = FakeLLM([{
            "mode": "multi",
            "subqueries": [f"delfråga {i}" for i in range(12)],
            "clarification": "",
        }])
        plan = plan_query("En bred fråga", fake)
        assert len(plan.subqueries) == MAX_SUBQUERIES
        assert plan.truncated

    def test_clarify_carries_a_counter_question(self):
        fake = FakeLLM([{
            "mode": "clarify",
            "subqueries": [],
            "clarification": "Vilket av era två avtal menar du?",
        }])
        plan = plan_query("Vad står det i avtalet?", fake)
        assert plan.mode == "clarify"
        assert plan.subqueries == []
        assert "avtal" in plan.clarification

    def test_clarify_without_a_question_degrades_to_search(self):
        fake = FakeLLM([{"mode": "clarify", "subqueries": [], "clarification": "  "}])
        plan = plan_query("Vad står det i avtalet?", fake)
        assert plan.mode == "single" and plan.degraded

    def test_multi_with_one_subquery_is_just_single(self):
        fake = FakeLLM([{"mode": "multi", "subqueries": ["bara en"], "clarification": ""}])
        assert plan_query("Fråga", fake).mode == "single"

    def test_unknown_mode_falls_back_to_single(self):
        fake = FakeLLM([{"mode": "agentic", "subqueries": ["x"], "clarification": ""}])
        plan = plan_query("Fråga", fake)
        assert plan.mode == "single" and plan.degraded

    def test_planner_failure_never_blocks_the_question(self):
        plan = plan_query("Vad kostar snöröjningen?", FakeLLM([]))  # raises LLMError
        assert plan.mode == "single"
        assert plan.subqueries == ["Vad kostar snöröjningen?"]
        assert plan.degraded

    def test_planner_is_never_shown_document_content(self, store):
        fake = FakeLLM([{"mode": "single", "subqueries": [], "clarification": ""}])
        plan_query("Fråga", fake, document_names=["Snöröjningsavtal.pdf"])
        user = fake.calls[0]["user"]
        assert "Snöröjningsavtal.pdf" in user
        assert "1250 kr" not in user  # names only, never excerpts

    def test_catalogue_order_is_the_corpus_not_its_upload_history(self, tmp_path):
        """The plan must be a function of WHICH documents exist, not of the
        order they happened to be uploaded in.

        Decoding is greedy, so catalogue order was the last remaining source
        of run-to-run variance — and an undesigned one: re-uploading a
        document could change how a question got planned. Measured before the
        sort, 22 of 59 cases changed mode when the catalogue was shuffled.
        """
        uploaded = ["Ärendelista.pdf", "budget.pdf", "Avtal.pdf", "Zonkarta.pdf", "årsredovisning.pdf"]
        st = Store(data_dir=tmp_path)
        for name in uploaded:
            st.add_document(name, build_pdf([[("Innehåll utan betydelse här.", 72, 100)]]))

        # Non-vacuity: upload order must not already be the sorted order,
        # or the assertion below would hold with no sort at all.
        assert [m.name for m in st.documents.values()] == uploaded
        assert uploaded != sorted(uploaded, key=lambda n: (n.casefold(), n))

        fake = FakeLLM([
            {"mode": "single", "subqueries": [], "clarification": ""},
            {"answer": "Vet ej.", "citations": [], "insufficient_data": True},
        ])
        ask_planned(st, "Vad gäller?", provider=fake)
        planner_user = fake.calls[0]["user"]

        positions = [planner_user.index(n) for n in uploaded]
        by_position = [n for _, n in sorted(zip(positions, uploaded))]
        assert by_position == sorted(uploaded, key=lambda n: (n.casefold(), n)), (
            "katalogen skickas i uppladdningsordning — planen beror på historik"
        )


class TestEvidencePack:
    def test_deduplication_keeps_first_and_records_the_repeat(self, store):
        index = store.index
        pack = EvidencePack(question="Q")
        hits = index.search("snöröjning ersättning", weight=0.5, candidates=50, top_k=3, min_confidence=0.0)
        assert hits
        pack.add_query("a", hits, plan_index=0)
        before = len(pack.hits)
        record = pack.add_query("b", hits, plan_index=1)
        assert len(pack.hits) == before, "samma chunk får inte hamna två gånger i prompten"
        assert record.duplicate_ids == [h.chunk_id for h in hits]
        assert pack.duplicate_count == len(hits)

    def test_pack_reports_the_documents_it_spans(self, store):
        index = store.index
        pack = EvidencePack(question="Q")
        pack.add_query("leverantör organisationsnummer", index.search(
            "leverantör organisationsnummer", weight=0.5, candidates=50, top_k=2, min_confidence=0.0))
        pack.add_query("styrelsen beslutade godkänna", index.search(
            "styrelsen beslutade godkänna", weight=0.5, candidates=50, top_k=2, min_confidence=0.0))
        assert len(pack.document_ids) == 2
        assert len(pack.document_names) == 2

    def test_the_dense_fixture_really_has_neighbours(self, dense_store):
        """Guards the guard: without several chunks on one page, every
        expansion assertion below would pass vacuously."""
        assert len(dense_store.chunks) >= 3

    def test_expansion_adds_real_citable_chunks_only(self, dense_store):
        """The invariant: an expanded excerpt is a real Chunk with its real
        id and its OWN unspliced text, so the unchanged citation path can
        verify a quote from it against the real page words."""
        index = dense_store.index
        pack = EvidencePack(question="Q")
        pack.add_query("åtgärd kostnad tidpunkt", index.search(
            "åtgärd kostnad tidpunkt", weight=0.5, candidates=50, top_k=1, min_confidence=0.0))
        added = expand_context(pack, dense_store.chunks, dense_store.documents, max_added=4)
        assert added > 0, "fixturen gav inga grannar — testet vore verkningslöst"
        for cid in pack.expanded_ids:
            assert cid in dense_store.chunks, "expansion får aldrig hitta på ett chunk-id"
            hit = next(h for h in pack.hits if h.chunk_id == cid)
            assert hit.text == dense_store.chunks[cid].text, "texten får aldrig skarvas ihop"
            assert hit.page == dense_store.chunks[cid].page
        assert added == len(pack.expanded_ids)

    def test_an_expanded_chunk_can_actually_be_cited(self, dense_store):
        """The end-to-end form of the identity invariant: a quote taken from
        an EXPANDED excerpt must survive real citation verification."""
        index = dense_store.index
        pack = EvidencePack(question="Q")
        pack.add_query("åtgärd kostnad", index.search(
            "åtgärd kostnad", weight=0.5, candidates=50, top_k=1, min_confidence=0.0))
        assert expand_context(pack, dense_store.chunks, dense_store.documents, max_added=2) > 0
        expanded_id = pack.expanded_ids[0]
        quote = " ".join(dense_store.chunks[expanded_id].text.split()[:6])
        fake = FakeLLM([{
            "answer": "Se underhållsplanen.",
            "citations": [{"chunk_id": expanded_id, "quote": quote}],
            "insufficient_data": False,
        }])
        resp = ask(dense_store, "Vad står i underhållsplanen?", provider=fake, evidence=pack)
        assert not resp.refusal, resp.answer
        assert [c.chunk_id for c in resp.citations] == [expanded_id]
        assert resp.citations[0].rects

    def test_expanded_hits_do_not_inflate_the_relevance_signal(self, dense_store):
        index = dense_store.index
        pack = EvidencePack(question="Q")
        pack.add_query("åtgärd kostnad", index.search(
            "åtgärd kostnad", weight=0.5, candidates=50, top_k=1, min_confidence=0.0))
        assert expand_context(pack, dense_store.chunks, dense_store.documents, max_added=4) > 0
        for cid in pack.expanded_ids:
            hit = next(h for h in pack.hits if h.chunk_id == cid)
            assert hit.confidence == 0.0 and hit.score == 0.0

    def test_expansion_never_crosses_a_page_boundary(self, dense_store):
        pack = EvidencePack(question="Q")
        pack.add_query("åtgärd", dense_store.index.search(
            "åtgärd", weight=0.5, candidates=50, top_k=1, min_confidence=0.0))
        seed_pages = {dense_store.chunks[h.chunk_id].page for h in pack.hits}
        assert expand_context(pack, dense_store.chunks, dense_store.documents, max_added=8) > 0
        for cid in pack.expanded_ids:
            assert dense_store.chunks[cid].page in seed_pages

    def test_expansion_respects_its_budget(self, dense_store):
        pack = EvidencePack(question="Q")
        pack.add_query("åtgärd", dense_store.index.search(
            "åtgärd", weight=0.5, candidates=50, top_k=3, min_confidence=0.0))
        assert expand_context(pack, dense_store.chunks, dense_store.documents, max_added=1) == 1


class TestPlannedAnswering:
    def test_clarify_refuses_instead_of_guessing(self, store):
        fake = FakeLLM([{
            "mode": "clarify", "subqueries": [],
            "clarification": "Menar du snöröjningsavtalet eller styrelseprotokollet?",
        }])
        result = ask_planned(store, "Vad står det i dokumentet?", provider=fake)
        assert result.plan.mode == "clarify"
        assert result.response.refusal
        assert result.response.citations == []
        assert "Menar du" in result.response.answer
        assert len(fake.calls) == 1, "en clarify får inte kosta en syntes-körning"

    def test_two_document_answer_verifies_through_the_existing_path(self, store):
        avtal = chunk_id_containing(store, "Vinterservice AB")
        protokoll = chunk_id_containing(store, "godkänna snöröjningsavtalet")
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "leverantör snöröjningsavtal organisationsnummer",
                "styrelsen beslutade godkänna snöröjningsavtalet",
            ]},
            {
                "answer": "Leverantör är Vinterservice AB och styrelsen beslutade att godkänna avtalet.",
                "citations": [
                    {"chunk_id": avtal, "quote": "Leverantör är Vinterservice AB"},
                    {"chunk_id": protokoll, "quote": "Styrelsen beslutade att godkänna snöröjningsavtalet"},
                ],
                "insufficient_data": False,
            },
        ])
        result = ask_planned(store, "Vem är leverantör och har styrelsen godkänt avtalet?", provider=fake)

        assert result.plan.mode == "multi"
        assert not result.response.refusal, result.response.answer
        assert len(result.response.citations) == 2
        # Real verification produced real page rects on both citations.
        assert all(c.rects for c in result.response.citations)
        assert len({c.document_id for c in result.response.citations}) == 2
        assert len(result.pack.document_ids) == 2
        assert len(result.pack.executed) == 2

    def test_the_original_question_is_what_gets_answered(self, store):
        """Subqueries are a retrieval instrument — the board asked something
        else, and that is what must reach the synthesis prompt."""
        avtal = chunk_id_containing(store, "Vinterservice AB")
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": ["leverantör", "styrelsens beslut"]},
            {"answer": "Vinterservice AB.",
             "citations": [{"chunk_id": avtal, "quote": "Leverantör är Vinterservice AB"}],
             "insufficient_data": False},
        ])
        question = "Vem är leverantör och har styrelsen godkänt avtalet?"
        ask_planned(store, question, provider=fake)
        synthesis_user = fake.calls[1]["user"]
        assert synthesis_user.startswith(f"FRÅGA: {question}")

    def test_ungrounded_citation_is_still_rejected_on_the_planned_path(self, store):
        """No weaker verification for multi-document answers."""
        avtal = chunk_id_containing(store, "Vinterservice AB")
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": ["leverantör", "styrelsens beslut"]},
            {"answer": "Leverantören heter Sommarservice AB.",
             "citations": [{"chunk_id": avtal, "quote": "Leverantör är Sommarservice AB"}],
             "insufficient_data": False},
        ])
        result = ask_planned(store, "Vem är leverantör och godkände styrelsen avtalet?", provider=fake)
        assert result.response.refusal
        assert result.response.refusal_reason == "grounding_failed"

    def test_numeric_gate_still_applies_on_the_planned_path(self, store):
        avtal = chunk_id_containing(store, "1250 kr")
        bad = {"answer": "Ersättningen är 1450 kr per timme.",
               "citations": [{"chunk_id": avtal, "quote": "Ersättning utgår med 1250 kr per påbörjad timme"}],
               "insufficient_data": False}
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": ["ersättning timme", "styrelsens beslut"]},
            bad, bad,  # original + the one allowed repair attempt
        ])
        result = ask_planned(store, "Vad är ersättningen och vem beslutade?", provider=fake)
        assert result.response.refusal
        assert result.response.refusal_reason == "numeric_grounding_failed"

    def test_single_plan_uses_the_unchanged_path(self, store):
        avtal = chunk_id_containing(store, "1250 kr")
        fake = FakeLLM([
            {"mode": "single", "subqueries": [], "clarification": ""},
            {"answer": "1250 kr per påbörjad timme.",
             "citations": [{"chunk_id": avtal, "quote": "Ersättning utgår med 1250 kr per påbörjad timme"}],
             "insufficient_data": False},
        ])
        result = ask_planned(store, "Vad är ersättningen per timme?", provider=fake)
        assert result.plan.mode == "single"
        assert not result.response.refusal
        assert result.response.citations

    def test_evidence_is_bounded(self, wide_store):
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "sophämtning", "hissmotor", "fogbruk"]},
            {"answer": "Vet ej.", "citations": [], "insufficient_data": True},
        ])
        result = ask_planned(wide_store, "Berätta allt", provider=fake)

        # Non-vacuity first: unless the fan-out found MORE than the ceiling,
        # the assertion below holds whatever the ceiling does. This test read
        # `<= MAX_EVIDENCE_CHUNKS` against a two-chunk corpus for a while and
        # asserted nothing at all.
        distinct_found = len({cid for e in result.pack.executed for cid in e.hit_ids})
        assert distinct_found > MAX_EVIDENCE_CHUNKS, (
            f"fan-outen hittade bara {distinct_found} chunkar — taket ({MAX_EVIDENCE_CHUNKS}) "
            "biter inte och testet mäter ingenting"
        )
        assert len(result.pack.hits) == MAX_EVIDENCE_CHUNKS

    def test_low_relevance_refuses_on_the_planned_path_too(self, store):
        """XS-64 gate parity.

        `ask()` used to pass `low_relevance=False` for a supplied evidence
        pack, so the fan-out's own excerpts were relevant by construction:
        the planned path could neither refuse on a thin corpus nor warn about
        one, and answered where the single path refused.
        """
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.99}))
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "snöröjning leverantör", "styrelsens beslut"]},
            {"answer": "Något.", "citations": [], "insufficient_data": False},
        ])
        result = ask_planned(store, "Hur fungerar kvantdatorer?", provider=fake)

        # Non-vacuity: the fan-out must have FOUND something, or the existing
        # empty-pack branch would return the same refusal without the gate.
        assert result.pack.hits, "tom bevispåse — då mäter testet fel gren"
        assert result.response.refusal
        assert result.response.refusal_reason == "low_relevance"
        assert len(fake.calls) == 1, "grinden ska stoppa före syntesen, inte efter"

    def test_low_relevance_warns_on_the_planned_path_in_warn_mode(self, store):
        """Same gate, warn mode: the answer is shown but must carry the
        uncertainty. Silently confident is the failure this catches."""
        avtal = chunk_id_containing(store, "Vinterservice AB")
        store.update_settings(store.settings.model_copy(
            update={"minRelevance": 0.99, "insufficientDataBehavior": "warn"}))
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "snöröjning leverantör", "styrelsens beslut"]},
            {"answer": "Leverantör är Vinterservice AB.",
             "citations": [{"chunk_id": avtal, "quote": "Leverantör är Vinterservice AB"}],
             "insufficient_data": False},
        ])
        result = ask_planned(store, "Vem är leverantör och vad beslutade styrelsen?", provider=fake)

        assert result.pack.hits
        assert not result.response.refusal
        assert result.response.warning and "Osäkert underlag" in result.response.warning

    def test_rerank_unavailable_is_loud_on_the_planned_path_too(self, store, monkeypatch):
        """XS-64 gate parity. The rerank check sat AFTER the evidence branch,
        so the planned path answered with unreranked hits while the single
        path raised — a second, quieter route past a gate that exists to be
        loud."""
        monkeypatch.setattr("app.answer.reranker_available", lambda: False)
        store.update_settings(store.settings.model_copy(update={"rerankEnabled": True}))
        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "snöröjning leverantör", "styrelsens beslut"]},
            {"answer": "Något.", "citations": [], "insufficient_data": False},
        ])

        with pytest.raises(LLMError, match="Omrankning"):
            ask_planned(store, "Vem är leverantör och vad beslutade styrelsen?", provider=fake)

        assert len(fake.calls) == 1, "bara planeringen fick köra; ingen syntes"

    def test_linked_legend_reaches_the_planned_prompt_too(self, tmp_path):
        """XS-64 gate parity, decision 1c. A coded leaf row is unreadable
        without the legend that defines its letter, and neither the citation
        resolver nor the numeric gate catches the resulting error: the quote
        is verbatim and the false claim is a WORD, not a number."""
        ekonomi = [
            (f"A2.31.{i:02d} Upprättande av årsredovisning och bokslut delmoment {i} A JA", 72, 90 + 14 * i)
            for i in range(8)
        ]
        underhall = [
            (f"A4.12.{i:02d} Besiktning av fasad och tak delmoment {i} B JA", 72, 90 + 14 * i)
            for i in range(8)
        ]
        st = Store(data_dir=tmp_path)
        st.add_document("Underhållsavtal.pdf", build_pdf([
            [('Kolumnen "utföres av" har markerats med ett "A" för Leverantören '
              'och med ett "B" för Beställaren.', 72, 100)],
            ekonomi,
            underhall,
        ]))
        st.update_settings(Settings(minRelevance=0.0, topK=3, chunkSize=20, chunkOverlap=0))

        fake = FakeLLM([
            {"mode": "multi", "clarification": "", "subqueries": [
                "årsredovisning bokslut delmoment", "besiktning fasad tak delmoment"]},
            {"answer": "Vet ej.", "citations": [], "insufficient_data": True},
        ])
        result = ask_planned(st, "Vem upprättar årsredovisningen?", provider=fake)

        # Non-vacuity: the coded row must be in the pack and the legend must
        # NOT be — otherwise the assertion below proves nothing about linking.
        pack_text = " ".join(h.text for h in result.pack.hits)
        assert "A2.31.01" in pack_text, "kodraden hämtades inte; testet mäter fel sak"
        assert "för Beställaren" not in pack_text, "legenden hämtades av sökningen själv"

        synthesis_user = fake.calls[1]["user"]
        assert "för Beställaren" in synthesis_user, (
            "legenden nådde aldrig prompten — den planerade vägen får en kodrad "
            "den inte kan tolka"
        )

    def test_empty_corpus_refuses_without_planning(self, tmp_path):
        st = Store(data_dir=tmp_path)
        fake = FakeLLM([])
        result = ask_planned(st, "Vad gäller?", provider=fake)
        assert result.response.refusal_reason == "no_documents"
        assert fake.calls == [], "en tom korpus ska inte kosta ett planeringsanrop"
