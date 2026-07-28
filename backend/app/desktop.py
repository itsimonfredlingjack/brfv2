"""Desktop-only FastAPI adapter for the Tauri 2 feasibility spike.

The product API remains owned by :func:`app.main.create_app`.  This module
only supplies the loopback HTTP boundary needed by the desktop shell:

* bind an OS-selected port on 127.0.0.1;
* mount the canonical built frontend below /brfv2/;
* emit one machine-readable readiness record after Uvicorn is listening;
* constrain Host/Origin and add HTTP security headers;
* use an installation-specific, /api/-scoped session cookie.

Run from ``backend/`` with::

    uv run python -m app.desktop --dist ../brfv2-mockup/dist \
      --data-root /path/chosen/by/tauri --seed-demo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import socket
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import AuthStore
from .main import create_app
from .registry import TenantRegistry

STARTUP_SCHEMA = "brfv2-desktop-startup/v1"
LOOPBACK_HOST = "127.0.0.1"
COOKIE_ID_FILE = ".desktop-cookie-id"
COOKIE_ID_RE = re.compile(r"^[a-f0-9]{24}$")
DESKTOP_COOKIE_PATH = "/api/"

CSP = "; ".join(
    (
        "default-src 'none'",
        "base-uri 'self'",
        "connect-src 'self'",
        "font-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "img-src 'self' data: blob:",
        "manifest-src 'self'",
        "media-src 'self' blob:",
        "object-src 'none'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "worker-src 'self' blob:",
    )
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": (
        "camera=(), display-capture=(), geolocation=(), microphone=(), "
        "payment=(), usb=()"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _default_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "brfv2-mockup" / "dist"


def _load_or_create_cookie_name(data_root: Path) -> str:
    """Persist an opaque cookie-name suffix inside Tauri's app-data root.

    Cookie names are not secrets.  The per-install suffix prevents accidental
    collisions with browser development sessions and other installations; the
    /api/ path narrows ambient delivery.  Cookies remain host-scoped, not
    port-scoped, so the HTTP and navigation boundaries are still mandatory.
    """

    data_root.mkdir(parents=True, exist_ok=True)
    identifier_path = data_root / COOKIE_ID_FILE
    try:
        identifier = identifier_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        identifier = secrets.token_hex(12)
        try:
            fd = os.open(identifier_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            identifier = identifier_path.read_text(encoding="ascii").strip()
        else:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(identifier + "\n")

    if not COOKIE_ID_RE.fullmatch(identifier):
        raise RuntimeError(f"Ogiltigt desktop-cookie-id i {identifier_path}")
    return f"brf_desktop_{identifier}"


def create_desktop_app(
    *,
    dist_dir: str | Path | None = None,
    data_root: str | Path,
    expected_origin: str,
    seed_demo: bool = False,
) -> FastAPI:
    """Create the same product app with an isolated desktop HTTP boundary."""

    dist = Path(dist_dir) if dist_dir is not None else _default_dist_dir()
    dist = dist.resolve()
    if not (dist / "index.html").is_file():
        raise RuntimeError(f"Byggd kanonisk frontend saknas: {dist / 'index.html'}")

    root = Path(data_root).resolve()
    auth = AuthStore(root / "auth.db")
    registry = TenantRegistry(root, auth)
    if seed_demo and not auth.list_tenants():
        # Development-only bootstrap for this un-packaged spike.  The data
        # lives in Tauri's app-data directory, never backend/data or pilot data.
        from scripts.seed import seed_demo as seed_demo_data

        seed_demo_data(registry, auth)

    app = create_app(
        registry=registry,
        auth=auth,
        data_root=root,
        session_cookie_name=_load_or_create_cookie_name(root),
        session_cookie_path=DESKTOP_COOKIE_PATH,
    )

    @app.middleware("http")
    async def desktop_http_boundary(request: Request, call_next):
        # Exact Host and Origin checks close the inherited development CORS
        # allowance and make DNS-rebinding/other-loopback-origin attempts fail
        # before auth or static content is reached.
        request_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        supplied_origin = request.headers.get("origin")
        if request_origin != expected_origin or (
            supplied_origin is not None and supplied_origin != expected_origin
        ):
            response = JSONResponse({"detail": "Otillåten desktop-origin."}, status_code=403)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @app.get("/", include_in_schema=False)
    def desktop_root() -> RedirectResponse:
        return RedirectResponse("/brfv2/")

    @app.get("/api/desktop/readiness", include_in_schema=False)
    def desktop_readiness() -> dict:
        return {
            "schema": STARTUP_SCHEMA,
            "status": "ready",
            "host": LOOPBACK_HOST,
            "port": int(expected_origin.rsplit(":", 1)[1]),
            "origin": expected_origin,
        }

    app.mount("/brfv2", StaticFiles(directory=dist, html=True), name="desktop-ui")
    return app


class _ReadinessServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, contract: dict) -> None:
        super().__init__(config)
        self._contract = contract

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            print(json.dumps(self._contract, sort_keys=True), flush=True)


def run(
    *,
    dist_dir: str | Path,
    data_root: str | Path,
    seed_demo: bool,
) -> None:
    """Bind a random loopback port and serve until the owner terminates us."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LOOPBACK_HOST, 0))
    port = int(listener.getsockname()[1])
    origin = f"http://{LOOPBACK_HOST}:{port}"
    contract = {
        "schema": STARTUP_SCHEMA,
        "status": "ready",
        "host": LOOPBACK_HOST,
        "port": port,
        "origin": origin,
    }
    app = create_desktop_app(
        dist_dir=dist_dir,
        data_root=data_root,
        expected_origin=origin,
        seed_demo=seed_demo,
    )
    config = uvicorn.Config(
        app,
        host=LOOPBACK_HOST,
        port=port,
        access_log=False,
        log_level="warning",
    )
    _ReadinessServer(config, contract).run(sockets=[listener])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=_default_dist_dir())
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--seed-demo", action="store_true")
    args = parser.parse_args()
    run(dist_dir=args.dist, data_root=args.data_root, seed_demo=args.seed_demo)


if __name__ == "__main__":
    main()
