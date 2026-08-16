"""U-shape document order for full-corpus excerpts."""

from app.full_corpus import (
    ARCHIVE_PROBE,
    document_ids_for_probe,
    edge_order,
    hits_for_full_corpus,
    ranked_document_ids,
)
from tests.pdf_fixtures import build_pdf
from tests.test_full_corpus import _two_chunk_store


def test_edge_order_puts_best_first_and_last():
    assert edge_order(["A", "B", "C", "D"]) == ["A", "C", "D", "B"]
    assert edge_order(["A", "B", "C"]) == ["A", "C", "B"]
    assert edge_order(["A", "B"]) == ["A", "B"]
    assert edge_order(["A"]) == ["A"]
    assert edge_order([]) == []


def test_hits_respect_document_id_order_then_page(tmp_path):
    st = _two_chunk_store(tmp_path)
    b_id = next(d.id for d in st.documents.values() if d.name == "B.pdf")
    a_id = next(d.id for d in st.documents.values() if d.name == "A.pdf")
    page_hits = hits_for_full_corpus(st.chunks, st.documents)
    assert [h.document_name for h in page_hits] == ["A.pdf", "B.pdf"]
    reordered = hits_for_full_corpus(st.chunks, st.documents, document_ids=[b_id, a_id])
    assert [h.document_name for h in reordered] == ["B.pdf", "A.pdf"]
    assert [h.page for h in reordered] == [1, 1]


def test_ranked_ids_edge_order_high_scores_at_ends():
    docs = {
        "a": type("D", (), {"id": "a", "name": "A.pdf"})(),
        "b": type("D", (), {"id": "b", "name": "B.pdf"})(),
        "c": type("D", (), {"id": "c", "name": "C.pdf"})(),
        "d": type("D", (), {"id": "d", "name": "D.pdf"})(),
    }
    scores = [
        type("S", (), {"document_id": "a", "max_score": 0.9})(),
        type("S", (), {"document_id": "b", "max_score": 0.8})(),
        type("S", (), {"document_id": "c", "max_score": 0.2})(),
        type("S", (), {"document_id": "d", "max_score": 0.1})(),
    ]
    assert ranked_document_ids(scores, docs) == ["a", "c", "d", "b"]


def test_probe_order_stable_across_questions(tmp_path):
    st = _two_chunk_store(tmp_path)
    st.add_document("C.pdf", build_pdf([[("Tredje dokumentets enda mening.", 72, 100)]]))
    order1 = probe_document_ids(st)
    order2 = probe_document_ids(st)
    assert order1 == order2
    assert len(order1) == len(st.documents)
    assert ARCHIVE_PROBE


def test_probe_order_keeps_prefix_stable(tmp_path):
    from app.answer import ask
    from app.llm import FakeLLM
    from tests.test_full_corpus import StubRuntime

    st = _two_chunk_store(tmp_path)
    st.add_document("C.pdf", build_pdf([[("Tredje dokumentets enda mening.", 72, 100)]]))
    st._full_corpus_order = "probe"
    fake = FakeLLM([
        {"answer": "a", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
        {"answer": "b", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
    ])
    rt = StubRuntime()
    ask(st, "Fraga ett?", provider=fake, corpus_runtime=rt)
    ask(st, "Helt annan fraga?", provider=fake, corpus_runtime=rt)
    prefix0 = fake.calls[0]["user"].split("\n\nFRÅGA:")[0]
    prefix1 = fake.calls[1]["user"].split("\n\nFRÅGA:")[0]
    assert prefix0 == prefix1


def probe_document_ids(store) -> list[str]:
    index, _chunks, _pages, documents = store.snapshot()
    return document_ids_for_probe(index, store.settings, documents, store.chunks)
