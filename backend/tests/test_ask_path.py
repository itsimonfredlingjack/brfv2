"""Ask-path routing lives in choose_ask_path — not in ask(), ask_planned(), or packers."""

from __future__ import annotations

import inspect

from app.answer import ask, choose_ask_path
from app.document_ask import evaluate_document_path
from app.llm import FakeLLM
from app.multihop import ask_planned
from tests.test_document_ask import _ANSWER, _set_descriptions
from tests.test_full_corpus import StubRuntime, _two_chunk_store


def test_ask_and_planned_route_only_through_choose_ask_path():
    ask_src = inspect.getsource(ask)
    planned_src = inspect.getsource(ask_planned)
    chooser_src = inspect.getsource(choose_ask_path)
    assert "choose_ask_path(" in ask_src
    assert "choose_ask_path(" in planned_src
    assert "evaluate_full_corpus(" in chooser_src
    assert "evaluate_document_path(" in chooser_src
    assert "evaluate_full_corpus(" not in ask_src
    assert "evaluate_document_path(" not in ask_src
    assert "evaluate_full_corpus(" not in planned_src
    assert "evaluate_document_path(" not in planned_src


def test_default_is_documents_when_descriptions_pack(tmp_path):
    st = _two_chunk_store(tmp_path)
    _set_descriptions(st)
    fake = FakeLLM([{"documents": ["A", "B"]}])
    index, chunks, _pages, documents = st.snapshot()
    chosen = choose_ask_path(
        store=st,
        question="Vad star det?",
        index=index,
        chunks=chunks,
        documents=documents,
        runtime=StubRuntime(),
        settings=st.settings,
        provider=fake,
    )
    assert chosen.name == "documents"
    assert chosen.bound == "fits"
    assert len(chosen.pack.document_ids) == 2


def test_threshold_zero_forces_retrieval_even_with_descriptions(tmp_path):
    st = _two_chunk_store(tmp_path)
    _set_descriptions(st)
    st.update_settings(st.settings.model_copy(update={"fullCorpusTokenThreshold": 0}))
    fake = FakeLLM([{"documents": ["A"]}])
    index, chunks, _pages, documents = st.snapshot()
    chosen = choose_ask_path(
        store=st,
        question="Vad star det?",
        index=index,
        chunks=chunks,
        documents=documents,
        runtime=StubRuntime(),
        settings=st.settings,
        provider=fake,
    )
    assert chosen.name == "retrieval"
    assert chosen.bound == "threshold"
    assert fake.calls == []


def test_no_descriptions_falls_back_to_retrieval_not_full_corpus(tmp_path):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([{"documents": ["A"]}])
    index, chunks, _pages, documents = st.snapshot()
    chosen = choose_ask_path(
        store=st,
        question="Vad star det?",
        index=index,
        chunks=chunks,
        documents=documents,
        runtime=StubRuntime(),
        settings=st.settings,
        provider=fake,
    )
    assert chosen.name == "retrieval"
    assert chosen.bound == "no_descriptions"
    assert fake.calls == []


def test_full_corpus_only_when_preferred(tmp_path):
    st = _two_chunk_store(tmp_path)
    st._prefer_full_corpus = True
    fake = FakeLLM([])
    index, chunks, _pages, documents = st.snapshot()
    chosen = choose_ask_path(
        store=st,
        question="Vad star det?",
        index=index,
        chunks=chunks,
        documents=documents,
        runtime=StubRuntime(),
        settings=st.settings,
        provider=fake,
    )
    assert chosen.name == "full_corpus"
    assert chosen.full_hits is not None
    assert len(chosen.full_hits) == len(st.chunks)
    assert fake.calls == []


def test_evaluate_document_path_does_not_use_fused_scores(tmp_path, monkeypatch):
    st = _two_chunk_store(tmp_path)
    _set_descriptions(st)

    def boom(*_a, **_k):
        raise AssertionError("fused score_documents must not run")

    monkeypatch.setattr("app.document_ask.score_documents", boom)
    monkeypatch.setattr(st.index, "search", boom)
    fake = FakeLLM([{"documents": ["A"]}])
    decision = evaluate_document_path(
        question="Vad star det?",
        index=st.index,
        chunks=st.chunks,
        documents=st.documents,
        runtime=StubRuntime(),
        settings=st.settings,
        provider=fake,
        store=st,
    )
    assert decision.use_documents is True
    names = [st.documents[i].name for i in decision.document_ids]
    assert names == ["A.pdf"]


def test_ask_uses_description_selection_not_search(tmp_path, monkeypatch):
    st = _two_chunk_store(tmp_path)
    _set_descriptions(st)
    st.update_settings(st.settings.model_copy(update={"minRelevance": 0.0}))

    def boom(*_a, **_k):
        raise AssertionError("index.search must not rank the document path")

    monkeypatch.setattr(st.index, "search", boom)
    fake = FakeLLM(
        [
            {"documents": ["A", "B"]},
            _ANSWER,
        ]
    )
    resp = ask(st, "Forsta dokumentets enda mening?", provider=fake, corpus_runtime=StubRuntime())
    assert not resp.refusal
    assert fake.calls[0]["user"].startswith("HANDLINGAR:")
    assert fake.calls[1]["user"].startswith("UTDRAG:")
