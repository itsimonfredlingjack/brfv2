"""Adversarial tenant-isolation suite (SPEC-PILOT "the hard part").

Every test here is an ATTACK: a member of BRF A actively trying to retrieve,
cite, see, or delete BRF B's content — through the API, crafted ids, crafted
queries, forged sessions, and path tricks. The suite passing is the phase's
definition of working. A green run here means none of these attacks reached
B's data.
"""

import pytest

from tests.pdf_fixtures import build_pdf


@pytest.fixture()
def env(two_tenant_app):
    return two_tenant_app


class TestCrossTenantRead:
    def test_a_admin_cannot_list_b_documents(self, env):
        r = env.client.get("/api/brf/brf-b/documents", headers=env.admin_a_headers)
        assert r.status_code == 404  # 404 not 403 — existence is not leaked

    def test_a_admin_cannot_fetch_b_pdf(self, env):
        r = env.client.get(f"/api/brf/brf-b/documents/{env.doc_b_id}/pdf", headers=env.admin_a_headers)
        assert r.status_code == 404
        assert env.secret_b.encode() not in r.content

    def test_a_admin_cannot_read_b_extraction(self, env):
        r = env.client.get(f"/api/brf/brf-b/documents/{env.doc_b_id}/extraction", headers=env.admin_a_headers)
        assert r.status_code == 404

    def test_a_admin_cannot_read_b_settings(self, env):
        assert env.client.get("/api/brf/brf-b/settings", headers=env.admin_a_headers).status_code == 404

    def test_bs_doc_id_under_as_path_is_not_found(self, env):
        # B's real document id, but requested under A's tenant path.
        r = env.client.get(f"/api/brf/brf-a/documents/{env.doc_b_id}/pdf", headers=env.admin_a_headers)
        assert r.status_code == 404


class TestCrossTenantWrite:
    def test_a_admin_cannot_upload_into_b(self, env):
        pdf = build_pdf([[("Intrångsdokument.", 72, 100)]])
        r = env.client.post(
            "/api/brf/brf-b/documents", files={"file": ("evil.pdf", pdf, "application/pdf")}, headers=env.admin_a_headers
        )
        assert r.status_code == 404
        # B's document set is unchanged.
        docs_b = env.client.get("/api/brf/brf-b/documents", headers=env.admin_b_headers).json()
        assert [d["id"] for d in docs_b] == [env.doc_b_id]

    def test_a_admin_cannot_delete_b_document(self, env):
        r = env.client.delete(f"/api/brf/brf-b/documents/{env.doc_b_id}", headers=env.admin_a_headers)
        assert r.status_code == 404
        assert env.client.get(f"/api/brf/brf-b/documents/{env.doc_b_id}/pdf", headers=env.admin_b_headers).status_code == 200

    def test_a_admin_cannot_delete_b_tenant(self, env):
        r = env.client.delete("/api/brf/brf-b", headers=env.admin_a_headers)
        assert r.status_code == 404
        assert env.auth.get_tenant("brf-b") is not None

    def test_a_admin_cannot_change_b_settings(self, env):
        s = env.client.get("/api/brf/brf-a/settings", headers=env.admin_a_headers).json()
        s["topK"] = 42
        assert env.client.put("/api/brf/brf-b/settings", json=s, headers=env.admin_a_headers).status_code == 404


class TestCrossTenantRetrieval:
    def test_a_query_for_bs_secret_never_retrieves_b(self, env):
        # Ask A, using B's unique code as the query. B's content must not appear
        # anywhere in A's retrieval set.
        r = env.client.post(
            "/api/brf/brf-a/ask", json={"question": f"Vad betyder koden {env.secret_b}?"}, headers=env.admin_a_headers
        )
        assert r.status_code == 200
        body = r.json()
        blob = str(body)
        assert env.secret_b not in blob
        assert "StadgarB.pdf" not in blob
        for hit in body.get("retrieval", []):
            assert hit["document_name"] == "StadgarA.pdf"

    def test_retrieval_indexes_are_physically_separate(self, env):
        store_a = env.registry.get("brf-a")
        store_b = env.registry.get("brf-b")
        assert store_a is not store_b
        assert store_a.index is not store_b.index
        a_text = " ".join(c.text for c in store_a.chunks.values())
        b_text = " ".join(c.text for c in store_b.chunks.values())
        assert env.secret_a in a_text and env.secret_b not in a_text
        assert env.secret_b in b_text and env.secret_a not in b_text


