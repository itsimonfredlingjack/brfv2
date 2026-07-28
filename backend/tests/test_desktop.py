from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.desktop import CSP, STARTUP_SCHEMA, create_desktop_app


def _dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(
        '<!doctype html><script type="module" src="/brfv2/assets/app.js"></script>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("document.body.textContent = 'desktop'", encoding="utf-8")
    return dist


def _client(tmp_path: Path, *, seed_demo: bool = False) -> TestClient:
    origin = "http://127.0.0.1:43123"
    app = create_desktop_app(
        dist_dir=_dist(tmp_path),
        data_root=tmp_path / "data",
        expected_origin=origin,
        seed_demo=seed_demo,
    )
    return TestClient(app, base_url=origin)


def test_same_origin_serves_real_ui_and_api_with_security_headers(tmp_path):
    with _client(tmp_path) as client:
        root = client.get("/", follow_redirects=False)
        ui = client.get("/brfv2/")
        health = client.get("/api/health")
        readiness = client.get("/api/desktop/readiness")

    assert root.status_code == 307
    assert root.headers["location"] == "/brfv2/"
    assert ui.status_code == 200
    assert "/brfv2/assets/app.js" in ui.text
    assert health.status_code == 200
    assert readiness.json() == {
        "schema": STARTUP_SCHEMA,
        "status": "ready",
        "host": "127.0.0.1",
        "port": 43123,
        "origin": "http://127.0.0.1:43123",
    }
    for response in (root, ui, health, readiness):
        assert response.headers["content-security-policy"] == CSP
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_desktop_boundary_rejects_other_hosts_ports_and_origins(tmp_path):
    with _client(tmp_path) as client:
        wrong_host = client.get("/api/health", headers={"host": "127.0.0.1:8787"})
        wrong_hostname = client.get("/api/health", headers={"host": "localhost:43123"})
        wrong_origin = client.post(
            "/api/auth/login",
            headers={"origin": "http://127.0.0.1:5173"},
            json={"email": "x@example.se", "password": "does-not-matter"},
        )

    assert wrong_host.status_code == 403
    assert wrong_hostname.status_code == 403
    assert wrong_origin.status_code == 403
    assert wrong_origin.headers["content-security-policy"] == CSP


def test_desktop_cookie_is_installation_specific_and_api_scoped(tmp_path):
    with _client(tmp_path, seed_demo=True) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "max@demo.se", "password": "max-demo-2026"},
        )
        me = client.get("/api/auth/me")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert re.search(r"^brf_desktop_[a-f0-9]{24}=", cookie)
    assert "HttpOnly" in cookie
    assert "Path=/api/" in cookie
    assert "SameSite=lax" in cookie
    assert me.status_code == 200
    assert {row["brf_id"] for row in me.json()["memberships"]} == {
        "gjutformen-12",
        "sjoutsikten-7",
    }


def test_cookie_identifier_is_stable_for_one_installation(tmp_path):
    _client(tmp_path)
    # Recreating the app over the same Tauri data root must reuse the cookie
    # name so persisted sessions remain usable between desktop launches.
    first_id = (tmp_path / "data" / ".desktop-cookie-id").read_text().strip()
    _client(tmp_path)
    second_id = (tmp_path / "data" / ".desktop-cookie-id").read_text().strip()

    assert first_id == second_id
    assert re.fullmatch(r"[a-f0-9]{24}", first_id)


def test_missing_built_frontend_fails_closed(tmp_path):
    missing = tmp_path / "missing-dist"
    try:
        create_desktop_app(
            dist_dir=missing,
            data_root=tmp_path / "data",
            expected_origin="http://127.0.0.1:43123",
        )
    except RuntimeError as exc:
        assert str(missing / "index.html") in str(exc)
    else:
        raise AssertionError("missing dist must not start an API-only desktop shell")
