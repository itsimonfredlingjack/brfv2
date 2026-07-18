"""Tenant-scoped API happy paths (auth enforced). Isolation attacks live in
test_isolation.py; lifecycle in test_lifecycle.py."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthStore
from app.main import create_app
from app.registry import TenantRegistry
from tests.pdf_fixtures import build_pdf


@pytest.fixture()
def env(two_tenant_app):
    return two_tenant_app


class TestHealth:
    def test_health(self, env):
        body = env.client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["embedding_provider"] == "hashed-char-ngram"
        assert body["tenants"] == 2


class TestAuthFlow:
    def test_login_sets_cookie_and_returns_memberships(self, env):
        r = env.client.post("/api/auth/login", json={"email": "admin-a@a.se", "password": "lösenord-a-admin"})
        assert r.status_code == 200
        assert "brf_session" in r.cookies
        assert r.json()["memberships"][0]["brf_id"] == "brf-a"

    def test_bad_password_401(self, env):
        r = env.client.post("/api/auth/login", json={"email": "admin-a@a.se", "password": "fel"})
        assert r.status_code == 401

    def test_me_requires_auth(self, env):
        assert env.client.get("/api/auth/me").status_code == 401
        r = env.client.get("/api/auth/me", headers=env.admin_a_headers)
        assert r.status_code == 200 and r.json()["user"]["email"] == "admin-a@a.se"

    def test_logout_invalidates_session(self, env):
        tok = env.token("admin-a@a.se", "lösenord-a-admin")
        h = {"Authorization": f"Bearer {tok}"}
        assert env.client.get("/api/auth/me", headers=h).status_code == 200
        env.client.post("/api/auth/logout", headers=h)
        assert env.client.get("/api/auth/me", headers=h).status_code == 401


class TestDocuments:
    def test_list_and_pdf_roundtrip(self, env):
        docs = env.client.get("/api/brf/brf-a/documents", headers=env.admin_a_headers).json()
        assert [d["id"] for d in docs] == [env.doc_a_id]
        r = env.client.get(f"/api/brf/brf-a/documents/{env.doc_a_id}/pdf", headers=env.admin_a_headers)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")

    def test_member_can_read_but_not_upload(self, env):
        assert env.client.get("/api/brf/brf-a/documents", headers=env.member_a_headers).status_code == 200
        pdf = build_pdf([[("Nytt dokument från medlem.", 72, 100)]])
        r = env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("X.pdf", pdf, "application/pdf")}, headers=env.member_a_headers
        )
        assert r.status_code == 403

    def test_admin_delete(self, env):
        pdf = build_pdf([[("Tillfälligt dokument.", 72, 100)]])
        rid = env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("T.pdf", pdf, "application/pdf")}, headers=env.admin_a_headers
        ).json()["id"]
        assert env.client.delete(f"/api/brf/brf-a/documents/{rid}", headers=env.admin_a_headers).status_code == 200

    def test_non_pdf_and_scanned_rejected(self, env):
        assert env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("e.txt", b"hej", "text/plain")}, headers=env.admin_a_headers
        ).status_code == 400
        assert env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("s.pdf", build_pdf([[]]), "application/pdf")},
            headers=env.admin_a_headers,
        ).status_code == 422

    def test_ocr_subprocess_nonzero_exit_returns_422_swedish_unchanged_store(self, env, monkeypatch):
        """End to end: a real tesseract exit-code failure inside app.ocr's
        subprocess.run must surface as a Swedish 422, not a raw 500 -- and
        must not register a half-ingested document."""
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)

        class _FakeProc:
            returncode = 1
            stderr = "tesseract: error boom"

        monkeypatch.setattr("app.ocr.subprocess.run", lambda *a, **kw: _FakeProc())

        before = env.client.get("/api/brf/brf-a/documents", headers=env.admin_a_headers).json()
        r = env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("scan1.pdf", build_pdf([[]]), "application/pdf")},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert "OCR-motorn misslyckades" in r.json()["detail"]
        after = env.client.get("/api/brf/brf-a/documents", headers=env.admin_a_headers).json()
        assert after == before

    def test_ocr_subprocess_timeout_returns_422_swedish_unchanged_store(self, env, monkeypatch):
        monkeypatch.setattr("app.store.tesseract_available", lambda: True)

        def _timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="tesseract", timeout=120)

        monkeypatch.setattr("app.ocr.subprocess.run", _timeout)

        before = env.client.get("/api/brf/brf-a/documents", headers=env.admin_a_headers).json()
        r = env.client.post(
            "/api/brf/brf-a/documents", files={"file": ("scan2.pdf", build_pdf([[]]), "application/pdf")},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 422
        assert "OCR-motorn tog för lång tid" in r.json()["detail"]
        after = env.client.get("/api/brf/brf-a/documents", headers=env.admin_a_headers).json()
        assert after == before


class TestSettings:
    def test_admin_roundtrip_member_readonly(self, env):
        s = env.client.get("/api/brf/brf-a/settings", headers=env.member_a_headers).json()
        s["topK"] = 3
        assert env.client.put("/api/brf/brf-a/settings", json=s, headers=env.member_a_headers).status_code == 403
        assert env.client.put("/api/brf/brf-a/settings", json=s, headers=env.admin_a_headers).status_code == 200
        assert env.client.get("/api/brf/brf-a/settings", headers=env.admin_a_headers).json()["topK"] == 3

    def test_invalid_settings_rejected(self, env):
        s = env.client.get("/api/brf/brf-a/settings", headers=env.admin_a_headers).json()
        s["chunkStrategy"] = "magic"
        assert env.client.put("/api/brf/brf-a/settings", json=s, headers=env.admin_a_headers).status_code == 422


class TestAsk:
    def test_empty_question_400(self, env):
        assert env.client.post("/api/brf/brf-a/ask", json={"question": " "}, headers=env.admin_a_headers).status_code == 400

    def test_ask_refuses_without_scripted_llm(self, env):
        # BRF_LLM=fake with no scripted responses → orchestrator degrades to a
        # refusal rather than crashing.
        r = env.client.post("/api/brf/brf-a/ask", json={"question": "Vad står i stadgarna?"}, headers=env.admin_a_headers)
        assert r.status_code == 200 and r.json()["refusal"] is True


class TestDevReset:
    def test_reset_forbidden_outside_dev(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRF_MODE", "staging")
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        client = TestClient(create_app(registry=registry, auth=auth, data_root=tmp_path))
        # Unauthenticated → 401 before the dev-mode check even matters.
        assert client.post("/api/reset").status_code == 401

    def test_reset_requires_authentication_in_dev(self, env):
        # Red-team finding: reset must never be anonymous, even in dev.
        assert env.client.post("/api/reset").status_code == 401
