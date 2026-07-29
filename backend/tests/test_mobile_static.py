"""Serving the built mobile client (xs_mobilapp) from /m.

Same origin as the API is the whole point: it is what lets the mobile client
reuse the httpOnly session cookie with no CORS entry and no token in
JavaScript.
"""

from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthStore
from app.main import create_app
from app.registry import TenantRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIST = REPO_ROOT / "xs_mobilapp" / "dist"

# A real, absolute, readable path outside dist — derived from this checkout
# rather than hardcoded, so the test travels with the repository instead of
# baking in one machine's layout.
ABSOLUTE_REPO_FILE = quote(str(REPO_ROOT / "SPEC.md"), safe="")
needs_build = pytest.mark.skipif(
    not (DIST / "index.html").is_file(),
    reason="mobilappen är inte byggd (kör `npm run build` i xs_mobilapp/)",
)


@pytest.fixture()
def client(tmp_path):
    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    return TestClient(create_app(registry=registry, auth=auth, data_root=tmp_path))


@needs_build
class TestServed:
    def test_root_serves_the_app(self, client):
        r = client.get("/m/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "<div id=\"root\">" in r.text

    def test_bare_m_redirects_to_the_app_root(self, client):
        r = client.get("/m", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/m/"

    @pytest.mark.parametrize("path", ["svar/abc123", "bibliotek", "dokument/doc-1", "konto"])
    def test_client_routes_fall_back_to_index(self, client, path):
        """The client owns its own routing — a deep link must open the app,
        not 404."""
        r = client.get(f"/m/{path}")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_manifest_and_service_worker_are_served(self, client):
        assert client.get("/m/manifest.webmanifest").status_code == 200
        sw = client.get("/m/sw.js")
        assert sw.status_code == 200
        # The service worker must never be pinned, or a deploy cannot land.
        assert sw.headers["cache-control"] == "no-cache"

    def test_index_is_not_cached_but_hashed_assets_are(self, client):
        assert client.get("/m/").headers["cache-control"] == "no-cache"

        asset = next((DIST / "assets").glob("*.js"), None)
        assert asset is not None, "inget byggt asset att kontrollera"
        r = client.get(f"/m/assets/{asset.name}")
        assert r.status_code == 200
        assert "immutable" in r.headers["cache-control"]

    def test_security_headers_are_served_with_the_app(self, client):
        """The app is same-origin by design and talks to nothing else. Stated
        as policy, a stray third-party script or beacon fails closed instead
        of quietly shipping document text off the device."""
        headers = client.get("/m/").headers
        csp = headers["content-security-policy"]

        assert "default-src 'self'" in csp
        assert "connect-src 'self'" in csp  # no exfiltration endpoint
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp  # not embeddable → no clickjacking
        assert "base-uri 'none'" in csp  # <base> cannot repoint relative URLs
        # Page rasters are rendered from IndexedDB blobs.
        assert "img-src 'self' blob: data:" in csp
        # No wildcard or scheme-only source anywhere.
        assert "*" not in csp
        assert "'unsafe-eval'" not in csp
        assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]

        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["x-frame-options"] == "DENY"

    def test_security_headers_cover_deep_links_and_assets_too(self, client):
        for path in ("svar/abc", "bibliotek", "sw.js", "manifest.webmanifest"):
            headers = client.get(f"/m/{path}").headers
            assert "content-security-policy" in headers, path
            assert headers["x-content-type-options"] == "nosniff", path

    def test_the_bundle_stays_inside_its_budget(self, client):
        """Not shipping a PDF engine is what buys the mobile performance
        budget. If this fails, something heavy was added — decide
        deliberately, do not just raise the number."""
        total = sum(p.stat().st_size for p in (DIST / "assets").glob("*.js"))
        assert total < 400_000, f"{total} bytes råstorlek JS (≈120 kB gzip-tak)"

    @pytest.mark.parametrize(
        "attack",
        [
            # Plain forms: the HTTP stack normalizes these away before routing,
            # so they never reach the handler at all.
            "../../SPEC.md",
            "../../../etc/passwd",
            "assets/../../../backend/app/main.py",
            # Percent-encoded forms survive normalization and DO arrive as a
            # literal "../.." path parameter — these are what the handler's
            # own containment check is for.
            "%2e%2e%2f%2e%2e%2fSPEC.md",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "assets%2f%2e%2e%2f%2e%2e%2f%2e%2e%2fbackend%2fapp%2fmain.py",
            # Absolute paths: pathlib's `/` operator DISCARDS the left operand
            # when the right is absolute, so `dist / "/etc/passwd"` is simply
            # "/etc/passwd". Only the containment check stops this one.
            "%2fetc%2fpasswd",
            ABSOLUTE_REPO_FILE,
        ],
    )
    def test_path_traversal_never_serves_anything_outside_dist(self, client, attack):
        """Either the request is refused or it falls back to index.html —
        what must never happen is a file from outside dist coming back."""
        r = client.get(f"/m/{attack}")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "text/html" in r.headers["content-type"]
        for leaked in ("Grounded Q&A Vertical Slice", "root:x:", "def create_app"):
            assert leaked not in r.text, f"{attack} läckte innehåll utanför dist"


@pytest.mark.skipif(
    (DIST / "index.html").is_file(),
    reason="dist finns — det här fallet gäller en obyggd utcheckning",
)
def test_unbuilt_app_says_so_instead_of_500(tmp_path):
    """A clean checkout that has not run `npm run build` should get a clear
    instruction, not a stack trace."""
    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    client = TestClient(create_app(registry=registry, auth=auth, data_root=tmp_path))

    r = client.get("/m/")
    assert r.status_code == 404
    assert "npm run build" in r.json()["detail"]
