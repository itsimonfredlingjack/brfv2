from app.document_ask import pack_documents, score_documents
from app.schemas import RetrievalHit
from app.store import Store
from tests.pdf_fixtures import build_pdf
from tests.test_full_corpus import StubRuntime


def _hit(doc, name, score, n=1, page=1):
    return RetrievalHit(
        chunk_id=f"{doc}-{n}",
        score=score,
        confidence=0.5,
        bm25=0.0,
        dense=0.0,
        document_id=doc,
        document_name=name,
        page=page,
        text="t",
        rerank_score=None,
    )


def test_score_documents_ranks_by_max_and_reports_counts():
    hits = [
        _hit("a", "A.pdf", 0.2, n=1),
        _hit("a", "A.pdf", 0.9, n=2),
        _hit("b", "B.pdf", 0.8, n=1),
        _hit("b", "B.pdf", 0.1, n=2),
        _hit("b", "B.pdf", 0.3, n=3),
    ]
    rows = score_documents(hits)
    assert [r.document_id for r in rows] == ["a", "b"]
    assert rows[0].max_score == 0.9 and rows[0].n_matching_chunks == 2
    assert rows[1].max_score == 0.8 and rows[1].n_matching_chunks == 3


def _fat_pdf(token: str, lines: int = 40) -> bytes:
    rows = [
        (f"{token} word extra padding text line {i} continues here", 72, 72 + 14 * i)
        for i in range(lines)
    ]
    return build_pdf([rows])


def _id_named(store: Store, name: str) -> str:
    return next(d.id for d in store.documents.values() if d.name == name)


def _score_named(store: Store, name: str, score: float):
    doc_id = _id_named(store, name)
    chunk = next(c for c in store.chunks.values() if c.document_id == doc_id)
    return RetrievalHit(
        chunk_id=chunk.id,
        score=score,
        confidence=score,
        bm25=score,
        dense=score,
        document_id=doc_id,
        document_name=name,
        page=1,
        text=chunk.text,
        rerank_score=None,
    )


def test_top_too_large_does_not_pack_second(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document("big.pdf", _fat_pdf("alpha"))
    st.add_document("small.pdf", build_pdf([[("beta only", 72, 100)]]))
    scores = score_documents(
        [
            _score_named(st, "big.pdf", 1.0),
            _score_named(st, "small.pdf", 0.5),
        ]
    )
    decision = pack_documents(
        scores=scores,
        chunks=st.chunks,
        documents=st.documents,
        runtime=StubRuntime(n=40),
        system="sys",
        n_ctx=567,
        response_budget=5,
        threshold=32000,
    )
    assert decision.use_documents is False
    assert decision.bound == "top_document_n_ctx"
    assert decision.document_ids == []


def test_packer_skips_later_too_large_keeps_top(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document("top.pdf", build_pdf([[("gamma only", 72, 100)]]))
    st.add_document("huge.pdf", _fat_pdf("delta"))
    st.add_document("third.pdf", build_pdf([[("epsilon only", 72, 100)]]))
    scores = score_documents(
        [
            _score_named(st, "top.pdf", 1.0),
            _score_named(st, "huge.pdf", 0.9),
            _score_named(st, "third.pdf", 0.8),
        ]
    )
    decision = pack_documents(
        scores=scores,
        chunks=st.chunks,
        documents=st.documents,
        runtime=StubRuntime(n=40),
        system="sys",
        n_ctx=600,
        response_budget=5,
        threshold=32000,
    )
    assert decision.use_documents is True
    assert decision.bound == "fits"
    names = [st.documents[i].name for i in decision.document_ids]
    assert names[0] == "top.pdf"
    assert "huge.pdf" not in names
    assert "third.pdf" in names


def test_packer_threshold_zero_is_off(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document("a.pdf", build_pdf([[("hello there", 72, 100)]]))
    scores = score_documents([_score_named(st, "a.pdf", 1.0)])
    decision = pack_documents(
        scores=scores,
        chunks=st.chunks,
        documents=st.documents,
        runtime=StubRuntime(),
        system="sys",
        n_ctx=16384,
        response_budget=5,
        threshold=0,
    )
    assert decision.use_documents is False
    assert decision.bound == "threshold"

