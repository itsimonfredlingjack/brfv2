"""The citation invariant under enrichment: enrichment can drive retrieval, but
enrichment text is never citable and the model never sees it. Synthetic only."""

from __future__ import annotations

from app.answer import ask
from app.citations import Rejected, resolve_citation
from app.llm import FakeLLM
from app.store import Store
from scripts.reality import common
from tests.pdf_fixtures import build_pdf


def _pdf() -> bytes:
    # Heading first + tall (detected + carried to the chunk); year line last, so
    # the enrichment prefix "2025 Resultaträkning" is NOT contiguous in the doc.
    return build_pdf([[
        ("Resultaträkning", 72, 100, 18),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Årsredovisning 2025 räkenskapsåret 2025", 72, 180),
    ]])


def _row_chunk(store, doc_id):
    return next(c for c in store.chunks.values()
               if c.document_id == doc_id and "Räntekostnader" in c.text)


class TestEnrichmentNotCitable:
    def test_enrichment_prefix_fails_verification(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _pdf())
        chunk = _row_chunk(store, meta.id)

        # The enrichment prefix (everything before the frozen text) is a real
        # search string but is NOT contiguous document text.
        prefix = chunk.search_text[: chunk.search_text.rfind(chunk.text)].strip()
        assert prefix and prefix not in chunk.text  # e.g. "2025 Resultaträkning"

        res = resolve_citation(chunk, [prefix], store.pages)
        assert isinstance(res, Rejected)  # enrichment text cannot be cited

        # And the frozen row text CAN be cited (control) — proving the reject is
        # about provenance, not a broken verifier.
        ok = resolve_citation(chunk, ["Räntekostnader 1 234 567"], store.pages)
        assert not isinstance(ok, Rejected)

    def test_model_never_sees_enrichment_via_ask(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        meta = store.add_document("ar.pdf", _pdf())
        chunk = _row_chunk(store, meta.id)
        question = "Hur stora var föreningens räntekostnader under året?"
        alias, _hits = common.alias_for_chunk(store, question, chunk.id)
        assert alias is not None

        # Model tries to cite the enrichment prefix -> rejected, answer refused/stripped.
        prefix = chunk.search_text[: chunk.search_text.rfind(chunk.text)].strip()
        fake = FakeLLM([{"answer": "x", "citations": [{"chunk_id": alias, "quote": prefix}],
                         "insufficient_data": False}])
        resp = ask(store, question, provider=fake)
        assert len(resp.citations) == 0
        assert any(r.reason in ("quote_not_found", "provenance_mismatch") for r in resp.rejected_citations)
