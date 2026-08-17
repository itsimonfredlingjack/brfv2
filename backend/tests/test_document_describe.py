from app.document_describe import (
    apply_description_lock,
    content_fingerprint,
    description_set_version,
    freeze_descriptions,
    parse_description,
    refresh_document_description,
    snapshot_description_lock,
)
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
    saved = st.documents[meta.id]
    assert saved.description == "Andra efter OCR."
    assert saved.description_previous == "Forsta."
    assert len(provider.calls) == 2
    reloaded = Store(data_dir=tmp_path)
    assert reloaded.documents[meta.id].description_previous == "Forsta."
    assert reloaded.documents[meta.id].description == "Andra efter OCR."


def test_rewrite_is_logged_when_extracted_text_changes(tmp_path, monkeypatch, caplog):
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
    with caplog.at_level("INFO", logger="brf.document_describe"):
        refresh_document_description(st, meta.id, provider)
    assert "beskrivning omskriven" in caplog.text
    assert meta.id in caplog.text


def test_frozen_descriptions_are_not_rewritten_on_fingerprint_mismatch(tmp_path, monkeypatch):
    provider = _NamedFake(
        [
            {"description": "Forsta."},
            {"description": "Andra, ska inte sparas."},
        ]
    )
    monkeypatch.setattr("app.document_describe.pick_provider", lambda: provider)
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    st.documents[meta.id] = st.documents[meta.id].model_copy(
        update={"description_fp": "eval-fake"}
    )
    version = freeze_descriptions(st)
    assert version == description_set_version(st.documents)
    page = st.pages[meta.id][0]
    extra = Word(text="OCR", x0=0, y0=0, x1=1, y1=1, block=0, line=0)
    st.pages[meta.id] = [page.model_copy(update={"words": [*page.words, extra]})]
    refresh_document_description(st, meta.id, provider)
    assert st.documents[meta.id].description == "Forsta."
    assert st.documents[meta.id].description_previous is None
    assert len(provider.calls) == 1


def test_description_lock_roundtrip_pins_same_version(tmp_path, monkeypatch):
    provider = _NamedFake([{"description": "Reglerar hyran."}])
    monkeypatch.setattr("app.document_describe.pick_provider", lambda: provider)
    st = Store(data_dir=tmp_path)
    meta = st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    lock = snapshot_description_lock(st)
    assert lock["version"] == description_set_version(st.documents)
    assert lock["documents"][0]["description"] == "Reglerar hyran."

    st.documents[meta.id] = st.documents[meta.id].model_copy(
        update={"description": "Annan, ska skrivas over.", "description_fp": "eval-fake"}
    )
    applied = apply_description_lock(st, lock)
    assert applied == lock["version"]
    assert st.documents[meta.id].description == "Reglerar hyran."
    refresh_document_description(st, meta.id, provider)
    assert st.documents[meta.id].description == "Reglerar hyran."
    assert len(provider.calls) == 1
