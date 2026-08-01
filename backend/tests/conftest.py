import os

import pytest

# Tests must be offline + deterministic: no model downloads, no real LLM.
os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("BRF_LLM", "fake")


def pytest_collection_modifyitems(config, items):
    run_llm = os.environ.get("RUN_LLM_TESTS") == "1"
    skip_llm = pytest.mark.skip(reason="set RUN_LLM_TESTS=1 to run real-LLM tests")
    for item in items:
        if "llm" in item.keywords and not run_llm:
            item.add_marker(skip_llm)


@pytest.fixture()
def two_tenant_app(tmp_path):
    """A live app with two fully separate tenants and users of each, plus
    building blocks the API/isolation suites share. Returns a namespace with
    the TestClient and per-tenant fixtures."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.auth import AuthStore
    from app.main import SESSION_COOKIE, create_app
    from app.registry import TenantRegistry
    from tests.pdf_fixtures import build_pdf

    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    app = create_app(registry=registry, auth=auth, data_root=tmp_path)
    client = TestClient(app)

    registry.create("Brf A", "synthetic", "brf-a")
    registry.create("Brf B", "synthetic", "brf-b")

    admin_a = auth.create_user("admin-a@a.se", "lösenord-a-admin", "Admin A")
    member_a = auth.create_user("member-a@a.se", "lösenord-a-medlem", "Member A")
    admin_b = auth.create_user("admin-b@b.se", "lösenord-b-admin", "Admin B")
    auth.add_membership(admin_a, "brf-a", "admin")
    auth.add_membership(member_a, "brf-a", "member")
    auth.add_membership(admin_b, "brf-b", "admin")

    def token(email: str, password: str) -> str:
        """The session token, read from the Set-Cookie the server issued.

        Login no longer echoes the token in its JSON body (auth is
        cookie-only), so it is taken from the cookie itself.
        """
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        session = r.cookies.get(SESSION_COOKIE)
        assert session, "inloggningen satte ingen sessionskaka"
        # Drop it from the shared jar: tests pass the session EXPLICITLY per
        # request, so "no header" must keep meaning "no session".
        client.cookies.clear()
        return session

    def auth_headers(email: str, password: str) -> dict:
        return {"Cookie": f"{SESSION_COOKIE}={token(email, password)}"}

    # Distinguishable content per tenant so leakage is detectable.
    doc_a = build_pdf([[("Föreningen Alfa har en hemlig kod ALFA-XYZZY-111 i sina stadgar.", 72, 100)]])
    doc_b = build_pdf([[("Föreningen Beta har en hemlig kod BETA-PLUGH-222 i sina stadgar.", 72, 100)]])

    ha = auth_headers("admin-a@a.se", "lösenord-a-admin")
    hb = auth_headers("admin-b@b.se", "lösenord-b-admin")
    ra = client.post("/api/brf/brf-a/documents", files={"file": ("StadgarA.pdf", doc_a, "application/pdf")}, headers=ha)
    rb = client.post("/api/brf/brf-b/documents", files={"file": ("StadgarB.pdf", doc_b, "application/pdf")}, headers=hb)
    assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)

    return SimpleNamespace(
        client=client,
        auth=auth,
        registry=registry,
        auth_headers=auth_headers,
        token=token,
        admin_a_headers=ha,
        admin_b_headers=hb,
        member_a_headers=auth_headers("member-a@a.se", "lösenord-a-medlem"),
        doc_a_id=ra.json()["id"],
        doc_b_id=rb.json()["id"],
        secret_a="ALFA-XYZZY-111",
        secret_b="BETA-PLUGH-222",
    )


@pytest.fixture()
def integration_env(tmp_path):
    """One tenant with the seeded demo corpus, ready for integration work.

    The real corpus is used rather than a hand-built page, because the whole
    point of the review engine is that it reads amounts out of documents that
    were not written to make it succeed. `Snöröjningsavtal 2026.pdf` states an
    hourly rate in prose, in a table-less paragraph, with a trailing comma —
    which is exactly the shape that broke the first version.
    """
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    backend_root = str(Path(__file__).resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from app.auth import AuthStore
    from app.integrations.accounting_fixture import FixtureAccountingAdapter
    from app.registry import TenantRegistry
    from scripts.seed import seed_demo

    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    seed_demo(registry, auth)

    brf_id = "gjutformen-12"
    store = registry.get(brf_id)
    assert store is not None, "seed_demo skapade inte den förväntade föreningen"

    adapter = FixtureAccountingAdapter()

    def import_invoice(external_ref: str):
        return store.integrations.upsert_invoice(adapter.get_invoice(brf_id, external_ref))

    return SimpleNamespace(
        root=tmp_path,
        auth=auth,
        registry=registry,
        brf_id=brf_id,
        store=store,
        integrations=store.integrations,
        adapter=adapter,
        import_invoice=import_invoice,
    )
