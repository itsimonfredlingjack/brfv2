"""Proves the demo membership contract the frontend's active-BRF selector
depends on, through the real HTTP surface — not just the seed internals
(test_seed.py) or the auth primitives (test_auth.py). Regression target: a
demo account silently starting with incomplete membership data would make
the sidebar selector look broken/hardcoded without any backend signal.
"""

from fastapi.testclient import TestClient

from app.auth import AuthStore
from app.main import create_app
from app.registry import TenantRegistry
from scripts.seed import seed_demo


def _seeded_client(tmp_path):
    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    seed_demo(registry, auth)
    app = create_app(registry=registry, auth=auth, data_root=tmp_path)
    return TestClient(app)


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


class TestDemoAccountMemberships:
    def test_max_has_admin_gjutformen_and_member_sjoutsikten(self, tmp_path):
        client = _seeded_client(tmp_path)
        body = _login(client, "max@demo.se", "max-demo-2026")
        by_brf = {m["brf_id"]: m["role"] for m in body["memberships"]}
        assert by_brf == {"gjutformen-12": "admin", "sjoutsikten-7": "member"}

        # /api/auth/me (session-restore path) must agree with the login
        # response — this is what the frontend's mount-time bootstrap calls.
        # The login cookie is already in this client's jar — that IS the
        # session the browser would carry.
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert {m["brf_id"]: m["role"] for m in me.json()["memberships"]} == by_brf

    def test_anna_has_exactly_one_membership(self, tmp_path):
        client = _seeded_client(tmp_path)
        body = _login(client, "anna@gjutformen12.se", "gjutformen-demo-2026")
        assert len(body["memberships"]) == 1
        assert body["memberships"][0]["brf_id"] == "gjutformen-12"
        assert body["memberships"][0]["role"] == "admin"

    def test_max_admin_role_enforced_on_gjutformen_upload(self, tmp_path):
        client = _seeded_client(tmp_path)
        _login(client, "max@demo.se", "max-demo-2026")
        r = client.post(
            "/api/brf/gjutformen-12/documents",
            files={"file": ("x.pdf", b"%PDF-1.4 not-a-real-pdf", "application/pdf")},
        )
        # Admin is authorized (a malformed PDF body fails later in the
        # pipeline, not at the role gate) — 403 would mean the membership
        # role backend enforces doesn't match what /api/auth/me advertised.
        assert r.status_code != 403

    def test_max_member_role_forbidden_from_sjoutsikten_upload(self, tmp_path):
        client = _seeded_client(tmp_path)
        _login(client, "max@demo.se", "max-demo-2026")
        r = client.post(
            "/api/brf/sjoutsikten-7/documents",
            files={"file": ("x.pdf", b"%PDF-1.4 not-a-real-pdf", "application/pdf")},
        )
        assert r.status_code == 403
