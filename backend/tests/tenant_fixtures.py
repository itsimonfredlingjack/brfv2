"""Shared harness for auth/tenancy tests: a fresh app with real AuthStore +
TenantRegistry rooted in a temp dir, plus helpers to mint tenants, users and
session tokens."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import AuthStore
from app.main import SESSION_COOKIE, create_app
from app.registry import TenantRegistry

DEFAULT_PW = "hemligt-losen-123"


class Harness:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.auth = AuthStore(tmp_path / "auth.db")
        self.registry = TenantRegistry(tmp_path, self.auth)
        self.app = create_app(registry=self.registry, auth=self.auth, data_root=tmp_path)
        self.client = TestClient(self.app)

    def make_tenant(self, name: str, corpus_origin: str, brf_id: str | None = None) -> str:
        return self.registry.create(name, corpus_origin, brf_id)

    def make_user(self, email: str, memberships=(), password: str = DEFAULT_PW) -> str:
        uid = self.auth.create_user(email, password)
        for brf_id, role in memberships:
            self.auth.add_membership(uid, brf_id, role)
        return uid

    def login(self, email: str, password: str = DEFAULT_PW) -> str:
        """Returns the session token from the Set-Cookie — auth is cookie-only,
        so the login body no longer carries one."""
        r = self.client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        session = r.cookies.get(SESSION_COOKIE)
        assert session, "inloggningen satte ingen sessionskaka"
        self.client.cookies.clear()
        return session

    def session(self, token: str) -> dict:
        """Headers carrying one specific session, passed explicitly so that a
        request without them is genuinely unauthenticated."""
        return {"Cookie": f"{SESSION_COOKIE}={token}"}
