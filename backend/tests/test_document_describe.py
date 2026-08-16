from app.document_describe import content_fingerprint, parse_description, refresh_document_description
from app.llm import FakeLLM
from app.schemas import Word
from app.store import Store
from tests.pdf_fixtures import build_pdf


class _NamedFake(FakeLLM):
    name = "selfhosted"


def test_parse_description_reads_json_object():
    assert parse_description('{"description": "Reglerar hyran."}') == "Reglerar hyran."


def test_ingest_skips_description_under_fake_llm(tmp_path):
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    assert meta.description is None
    assert meta.description_fp is None


def test_description_generated_at_ingest_with_real_named_provider(tmp_path, monkeypatch):
    provider = _NamedFake([{"description": "Reglerar parkering och uppsägning."}])
    monkeypatch.setattr("app.document_describe.pick_provider", lambda: provider)
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    assert meta.description == "Reglerar parkering och uppsägning."
    assert meta.description_fp == content_fingerprint(st.pages[meta.id])
    assert provider.calls
    assert "vad handlingen styr" in provider.calls[0]["system"]


def test_description_not_regenerated_when_fingerprint_matches(tmp_path, monkeypatch):
    provider = _NamedFake(
        [
            {"description": "Forsta."},
            {"description": "Andra, ska inte sparas."},
        ]
    )
    monkeypatch.setattr("app.document_describe.pick_provider", lambda: provider)
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    assert meta.description == "Forsta."
    refresh_document_description(st, meta.id, provider)
    assert st.documents[meta.id].description == "Forsta."
    assert len(provider.calls) == 1


def test_description_regenerated_when_extracted_text_changes(tmp_path, monkeypatch):
    provider = _NamedFake(
        [
            {"description": "Forsta."},
            {"description": "Andra efter OCR."},
        ]
    )
    monkeypatch.setattr("app.document_describe.pick_provider", lambda: provider)
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    page = st.pages[meta.id][0]
    extra = Word(text="OCR", x0=0, y0=0, x1=1, y1=1, block=0, line=0)
    st.pages[meta.id] = [page.model_copy(update={"words": [*page.words, extra]})]
    refresh_document_description(st, meta.id, provider)
    assert st.documents[meta.id].description == "Andra efter OCR."
    assert len(provider.calls) == 2