class TestForgedCredentials:
    def test_no_session_is_401_everywhere(self, env):
        for method, path in [
            ("get", "/api/brf/brf-a/documents"),
            ("post", "/api/brf/brf-a/ask"),
            ("get", "/api/brf/brf-a/settings"),
            ("delete", f"/api/brf/brf-a/documents/{env.doc_a_id}"),
            ("delete", "/api/brf/brf-a"),
        ]:
            kwargs = {"json": {"question": "x"}} if method == "post" else {}
            resp = getattr(env.client, method)(path, **kwargs)
            assert resp.status_code == 401, (path, resp.status_code)

    def test_forged_bearer_token_rejected(self, env):
        h = {"Authorization": "Bearer " + "f" * 43}
        assert env.client.get("/api/brf/brf-a/documents", headers=h).status_code == 401

    def test_bs_valid_session_cannot_touch_a(self, env):
        # A perfectly valid B session is still a stranger to A.
        hb = env.admin_b_headers
        assert env.client.get("/api/brf/brf-a/documents", headers=hb).status_code == 404
        assert env.client.get(f"/api/brf/brf-a/documents/{env.doc_a_id}/pdf", headers=hb).status_code == 404


class TestIdTricks:
    @pytest.mark.parametrize(
        "brf_id",
        ["../brf-b", "brf-b/../brf-b", "brf-a/../../etc", "..%2fbrf-b", "brf_b", "BRF-B", " brf-b"],
    )
    def test_path_and_case_tricks_do_not_reach_another_tenant(self, env, brf_id):
        r = env.client.get(f"/api/brf/{brf_id}/documents", headers=env.admin_a_headers)
        # Either not found / not routed — never B's actual document list.
        assert r.status_code in (401, 403, 404), (brf_id, r.status_code)
        if r.status_code == 200:  # defensive: if it somehow routed, must not be B
            assert all(d["id"] != env.doc_b_id for d in r.json())

    def test_unknown_tenant_is_404_for_member(self, env):
        assert env.client.get("/api/brf/does-not-exist/documents", headers=env.admin_a_headers).status_code == 404


class TestFilesystemSeparation:
    def test_tenant_directories_are_disjoint(self, env, tmp_path):
        pa = env.registry._tenant_dir("brf-a").resolve()
        pb = env.registry._tenant_dir("brf-b").resolve()
        assert pa != pb
        assert not str(pa).startswith(str(pb)) and not str(pb).startswith(str(pa))
        # Each tenant's PDF bytes live only under its own directory.
        a_pdfs = list((pa / "docs").glob("*.pdf"))
        b_pdfs = list((pb / "docs").glob("*.pdf"))
        assert a_pdfs and b_pdfs
        assert {p.name for p in a_pdfs}.isdisjoint({p.name for p in b_pdfs})


class TestRouteCoverageMetaGuard:
    def test_every_tenant_route_depends_on_auth(self, env):
        """Meta-test: no /api/brf/{brf_id}/... route may exist without going
        through the tenant_store or require_admin dependency. Catches a future
        route added without isolation."""
        from app import main

        app = env.client.app
        guarded = {"tenant_store", "require_admin"}
        offenders = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/brf/{brf_id}"):
                continue
            dep_names = _dependency_names(route)
            if not (guarded & dep_names):
                offenders.append((path, sorted(dep_names)))
        assert not offenders, f"Unguarded tenant routes: {offenders}"


def _dependency_names(route) -> set:
    names: set[str] = set()
    dependant = getattr(route, "dependant", None)
    stack = [dependant] if dependant else []
    while stack:
        d = stack.pop()
        call = getattr(d, "call", None)
        if call is not None and getattr(call, "__name__", None):
            names.add(call.__name__)
        stack.extend(getattr(d, "dependencies", []) or [])
    return names
