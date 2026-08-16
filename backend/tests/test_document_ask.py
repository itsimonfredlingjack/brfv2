from app.document_ask import score_documents
from app.schemas import RetrievalHit


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
