import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from tests.pdf_fixtures import build_pdf


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(Store(data_dir=tmp_path)))


@pytest.fixture()
def uploaded(client):
    pdf = build_pdf(
        [
            [
                ("Årsavgiften fastställs av styrelsen och fördelas efter andelstal.", 72, 100),
                ("Överlåtelseavgift får tas ut med högst 2,5 procent av prisbasbeloppet.", 72, 114),
                ("Pantsättningsavgift får tas ut med högst en procent av prisbasbeloppet.", 72, 128),
                ("Avgifterna betalas av köparen respektive pantsättaren till föreningen.", 72, 142),
            ]
        ]
    )
    r = client.post("/api/documents", files={"file": ("Stadgar.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["embedding_provider"] == "hashed-char-ngram"


class TestDocuments:
    def test_upload_and_list(self, client, uploaded):
        assert uploaded["pages"] == 1
        assert uploaded["words"] > 10
        assert uploaded["chunks"] >= 1
        docs = client.get("/api/documents").json()
        assert [d["id"] for d in docs] == [uploaded["id"]]

    def test_pdf_roundtrip(self, client, uploaded):
        r = client.get(f"/api/documents/{uploaded['id']}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")

    def test_extraction_summary(self, client, uploaded):
        r = client.get(f"/api/documents/{uploaded['id']}/extraction")
        assert r.status_code == 200
        body = r.json()
        assert body["pages"][0]["words"] > 0
        assert body["chunks"][0]["preview"]

    def test_non_pdf_rejected(self, client):
        r = client.post("/api/documents", files={"file": ("evil.txt", b"hej", "text/plain")})
        assert r.status_code == 400

    def test_scanned_pdf_rejected_with_explanation(self, client):
        r = client.post("/api/documents", files={"file": ("scan.pdf", build_pdf([[]]), "application/pdf")})
        assert r.status_code == 422
        assert "textlager" in r.json()["detail"]

    def test_delete(self, client, uploaded):
        assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 200
        assert client.get("/api/documents").json() == []
        assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 404

    def test_unknown_doc_404(self, client):
        assert client.get("/api/documents/nope/pdf").status_code == 404
        assert client.get("/api/documents/nope/extraction").status_code == 404


class TestSettings:
    def test_roundtrip(self, client):
        s = client.get("/api/settings").json()
        s["topK"] = 3
        s["searchWeighting"] = 80
        r = client.put("/api/settings", json=s)
        assert r.status_code == 200
        assert client.get("/api/settings").json()["topK"] == 3

    def test_invalid_settings_rejected(self, client):
        s = client.get("/api/settings").json()
        s["chunkStrategy"] = "magic"
        assert client.put("/api/settings", json=s).status_code == 422

    def test_chunk_knob_change_rechunks_documents(self, client, uploaded):
        before = client.get(f"/api/documents/{uploaded['id']}/extraction").json()["chunks"]
        s = client.get("/api/settings").json()
        s["chunkStrategy"] = "fixed"
        s["chunkSize"] = 20
        s["chunkOverlap"] = 0
        assert client.put("/api/settings", json=s).status_code == 200
        after = client.get(f"/api/documents/{uploaded['id']}/extraction").json()["chunks"]
        assert len(after) > len(before)


class TestAsk:
    def test_empty_question_400(self, client):
        assert client.post("/api/ask", json={"question": "   "}).status_code == 400

    def test_no_documents_refusal(self, client):
        r = client.post("/api/ask", json={"question": "Vad gäller?"})
        assert r.status_code == 200
        body = r.json()
        assert body["refusal"] and body["refusal_reason"] == "no_documents"

    def test_ask_uses_fake_provider_from_env(self, client, uploaded):
        # BRF_LLM=fake (conftest) → provider has no scripted responses → the
        # orchestrator degrades to a refusal rather than crashing.
        r = client.post("/api/ask", json={"question": "Vem fastställer årsavgiften?"})
        assert r.status_code == 200
        assert r.json()["refusal"] is True


class TestPersistence:
    def test_store_reloads_from_disk(self, tmp_path):
        st1 = Store(data_dir=tmp_path)
        pdf = build_pdf([[("Underhållsplanen omfattar takrenovering.", 72, 100)]])
        meta = st1.add_document("Plan.pdf", pdf)
        st2 = Store(data_dir=tmp_path)
        assert meta.id in st2.documents
        assert len(st2.chunks) >= 1
        assert len(st2.index) == len(st2.chunks)
