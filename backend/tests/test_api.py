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

    def test_health_preserves_pre_existing_top_level_fields(self, env):
        # The `llm` object is additive — every field a client already reads
        # directly off the top-level response (mode, llm_provider, the
        # embedding/tenant fields above) must keep working unchanged.
        body = env.client.get("/api/health").json()
        assert set(body) >= {"status", "mode", "llm_provider", "embedding_provider", "tenants", "llm"}
        assert body["mode"] == "dev"
        assert body["llm_provider"] == body["llm"]["provider"]

    def test_llm_metadata_present_and_not_ready_for_fake_provider(self, env):
        # conftest forces BRF_LLM=fake for the whole test session — the
        # header status must never claim a model is active for it.
        llm = env.client.get("/api/health").json()["llm"]
        assert llm["provider"] == "fake"
        assert llm["ready"] is False
        assert llm["model"] == ""
        assert llm["display_name"] == ""

    def test_llm_metadata_ready_and_named_for_selfhosted_provider(self, env, monkeypatch):
        import app.llm as llm_mod

        monkeypatch.setenv("BRF_LLM", "selfhosted")
        monkeypatch.setenv("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("BRF_LLM_MODEL", "gemma4:e12b")
        monkeypatch.setenv("BRF_LLM_RUNTIME_LABEL", "agenntserver")
        monkeypatch.setattr(llm_mod, "_provider", None)
        try:
            llm = env.client.get("/api/health").json()["llm"]
            assert llm["provider"] == "selfhosted"
            assert llm["model"] == "gemma4:e12b"
            assert llm["display_name"] == "Gemma 4 12B"
            assert llm["runtime_label"] == "agenntserver"
            assert llm["ready"] is True
        finally:
            # The provider cache is process-global — leaving a stray
            # selfhosted instance behind would bleed into later tests that
            # expect the session's forced BRF_LLM=fake.
            monkeypatch.setattr(llm_mod, "_provider", None)

    def test_llm_metadata_none_provider_reads_not_ready_unnamed(self, env, monkeypatch):
        import app.llm as llm_mod

        monkeypatch.setenv("BRF_LLM", "none-does-not-exist-so-falls-through")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("app.llm_hosted.shutil.which", lambda _: None)
        monkeypatch.setattr(llm_mod, "_provider", None)
        try:
            llm = env.client.get("/api/health").json()["llm"]
            assert llm["provider"] == "none"
            assert llm["ready"] is False
            assert llm["model"] == ""
            assert llm["display_name"] == ""
        finally:
            monkeypatch.setattr(llm_mod, "_provider", None)

    def test_llm_metadata_never_leaks_endpoint_or_credentials(self, env, monkeypatch):
        import app.llm as llm_mod

        monkeypatch.setenv("BRF_LLM", "selfhosted")
        monkeypatch.setenv("BRF_LLM_BASE_URL", "http://internal-secret-host:8000/v1")
        monkeypatch.setenv("BRF_LLM_MODEL", "gemma4:e12b")
        monkeypatch.setenv("BRF_LLM_API_KEY", "sk-super-secret-token")
        monkeypatch.setattr(llm_mod, "_provider", None)
        try:
            raw = env.client.get("/api/health").content.decode("utf-8")
            assert "sk-super-secret-token" not in raw
            assert "internal-secret-host" not in raw
            assert "/v1" not in raw
            assert ".gguf" not in raw
        finally:
            monkeypatch.setattr(llm_mod, "_provider", None)

    def test_llm_model_field_matches_the_model_answer_py_actually_used(self, env, monkeypatch):
        """The health metadata and a real /ask response must report the same
        model string for the same cached provider — the header must never
        drift from what actually generated the answer."""

        class StubSelfhosted:
            name = "selfhosted"
            model = "gemma4:e12b"

            def complete(self, *a, **kw):
                raise Exception("stub never actually generates in this test")

        stub = StubSelfhosted()
        monkeypatch.setattr("app.llm.pick_provider", lambda: stub)
        monkeypatch.setattr("app.answer.pick_provider", lambda: stub)

        health_model = env.client.get("/api/health").json()["llm"]["model"]
        ask_body = env.client.post(
            "/api/brf/brf-a/ask", json={"question": "Vad gäller?"}, headers=env.admin_a_headers
        ).json()
        assert ask_body["model"] == health_model == "gemma4:e12b"


class TestAuthFlow:
    def test_login_sets_cookie_and_returns_memberships(self, env):
        r = env.client.post("/api/auth/login", json={"email": "admin-a@a.se", "password": "lösenord-a-admin"})
        assert r.status_code == 200
        assert "brf_session" in r.cookies
        assert r.json()["memberships"][0]["brf_id"] == "brf-a"

    def test_bad_password_401(self, env):
        r = env.client.post("/api/auth/login", json={"email": "admin-a@a.se", "password": "fel"})
        assert r.status_code == 401

    def test_login_body_carries_no_session_token(self, env):
        """The session travels as the httpOnly cookie and nowhere else.

        Echoing it in the JSON body put a long-lived credential somewhere
        page script — or any logging proxy in between — could read it, which
        is exactly what httpOnly exists to prevent.
        """
        r = env.client.post(
            "/api/auth/login",
            json={"email": "admin-a@a.se", "password": "lösenord-a-admin"},
        )
        env.client.cookies.clear()
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"user", "memberships"}
        assert "token" not in body
        # The cookie is still issued, and is httpOnly.
        set_cookie = r.headers["set-cookie"]
        assert "brf_session=" in set_cookie
        assert "httponly" in set_cookie.lower()

    def test_me_requires_auth(self, env):
        assert env.client.get("/api/auth/me").status_code == 401
        r = env.client.get("/api/auth/me", headers=env.admin_a_headers)
        assert r.status_code == 200 and r.json()["user"]["email"] == "admin-a@a.se"

    def test_logout_invalidates_session(self, env):
        tok = env.token("admin-a@a.se", "lösenord-a-admin")
        h = {"Cookie": f"brf_session={tok}"}
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

    def test_fake_provider_never_claims_the_configured_tenant_model(self, env, monkeypatch):
        from app.llm import FakeLLM

        store = env.registry.get("brf-a")
        chunk_id = next(iter(store.chunks))
        fake = FakeLLM([{
            "answer": "Föreningen Alfa har en hemlig kod ALFA-XYZZY-111 i sina stadgar.",
            "citations": [{
                "chunk_id": chunk_id,
                "quote": "Föreningen Alfa har en hemlig kod ALFA-XYZZY-111 i sina stadgar.",
            }],
            "insufficient_data": False,
        }])
        monkeypatch.setattr("app.answer.pick_provider", lambda: fake)

        r = env.client.post(
            "/api/brf/brf-a/ask",
            json={"question": "Vad är Alfadata?"},
            headers=env.admin_a_headers,
        )

        assert r.status_code == 200
        assert r.json()["provider"] == "fake"
        assert r.json()["model"] == ""


