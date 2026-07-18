"""OCR ingestion wired into Store.add_document (store.py:124).

Dispatch/unavailable/verification-chain tests are fully offline: `ocr_pdf`
and `tesseract_available` are monkeypatched, so they run without a tesseract
binary. The real-tesseract integration test at the bottom is marked `ocr` and
skipped where tesseract+swe isn't installed (pattern: tests/test_ocr_spike.py).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from app.answer import ask
from app.llm import FakeLLM
from app.schemas import PageData, Word
from app.store import MAX_DOCUMENT_PAGES, Store
from tests.pdf_fixtures import build_image_only_pdf, build_pdf


def _line_words(texts: list[str], *, y0: float = 100.0, block: int = 1, line: int = 1) -> list[Word]:
    """A single visual line of words, left to right, non-overlapping."""
    words = []
    x = 72.0
    for t in texts:
        w = 8.0 * len(t) + 4.0
        words.append(Word(text=t, x0=x, y0=y0, x1=x + w, y1=y0 + 14.0, block=block, line=line))
        x += w + 6.0
    return words


PAGE1 = PageData(
    number=1,
    width=595.0,
    height=842.0,
    rotation=0,
    words=_line_words(["Årsavgiften", "fastställs", "till", "500", "kr"]),
)
PAGE2_BLANK = PageData(number=2, width=595.0, height=842.0, rotation=0, words=[])
PAGE3 = PageData(
    number=3,
    width=595.0,
    height=842.0,
    rotation=0,
    words=_line_words(["Styrelsen", "sammanträder", "varje", "månad"]),
)


def _textless_pdf() -> bytes:
    return build_pdf([[]])


class TestDispatch:
    def test_ocr_dispatch_ingests_chunks_indexes_and_marks_source_scanned(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", lambda data, **kw: [PAGE1, PAGE2_BLANK, PAGE3])

        store = Store(data_dir=tmp_path)
        meta = store.add_document("Skannad.pdf", _textless_pdf())

        assert meta.source == "scanned"
        assert meta.pages == 3
        assert meta.words == len(PAGE1.words) + len(PAGE3.words)

        doc_chunks = [c for c in store.chunks.values() if c.document_id == meta.id]
        assert doc_chunks  # chunks exist
        assert all(c.page != 2 for c in doc_chunks)  # blank middle page: no chunks, no failure

        hits = store.index.search("Årsavgiften", weight=0.5, candidates=10, top_k=5, min_confidence=0.0)
        assert any(h.document_id == meta.id for h in hits)

        # Persisted extraction is ordinary PageData -- reload proves it round-trips.
        reloaded = Store(data_dir=tmp_path)
        assert reloaded.documents[meta.id].source == "scanned"
        assert [p.words for p in reloaded.pages[meta.id]] == [PAGE1.words, [], PAGE3.words]

    def test_ocr_not_invoked_when_digital_text_layer_present(self, tmp_path, monkeypatch):
        def _boom(data, **kw):
            raise AssertionError("ocr_pdf must not run when the PDF has a text layer")

        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", _boom)

        store = Store(data_dir=tmp_path)
        pdf = build_pdf([[("Vanlig digital text.", 72, 100)]])
        meta = store.add_document("Digital.pdf", pdf)
        assert meta.source == "digital"


class TestPageCountGuardOrdering:
    """store.py: MAX_DOCUMENT_PAGES must be checked BEFORE the OCR dispatch —
    a 401-page scanned PDF is rejected on page count alone, never reaching
    tesseract. `ocr_pdf` is monkeypatched to fail the test outright if
    invoked, so this is a hard guarantee, not just an assertion on the
    resulting error."""

    def test_page_count_over_limit_on_textless_pdf_rejected_without_ocr(self, tmp_path, monkeypatch):
        def _boom(data, **kw):
            raise AssertionError("ocr_pdf must not run when the page count already exceeds the limit")

        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", _boom)

        store = Store(data_dir=tmp_path)
        oversized = build_pdf([[] for _ in range(MAX_DOCUMENT_PAGES + 1)])
        with pytest.raises(ValueError, match=f"max {MAX_DOCUMENT_PAGES}"):
            store.add_document("Stor.pdf", oversized)
        assert store.documents == {}


class TestOcrRuntimeErrors:
    """store.py wraps the ocr_pdf call: a tesseract subprocess failure
    (RuntimeError) or a hung tesseract (subprocess.TimeoutExpired) must
    surface as a Swedish ValueError, not propagate raw -- main.py's existing
    ValueError -> HTTPException(422) mapping only fires on ValueError."""

    def test_tesseract_nonzero_exit_becomes_swedish_valueerror(self, tmp_path, monkeypatch):
        def _boom(data, **kw):
            raise RuntimeError("tesseract fel: boom")

        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", _boom)

        store = Store(data_dir=tmp_path)
        with pytest.raises(ValueError, match="OCR-motorn misslyckades"):
            store.add_document("Skannad.pdf", _textless_pdf())
        assert store.documents == {}

    def test_tesseract_timeout_becomes_swedish_valueerror(self, tmp_path, monkeypatch):
        def _boom(data, **kw):
            raise subprocess.TimeoutExpired(cmd="tesseract", timeout=120)

        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", _boom)

        store = Store(data_dir=tmp_path)
        with pytest.raises(ValueError, match="OCR-motorn tog för lång tid"):
            store.add_document("Skannad.pdf", _textless_pdf())
        assert store.documents == {}


class TestUnavailable:
    def test_tesseract_unavailable_raises_existing_swedish_error(self, tmp_path, monkeypatch):
        def _boom(data, **kw):
            raise AssertionError("ocr_pdf must not run when tesseract is unavailable")

        monkeypatch.setattr("app.store.tesseract_available", lambda: False)
        monkeypatch.setattr("app.store.ocr_pdf", _boom)

        store = Store(data_dir=tmp_path)
        with pytest.raises(ValueError, match="saknar textlager"):
            store.add_document("Skannad.pdf", _textless_pdf())

    def test_no_document_registered_after_unavailable_rejection(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.store.tesseract_available", lambda: False)
        store = Store(data_dir=tmp_path)
        with pytest.raises(ValueError):
            store.add_document("Skannad.pdf", _textless_pdf())
        assert store.documents == {}


class TestOcrYieldsNoText:
    def test_zero_words_after_ocr_raises_swedish_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr(
            "app.store.ocr_pdf",
            lambda data, **kw: [PageData(number=1, width=595.0, height=842.0, rotation=0, words=[])],
        )
        store = Store(data_dir=tmp_path)
        with pytest.raises(ValueError, match="OCR"):
            store.add_document("Tomt.pdf", _textless_pdf())
        assert store.documents == {}


class TestVerificationChainOnOcrData:
    """OCR words flow through the SAME resolve/highlight chain as digital
    words: zero verification changes, invariant intact on OCR-shaped data."""

    @pytest.fixture()
    def ocr_store(self, tmp_path, monkeypatch) -> Store:
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)
        monkeypatch.setattr("app.store.ocr_pdf", lambda data, **kw: [PAGE1])
        store = Store(data_dir=tmp_path)
        store.add_document("Skannad.pdf", _textless_pdf())
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        return store

    def test_verbatim_ocr_quote_verifies_with_rects(self, ocr_store):
        chunk_id = next(iter(ocr_store.chunks))
        fake = FakeLLM(
            [
                {
                    "answer": "Årsavgiften fastställs till 500 kr.",
                    "citations": [{"chunk_id": chunk_id, "quote": "Årsavgiften fastställs till 500 kr"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(ocr_store, "Vad är årsavgiften?", provider=fake)
        assert not resp.refusal
        assert len(resp.citations) == 1
        assert resp.citations[0].rects and all(len(r) == 4 for r in resp.citations[0].rects)

    def test_fabricated_ocr_quote_rejected(self, ocr_store):
        chunk_id = next(iter(ocr_store.chunks))
        fake = FakeLLM(
            [
                {
                    "answer": "Påhittat.",
                    "citations": [{"chunk_id": chunk_id, "quote": "Årsavgiften är gratis för alla medlemmar"}],
                    "insufficient_data": False,
                }
            ]
        )
        resp = ask(ocr_store, "Vad är årsavgiften?", provider=fake)
        assert resp.refusal and resp.refusal_reason == "grounding_failed"
        assert resp.rejected_citations[0].reason == "quote_not_found"


# ---------- real-tesseract integration ----------


def tesseract_with_swe() -> bool:
    if shutil.which("tesseract") is None:
        return False
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "swe" in langs.split()


SYNTHETIC_LINES = [
    ("Årsavgiften för föreningen fastställs av styrelsen varje år.", 72, 100),
    ("Nästa styrelsemöte hålls i februari månad.", 72, 122),
]


@pytest.mark.skipif(not tesseract_with_swe(), reason="tesseract+swe not installed")
@pytest.mark.ocr
def test_scanned_synthetic_pdf_ingests_and_citation_resolves(tmp_path):
    pdf = build_image_only_pdf([SYNTHETIC_LINES])
    store = Store(data_dir=tmp_path)
    meta = store.add_document("Skannat.pdf", pdf)

    assert meta.source == "scanned"
    assert meta.chunks > 0
    doc_chunks = [c for c in store.chunks.values() if c.document_id == meta.id]
    assert doc_chunks

    store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
    chunk_id = doc_chunks[0].id
    fake = FakeLLM(
        [
            {
                "answer": "Årsavgiften fastställs av styrelsen varje år.",
                "citations": [
                    {
                        "chunk_id": chunk_id,
                        "quote": "Årsavgiften för föreningen fastställs av styrelsen varje år",
                    }
                ],
                "insufficient_data": False,
            }
        ]
    )
    resp = ask(store, "Vem fastställer årsavgiften?", provider=fake)
    assert not resp.refusal, f"unexpected refusal: {resp.refusal_reason}, rejected={resp.rejected_citations}"
    assert resp.citations and resp.citations[0].rects
