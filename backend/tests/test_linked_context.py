from app.linked_context import (
    append_linked_table_legends,
    coded_row_uses,
    responsibility_legend_codes,
)
from app.schemas import Chunk, DocumentMeta, RetrievalHit


LEGEND = (
    'Kolumnen "utföres av" har markerats med ett "A" för Leverantören '
    'och med ett "B" för Beställaren.'
)
ROW = "A2.31.01 Upprättande av årsredovisning A JA"


def _chunk(chunk_id: str, document_id: str, page: int, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        page=page,
        word_start=0,
        word_end=max(0, len(text.split()) - 1),
        text=text,
    )


def _hit(chunk: Chunk) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk.id,
        score=1.0,
        confidence=0.8,
        bm25=4.0,
        dense=0.6,
        document_id=chunk.document_id,
        document_name="Avtal.pdf",
        page=chunk.page,
        text=chunk.text,
    )


def _doc(doc_id: str, name: str = "Avtal.pdf") -> DocumentMeta:
    return DocumentMeta(
        id=doc_id,
        name=name,
        pages=2,
        words=100,
        chunks=2,
        uploaded_at="2026-07-23T00:00:00+00:00",
        source="digital",
        corpus_origin="synthetic",
    )


def test_detects_generic_responsibility_legend_and_coded_leaf_row():
    codes = responsibility_legend_codes(LEGEND)
    assert codes == frozenset({"A", "B"})
    assert coded_row_uses(ROW, codes)


def test_does_not_treat_arbitrary_quoted_letters_or_uncoded_text_as_linkable():
    assert responsibility_legend_codes('Bilaga "A" och bilaga "B" finns.') == frozenset()
    assert not coded_row_uses("Upprättande av årsredovisning A", frozenset({"A", "B"}))


def test_appends_same_document_legend_without_changing_original_hit_scores():
    row = _chunk("doc:p2:0-6", "doc", 2, ROW)
    legend = _chunk("doc:p1:0-15", "doc", 1, LEGEND)
    original = _hit(row)

    result = append_linked_table_legends(
        [original],
        {row.id: row, legend.id: legend},
        {"doc": _doc("doc")},
    )

    assert [hit.chunk_id for hit in result] == [row.id, legend.id]
    assert result[0] == original
    assert result[1].score == result[1].confidence == 0.0
    assert result[1].document_name == "Avtal.pdf"


def test_never_links_a_legend_from_another_document():
    row = _chunk("row:p2:0-6", "row-doc", 2, ROW)
    foreign_legend = _chunk("legend:p1:0-15", "legend-doc", 1, LEGEND)

    result = append_linked_table_legends(
        [_hit(row)],
        {row.id: row, foreign_legend.id: foreign_legend},
        {"row-doc": _doc("row-doc"), "legend-doc": _doc("legend-doc")},
    )

    assert [hit.chunk_id for hit in result] == [row.id]


def test_does_not_duplicate_a_legend_already_retrieved():
    row = _chunk("doc:p2:0-6", "doc", 2, ROW)
    legend = _chunk("doc:p1:0-15", "doc", 1, LEGEND)

    result = append_linked_table_legends(
        [_hit(row), _hit(legend)],
        {row.id: row, legend.id: legend},
        {"doc": _doc("doc")},
    )

    assert [hit.chunk_id for hit in result] == [row.id, legend.id]