class TestAskTenantNamePropagation:
    """Proves the registered tenant name actually reaches the numeric
    grounding gate THROUGH THE REAL ROUTE (main.py's api_ask calling
    auth.get_tenant(brf_id) and forwarding it into ask()'s trusted_names
    kwarg) — not just through the ask() function's optional argument
    exercised directly in test_answer.py. A pure-function or direct-ask()
    test alone would miss a route left disconnected from the fix."""

    def _tenant_with_digit_name(self, env):
        brf_id = env.registry.create("Brf Gjutformen 12", "synthetic", "brf-g12")
        admin = env.auth.create_user("admin-g12@g12.se", "lösenord-g12-admin", "Admin G12")
        env.auth.add_membership(admin, brf_id, "admin")
        headers = env.auth_headers("admin-g12@g12.se", "lösenord-g12-admin")
        pdf = build_pdf([[("Antal lägenheter: 56 lägenheter enligt stadgarna.", 72, 100)]])
        r = env.client.post(
            f"/api/brf/{brf_id}/documents", files={"file": ("Info.pdf", pdf, "application/pdf")}, headers=headers
        )
        assert r.status_code == 200, r.text
        return brf_id, headers

    def test_tenant_name_digit_does_not_trigger_refusal_via_the_real_route(self, env, monkeypatch):
        from app.llm import FakeLLM

        brf_id, headers = self._tenant_with_digit_name(env)
        chunk_id = next(iter(env.registry.get(brf_id).chunks))
        fake = FakeLLM([{
            "answer": "BRF GJUTFORMEN 12 har 56 lägenheter.",
            "citations": [{"chunk_id": chunk_id, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }])
        # The route itself must resolve auth.get_tenant(brf_id) and forward
        # the name — nothing in this test constructs trusted_names by hand.
        monkeypatch.setattr("app.answer.pick_provider", lambda: fake)

        r = env.client.post(
            f"/api/brf/{brf_id}/ask", json={"question": "Hur många lägenheter har föreningen?"}, headers=headers
        )

        assert r.status_code == 200
        body = r.json()
        assert body["refusal"] is False, body

    def test_separate_unsupported_quantity_still_refused_via_the_real_route(self, env, monkeypatch):
        """Control: the same tenant-name mention must not become a blanket
        exemption — an unrelated wrong number in the same answer still
        refuses, proving the route's propagation isn't over-broad either."""
        from app.llm import FakeLLM

        brf_id, headers = self._tenant_with_digit_name(env)
        chunk_id = next(iter(env.registry.get(brf_id).chunks))
        bad = {
            "answer": "BRF GJUTFORMEN 12 har 65 lägenheter.",  # wrong count: 65, not 56
            "citations": [{"chunk_id": chunk_id, "quote": "Antal lägenheter: 56 lägenheter"}],
            "insufficient_data": False,
        }
        fake = FakeLLM([bad, bad])
        monkeypatch.setattr("app.answer.pick_provider", lambda: fake)

        r = env.client.post(
            f"/api/brf/{brf_id}/ask", json={"question": "Hur många lägenheter har föreningen?"}, headers=headers
        )

        assert r.status_code == 200
        body = r.json()
        assert body["refusal"] is True
        assert body["refusal_reason"] == "numeric_grounding_failed"


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


class TestPlannedAskFlag:
    """BRF-1 endpoint wiring: the planned path is reachable only behind BOTH
    the server flag and the per-request opt-in, and the default is untouched."""

    def _plan_provider(self, monkeypatch, script):
        from app.llm import FakeLLM

        stub = FakeLLM(script)
        monkeypatch.setattr("app.llm.pick_provider", lambda: stub)
        monkeypatch.setattr("app.answer.pick_provider", lambda: stub)
        monkeypatch.setattr("app.multihop.pick_provider", lambda: stub)
        return stub

    def test_default_request_never_reaches_the_planner(self, env, monkeypatch):
        monkeypatch.setenv("BRF_PLANNED_ASK", "1")
        stub = self._plan_provider(monkeypatch, [])
        env.client.post(
            "/api/brf/brf-a/ask", json={"question": "Vad står i stadgarna?"}, headers=env.admin_a_headers
        )
        assert all("planerar dokumentsökningar" not in c["system"] for c in stub.calls)

    def test_opt_in_without_the_server_flag_is_ignored(self, env, monkeypatch):
        monkeypatch.delenv("BRF_PLANNED_ASK", raising=False)
        stub = self._plan_provider(monkeypatch, [])
        r = env.client.post(
            "/api/brf/brf-a/ask",
            json={"question": "Vad står i stadgarna?", "planned": True},
            headers=env.admin_a_headers,
        )
        assert r.status_code == 200
        assert all("planerar dokumentsökningar" not in c["system"] for c in stub.calls)

    def test_clarify_is_distinguishable_from_an_ordinary_refusal(self, env, monkeypatch):
        monkeypatch.setenv("BRF_PLANNED_ASK", "1")
        self._plan_provider(monkeypatch, [
            {"mode": "clarify", "subqueries": [], "clarification": "Vilket avtal menar du?"},
        ])
        body = env.client.post(
            "/api/brf/brf-a/ask",
            json={"question": "När går avtalet ut?", "planned": True},
            headers=env.admin_a_headers,
        ).json()
        assert body["refusal"] is True
        assert body["citations"] == []
        assert body["clarification"] == "Vilket avtal menar du?"

    def test_ordinary_refusal_carries_no_clarification(self, env):
        body = env.client.post(
            "/api/brf/brf-a/ask", json={"question": "Vad står i stadgarna?"}, headers=env.admin_a_headers
        ).json()
        assert body["refusal"] is True
        assert body["clarification"] is None
