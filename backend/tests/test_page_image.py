"""Rasterized page images for the mobile client (xs_mobilapp).

The mobile app replaces pdf.js with `GET .../page/{n}?w=` plus plain boxes
drawn from the citation rects. That only holds if the raster shares one
coordinate space with the extraction the rects came from — so the geometry
assertions here are load-bearing product behavior, not smoke tests.
"""

import struct

import pytest

from app.main import PAGE_IMAGE_WIDTHS
from tests.pdf_fixtures import build_pdf


def png_size(body: bytes) -> tuple[int, int]:
    """(width, height) from the IHDR chunk — no image library needed."""
    assert body[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", body[16:24])
    return width, height


@pytest.fixture()
def env(two_tenant_app):
    return two_tenant_app


def page_url(brf_id: str, doc_id: str, page: int = 1) -> str:
    return f"/api/brf/{brf_id}/documents/{doc_id}/page/{page}"


class TestRendering:
    def test_returns_a_png_at_the_requested_width(self, env):
        r = env.client.get(page_url("brf-a", env.doc_a_id), params={"w": 1080}, headers=env.member_a_headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert png_size(r.content)[0] == 1080

    @pytest.mark.parametrize("width", PAGE_IMAGE_WIDTHS)
    def test_every_allowed_width_renders_at_exactly_that_width(self, env, width):
        r = env.client.get(page_url("brf-a", env.doc_a_id), params={"w": width}, headers=env.member_a_headers)
        assert r.status_code == 200
        assert png_size(r.content)[0] == width

    def test_default_width_is_1080(self, env):
        r = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.member_a_headers)
        assert png_size(r.content)[0] == 1080

    def test_aspect_ratio_matches_the_declared_page_points(self, env):
        """The client computes `scale = imageWidthPx / widthPt` and applies it
        to BOTH axes. If the raster's aspect ratio ever drifted from the page
        points reported by /extraction, every highlight would be vertically
        offset — silently, and worse the further down the page it sits."""
        r = env.client.get(page_url("brf-a", env.doc_a_id), params={"w": 1080}, headers=env.member_a_headers)
        px_w, px_h = png_size(r.content)
        width_pt = float(r.headers["X-Page-Width-Pt"])
        height_pt = float(r.headers["X-Page-Height-Pt"])

        expected_h = px_w * (height_pt / width_pt)
        assert abs(px_h - expected_h) <= 1, f"{px_h} vs expected {expected_h:.2f}"

    def test_declared_points_agree_with_the_extraction_endpoint(self, env):
        """Same page, two endpoints, one coordinate space. The mobile client
        reads dimensions from /extraction and pixels from here; a disagreement
        between them puts highlights in the wrong place."""
        img = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.member_a_headers)
        extraction = env.client.get(
            f"/api/brf/brf-a/documents/{env.doc_a_id}/extraction", headers=env.member_a_headers
        ).json()
        page_one = extraction["pages"][0]

        assert float(img.headers["X-Page-Width-Pt"]) == pytest.approx(page_one["width"], abs=0.01)
        assert float(img.headers["X-Page-Height-Pt"]) == pytest.approx(page_one["height"], abs=0.01)

    def test_never_stored_in_the_browser_cache(self, env):
        """These bytes are tenant document content.

        The browser's HTTP cache is not something the app's logout can clear,
        so a cached page image would be a copy of one user's documents that
        outlives their session on a shared device — outside the
        tenant-namespaced client store the wipe guarantee rests on. The client
        keeps its own copy, so no-store costs nothing.
        """
        r = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.member_a_headers)
        cache_control = r.headers["cache-control"]
        assert "no-store" in cache_control
        assert "immutable" not in cache_control
        assert "max-age" not in cache_control

    def test_multi_page_documents_render_each_page(self, env):
        pdf = build_pdf(
            [
                [("Sida ett handlar om snöröjning.", 72, 100)],
                [("Sida två handlar om underhållsplanen.", 72, 100)],
                [("Sida tre handlar om avgifter.", 72, 100)],
            ]
        )
        doc_id = env.client.post(
            "/api/brf/brf-a/documents",
            files={"file": ("Flersidig.pdf", pdf, "application/pdf")},
            headers=env.admin_a_headers,
        ).json()["id"]

        for page in (1, 2, 3):
            r = env.client.get(page_url("brf-a", doc_id, page), headers=env.member_a_headers)
            assert r.status_code == 200, f"sida {page}: {r.text}"
            assert png_size(r.content)[0] == 1080


class TestGuards:
    @pytest.mark.parametrize("width", [1, 800, 2000, 4096, 100000, -1080, 0])
    def test_width_outside_the_allowlist_is_rejected(self, env, width):
        """An open width parameter is a rasterization amplifier: each distinct
        value is a fresh MuPDF render that no cache absorbs."""
        r = env.client.get(page_url("brf-a", env.doc_a_id), params={"w": width}, headers=env.member_a_headers)
        assert r.status_code == 400

    def test_non_numeric_width_is_rejected(self, env):
        r = env.client.get(page_url("brf-a", env.doc_a_id), params={"w": "stor"}, headers=env.member_a_headers)
        assert r.status_code == 422

    @pytest.mark.parametrize("page", [0, -1, 2, 999])
    def test_page_out_of_range_is_404(self, env, page):
        r = env.client.get(page_url("brf-a", env.doc_a_id, page), headers=env.member_a_headers)
        assert r.status_code == 404

    def test_unknown_document_is_404(self, env):
        r = env.client.get(page_url("brf-a", "finns-inte"), headers=env.member_a_headers)
        assert r.status_code == 404

    def test_anonymous_access_is_401(self, env):
        r = env.client.get(page_url("brf-a", env.doc_a_id))
        assert r.status_code == 401


class TestIsolation:
    def test_a_member_of_b_cannot_render_a_page_of_a(self, env):
        r = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.admin_b_headers)
        assert r.status_code == 404
        assert r.content[:8] != b"\x89PNG\r\n\x1a\n"

    def test_cross_tenant_document_id_under_own_tenant_is_404(self, env):
        """A's document id addressed through B's own tenant path — the id is
        real, the membership is real, the pairing is not."""
        r = env.client.get(page_url("brf-b", env.doc_a_id), headers=env.admin_b_headers)
        assert r.status_code == 404

    def test_non_member_gets_404_not_403(self, env):
        """Existence must not be probeable: an outsider learns nothing about
        whether brf-a exists (main.py's tenant_store contract)."""
        outsider = env.auth.create_user("utomstaende@x.se", "lösenord-utan-medlemskap")
        assert outsider
        headers = env.auth_headers("utomstaende@x.se", "lösenord-utan-medlemskap")
        real = env.client.get(page_url("brf-a", env.doc_a_id), headers=headers)
        fake = env.client.get(page_url("brf-finns-inte", env.doc_a_id), headers=headers)
        assert real.status_code == fake.status_code == 404
        assert real.json() == fake.json()

    def test_deleted_document_stops_rendering(self, env):
        """No raster survives the document it came from — the reason this
        endpoint renders on demand instead of caching to disk."""
        before = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.member_a_headers)
        assert before.status_code == 200

        env.client.delete(f"/api/brf/brf-a/documents/{env.doc_a_id}", headers=env.admin_a_headers)

        after = env.client.get(page_url("brf-a", env.doc_a_id), headers=env.member_a_headers)
        assert after.status_code == 404
