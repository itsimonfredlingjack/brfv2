"""Helpful insufficient_data refusal: what was read, that the answer
is not in it, and what kind of document typically regulates the question.
"""

from app.llm import FakeLLM
from app.refusal_help import (
    compose_refusal_answer,
    extract_kind_clause,
    kind_prompt,
    match_prompt,
    names_gold_kind,
    parse_kind,
    parse_matches,
    read_document_names,
)
from app.schemas import RetrievalHit, Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf


def test_compose_names_what_was_read_and_that_the_answer_is_not_there():
    text = compose_refusal_answer(
        read_names=["Teknisk förvaltning.pdf"],
        kind=None,
        matching_names=[],
    )
    assert "Teknisk förvaltning.pdf" in text
    assert "står inte" in text


def test_compose_marks_typical_kind_as_general_and_says_when_none_in_archive():
    text = compose_refusal_answer(
        read_names=["Teknisk förvaltning.pdf"],
        kind="ett avtal om sophantering",
        matching_names=[],
    )
    assert text.startswith("Jag läste")
    assert "Allmänt" in text
    assert "ett avtal om sophantering" in text
    assert "Ingen handling av den sorten" in text
    assert "föreningen ska" not in text.lower()
    assert "måste ha" not in text.lower()
    assert "bör ha" not in text.lower()


def test_compose_names_matching_archive_documents_without_claiming_they_answer():
    text = compose_refusal_answer(
        read_names=["Teknisk förvaltning.pdf"],
        kind="ett avtal om sophantering",
        matching_names=["Avtal om Sophantering och gårdsskötsel.pdf"],
    )
    assert "Avtal om Sophantering och gårdsskötsel.pdf" in text
    assert "beskrivs som den sorten" in text
    assert "står inte i dem" in text


def test_compose_omits_kind_when_unknown():
    text = compose_refusal_answer(
        read_names=["A.pdf", "B.pdf"],
        kind="",
        matching_names=[],
    )
    assert "A.pdf" in text and "B.pdf" in text
    assert "Allmänt" not in text


def test_kind_prompt_sees_only_the_question():
    system, user = kind_prompt("Vad kostar sophämtningen efter 31 mars 2024?")
    assert "FRÅGA:" in user
    assert "sophämtningen" in user
    assert "HANDLINGAR" not in user
    assert "beskrivning" not in user.lower()
    assert "föreningen ska ha" not in system.lower()
    assert system.startswith("Du säger vilken sorts handling")


def test_match_prompt_asks_which_descriptions_are_that_kind():
    system, user = match_prompt(
        "ett avtal om sophantering",
        [("A", "Teknisk förvaltning.pdf", "Reglerar felanmälan och jour."),
         ("E", "Avtal om Sophantering.pdf", "Reglerar sophantering och gårdsskötsel.")],
    )
    assert system.startswith("Du matchar en handlingssort")
    assert "ett avtal om sophantering" in user
    assert "Reglerar sophantering och gårdsskötsel." in user
    assert "föreningen ska ha" not in system.lower()


def test_parse_kind_and_matches():
    assert parse_kind('{"kind": "en årsredovisning"}') == "en årsredovisning"
    assert parse_kind("inte json") == ""
    assert parse_matches('{"matches": ["E", "A", "E"]}', {"A", "E"}) == ["E", "A"]
    assert parse_matches("nej", {"A"}) == []


def test_read_document_names_keeps_first_seen_order():
    hits = [
        RetrievalHit(
            chunk_id="c1", score=1, confidence=1, bm25=1, dense=1,
            document_id="b", document_name="B.pdf", page=1, text="x",
        ),
        RetrievalHit(
            chunk_id="c2", score=1, confidence=1, bm25=1, dense=1,
            document_id="a", document_name="A.pdf", page=1, text="y",
        ),
        RetrievalHit(
            chunk_id="c3", score=1, confidence=1, bm25=1, dense=1,
            document_id="b", document_name="B.pdf", page=2, text="z",
        ),
    ]
    assert read_document_names(hits) == ["B.pdf", "A.pdf"]


def test_names_gold_kind_is_about_the_sort_not_a_filename_copy():
    gold = "Avtal om Sophantering och gårdsskötsel.pdf"
    assert names_gold_kind(
        "Allmänt brukar en sådan fråga regleras i ett avtal om sophantering.",
        gold,
    )
    assert not names_gold_kind(
        "Allmänt brukar en sådan fråga regleras i en årsredovisning.",
        gold,
    )


def test_extract_kind_clause_reads_the_general_sentence():
    text = compose_refusal_answer(
        read_names=["B.pdf"],
        kind="ett avtal om sophantering",
        matching_names=[],
    )
    assert extract_kind_clause(text) == "ett avtal om sophantering"


def test_insufficient_data_refusal_names_the_read_documents(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document(
        "Snöröjningsavtal.pdf",
        build_pdf([[("Jourperioden för snöröjning löper från 15 november till 15 april.", 72, 100)]]),
    )
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    fake = FakeLLM([{"answer": "Uppgift saknas.", "citations": [], "insufficient_data": True}])
    from app.answer import ask

    resp = ask(st, "Vad kostar garaget?", provider=fake)
    assert resp.refusal and resp.refusal_reason == "insufficient_data"
    assert "Snöröjningsavtal.pdf" in resp.answer
    assert "står inte" in resp.answer
    assert resp.answer != "Uppgift saknas."


def test_insufficient_data_includes_general_kind_when_model_returns_one(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document(
        "Snöröjningsavtal.pdf",
        build_pdf([[("Jourperioden för snöröjning löper från 15 november till 15 april.", 72, 100)]]),
    )
    st.documents[next(iter(st.documents))] = st.documents[next(iter(st.documents))].model_copy(
        update={"description": "Reglerar snöröjning och halkbekämpning."}
    )
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    fake = FakeLLM(
        [
            {"answer": "Uppgift saknas.", "citations": [], "insufficient_data": True},
            {"kind": "ett snöröjningsavtal"},
            {"matches": ["A"]},
        ]
    )
    from app.answer import ask

    resp = ask(st, "Vad kostar garaget?", provider=fake)
    assert resp.refusal_reason == "insufficient_data"
    assert "Allmänt" in resp.answer
    assert "ett snöröjningsavtal" in resp.answer
    assert "Snöröjningsavtal.pdf" in resp.answer


def test_numeric_grounding_failed_message_is_unchanged(tmp_path):
    st = Store(data_dir=tmp_path)
    lines = [("Total utgift 15 659 566 kr", 72, 100)]
    st.add_document("Budget.pdf", build_pdf([lines]))
    st.update_settings(Settings(minRelevance=0.0, topK=3))
    cid = next(iter(st.chunks))
    bad = {
        "answer": "Den totala utgiften är 1 565 956 kr.",
        "citations": [{"chunk_id": cid, "quote": "Total utgift 15 659 566 kr"}],
        "insufficient_data": False,
    }
    fake = FakeLLM([bad, bad])
    from app.answer import ask

    resp = ask(st, "Vad är den totala utgiften?", provider=fake)
    assert resp.refusal_reason == "numeric_grounding_failed"
    assert "Siffrorna i svaret stämmer inte exakt med källan" in resp.answer
