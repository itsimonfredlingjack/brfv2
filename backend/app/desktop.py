"""Desktop product adapter — the loopback HTTP boundary the Tauri shell owns.

The product API and all product logic stay owned by :func:`app.main.create_app`.
This module only supplies what a *locally installed* application needs on top
of it:

* bind an OS-selected port on 127.0.0.1 and serve the canonical built frontend
  under ``/brfv2/`` from the same origin as ``/api/``;
* emit one machine-readable readiness record after Uvicorn is listening;
* constrain Host/Origin and add HTTP security headers;
* use an installation-specific, ``/api/``-scoped session cookie;
* run the product in ``BRF_MODE=desktop``: the self-hosted model runtime is the
  only generation path that can ever be selected, and the destructive dev-only
  ``/api/reset`` route is off;
* first-run provisioning (owner account + first BRF) so a normal user never
  needs a terminal, and no demo credentials ship with the product;
* explicit, user-visible model-runtime configuration instead of ambient
  environment variables — changeable only with installation-administrator
  authority, and only to an endpoint the policy in :mod:`app.model_endpoint`
  allows;
* durable local backup/restore of the whole application data directory.

Run from ``backend/`` with::

    python -m app.desktop --dist ../brfv2-mockup/dist \
      --data-root /path/chosen/by/tauri
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import shutil
import socket
import stat
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import BRF_ID_RE, AuthError, AuthStore
from .main import create_app
from .model_endpoint import (
    EndpointRejected,
    classify_endpoint,
    policy_document,
    require_allowed_endpoint,
)
from .registry import TenantRegistry

logger = logging.getLogger("brf.desktop")

APP_VERSION = "0.2.0"

STARTUP_SCHEMA = "brfv2-desktop-startup/v1"
STATE_SCHEMA = "brfv2-desktop-state/v1"
BACKUP_SCHEMA = "brfv2-backup/v1"

LOOPBACK_HOST = "127.0.0.1"
COOKIE_ID_FILE = ".desktop-cookie-id"
COOKIE_ID_RE = re.compile(r"^[a-f0-9]{24}$")
DESKTOP_COOKIE_PATH = "/api/"

CONFIG_FILE = "desktop-config.json"
BACKUP_MANIFEST = "brfv2-backup.json"
BACKUP_PAYLOAD_PREFIX = "data/"
BACKUP_NAME_RE = re.compile(r"^brfv2-backup-[0-9]{8}-[0-9]{6}(-[0-9a-f]{4})?\.zip$")
PENDING_RESTORE = "pending-restore.zip"
RESTORE_RESULT_FILE = "last-restore.json"

# The Tauri shell restarts the whole application when the backend exits with
# exactly this code.  Any other non-zero exit is a real failure and surfaces
# as a native error dialog instead.
RESTART_EXIT_CODE = 86

MIN_PASSWORD_LENGTH = 12

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


# --------------------------------------------------------------------------
# Model-runtime configuration
# --------------------------------------------------------------------------


class ModelRuntimeConfig(BaseModel):
    """The one outbound connection this product is allowed to make.

    Empty ``baseUrl`` is a first-class state: the app then runs with no
    generation provider at all and says so, rather than silently falling back
    to an ambient hosted API or a scripted stand-in.

    A non-empty ``baseUrl`` must satisfy :mod:`app.model_endpoint`.  That check
    lives in the type rather than in the route handler, so no path — the HTTP
    API, a hand-edited configuration file, or a restored backup — can put an
    address into effect that the policy would refuse.
    """

    baseUrl: str = ""
    model: str = "gemma4:e12b"
    apiKey: str = ""
    label: str = ""
    timeoutS: float = 300.0

    def normalized(self) -> "ModelRuntimeConfig":
        base = self.baseUrl.strip().rstrip("/")
        if base:
            require_allowed_endpoint(base)
        timeout = self.timeoutS if 1.0 <= self.timeoutS <= 3600.0 else 300.0
        return ModelRuntimeConfig(
            baseUrl=base,
            model=self.model.strip() or "gemma4:e12b",
            apiKey=self.apiKey.strip(),
            label=self.label.strip(),
            timeoutS=timeout,
        )

    def endpoint_decision(self) -> dict:
        return classify_endpoint(self.baseUrl).as_dict()

    def public(self) -> dict:
        """Everything the UI may see.  The bearer token never leaves the host
        process — the UI only learns whether one is stored."""
        decision = classify_endpoint(self.baseUrl)
        return {
            "baseUrl": self.baseUrl,
            "model": self.model,
            "label": self.label,
            "timeoutS": self.timeoutS,
            "hasApiKey": bool(self.apiKey),
            "configured": bool(self.baseUrl),
            "deploymentClass": decision.deployment_class,
        }


class DesktopConfig(BaseModel):
    schema_version: int = Field(default=1, alias="schemaVersion")
    llm: ModelRuntimeConfig = Field(default_factory=ModelRuntimeConfig)

    model_config = {"populate_by_name": True}


def _config_path(data_root: Path) -> Path:
    return data_root / CONFIG_FILE


def load_config(data_root: Path) -> DesktopConfig:
    path = _config_path(data_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DesktopConfig()
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Kunde inte läsa %s (%s) — använder tom konfiguration.", path, exc)
        return DesktopConfig()
    try:
        config = DesktopConfig.model_validate(raw)
    except Exception as exc:
        logger.error("Ogiltig desktopkonfiguration i %s (%s) — använder tom.", path, exc)
        return DesktopConfig()
    # The file is writable by the OS user, so what it says is a proposal, not a
    # decision.  An endpoint the policy refuses is dropped here rather than
    # trusted because it was already on disk — the installation then starts
    # with no generation provider and says so.
    try:
        config.llm.normalized()
    except EndpointRejected as exc:
        logger.error(
            "Modelltjänstens adress i %s är inte tillåten (%s: %s) — startar utan modelltjänst.",
            path,
            exc.code,
            exc.message,
        )
        return DesktopConfig(llm=ModelRuntimeConfig())
    return config


def save_config(data_root: Path, config: DesktopConfig) -> None:
    """Write 0600 and atomically — the file can hold a model bearer token."""
    path = _config_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config.model_dump(by_alias=True), handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def apply_model_runtime(config: ModelRuntimeConfig) -> None:
    """Make ``config`` the process-wide generation configuration.

    ``BRF_LLM`` is pinned to ``selfhosted`` unconditionally.  That is the
    runtime half of the no-hidden-egress guarantee: whatever third-party
    credentials or CLIs happen to exist on the machine, provider
    auto-detection can never select one here.  The structural half is the
    payload itself — the packaged delivery ships no hosted provider plug-in
    (``app.llm_hosted``), so :func:`app.llm.hosted_providers` finds nothing to
    register and no key selects one.  Without a configured base URL the
    provider becomes ``none`` and every answer attempt fails visibly instead
    of silently reaching a third party.

    The endpoint policy is re-checked here, at the last point before the
    address becomes process state.  Everything upstream already checks it; this
    is the check that makes "no disallowed destination is ever exported to the
    HTTP client" true by construction rather than by review.
    """

    from . import llm

    if config.baseUrl:
        require_allowed_endpoint(config.baseUrl)

    os.environ["BRF_LLM"] = "selfhosted"
    os.environ["BRF_LLM_BASE_URL"] = config.baseUrl
    os.environ["BRF_LLM_MODEL"] = config.model
    os.environ["BRF_LLM_TIMEOUT_S"] = str(config.timeoutS)
    os.environ["BRF_LLM_RUNTIME_LABEL"] = config.label
    if config.apiKey:
        os.environ["BRF_LLM_API_KEY"] = config.apiKey
    else:
        os.environ.pop("BRF_LLM_API_KEY", None)
    llm.reset_provider_cache()


def probe_model_runtime(config: ModelRuntimeConfig, *, timeout: float = 10.0) -> dict:
    """Ask the configured runtime what it serves.  Real request, real verdict."""

    if not config.baseUrl:
        return {"ok": False, "detail": "Ingen adress till modelltjänsten är angiven."}

    import httpx

    headers = {"Authorization": f"Bearer {config.apiKey}"} if config.apiKey else {}
    started = time.monotonic()
    try:
        response = httpx.get(f"{config.baseUrl}/models", headers=headers, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "detail": f"Kunde inte nå modelltjänsten: {type(exc).__name__}: {exc}",
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
    rows = body.get("data") or body.get("models") or []
    served = [str(row.get("id") or row.get("name") or "") for row in rows if isinstance(row, dict)]
    return {
        "ok": True,
        "detail": "Modelltjänsten svarar.",
        "latencyMs": int((time.monotonic() - started) * 1000),
        "served": served[:10],
    }


# --------------------------------------------------------------------------
# Backup and restore
# --------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _backup_inventory(data_root: Path) -> dict:
    auth_db = data_root / "auth.db"
    tenants: list[dict] = []
    if auth_db.is_file():
        try:
            for tenant in AuthStore(auth_db).list_tenants():
                docs = data_root / "tenants" / tenant["brf_id"] / "documents.json"
                try:
                    count = len(json.loads(docs.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError, TypeError):
                    count = 0
                tenants.append({"brf_id": tenant["brf_id"], "name": tenant["name"], "documents": count})
        except Exception as exc:  # a backup must never fail on inventory prose
            logger.warning("Kunde inte läsa säkerhetskopians innehållsförteckning: %s", exc)
    return {"tenants": tenants}


def _is_excluded_from_backup(relative: Path) -> bool:
    """True for the integration credential files, which never go in an archive.

    A backup is the artefact most likely to leave the machine: copied to a USB
    stick, mailed to a consultant, restored onto a spare laptop. A refresh
    token in it is a standing grant to read somebody's mailbox that outlives
    every conversation about who was allowed to, and nothing about a `.zip`
    named "backup" tells the person handling it that it is a credential.

    So the exclusion is structural rather than a cipher: the bytes are not in
    the archive at all. Everything about the connection *except* the secret is
    — which account, which scopes, who connected it — so a restored
    installation shows its integrations as needing to be signed in again
    rather than silently forgetting they existed. See
    ``app.integrations.credentials``.
    """
    from .integrations.credentials import SECRET_DIRNAME

    return SECRET_DIRNAME in relative.parts


def create_backup(data_root: Path, backup_root: Path) -> dict:
    """Zip the whole application data directory, atomically published.

    Everything except integration credentials — see
    :func:`_is_excluded_from_backup`.
    """

    backup_root.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_root, 0o700)
    stamp = _utc_now().strftime("%Y%m%d-%H%M%S")
    name = f"brfv2-backup-{stamp}-{secrets.token_hex(2)}.zip"
    target = backup_root / name
    tmp = backup_root / (name + ".part")

    inventory = _backup_inventory(data_root)

    # Decide what goes in before the manifest is written, so the manifest can
    # state the exclusion count. A manifest that described a different archive
    # than the one it sits in would be worse than no manifest.
    included: list[tuple[Path, Path]] = []
    excluded = 0
    for path in sorted(data_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(data_root)
        if _is_excluded_from_backup(relative):
            excluded += 1
            continue
        included.append((path, relative))

    manifest = {
        "schema": BACKUP_SCHEMA,
        "createdAt": _utc_now().isoformat(),
        "appVersion": APP_VERSION,
        # Stated in the archive itself: a restore is expected to ask for a new
        # sign-in, and the person doing it should learn that from the backup
        # rather than from a surprised integration.
        "excludedCredentialFiles": excluded,
        "excludedCredentialNote": (
            "Integrationernas hemligheter (access- och refresh-tokens) ingår aldrig i en "
            "säkerhetskopia. Efter återställning behöver en administratör ansluta igen."
        ),
        **inventory,
    }

    files = 0
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(BACKUP_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        for path, relative in included:
            archive.write(path, BACKUP_PAYLOAD_PREFIX + relative.as_posix())
            files += 1
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return {**_backup_row(target), "files": files, **inventory}


def _backup_row(path: Path) -> dict:
    stat_result = path.stat()
    return {
        "name": path.name,
        "bytes": stat_result.st_size,
        "createdAt": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat(),
    }


def list_backups(backup_root: Path) -> list[dict]:
    if not backup_root.is_dir():
        return []
    rows = [
        _backup_row(path)
        for path in backup_root.iterdir()
        if path.is_file() and BACKUP_NAME_RE.fullmatch(path.name)
    ]
    return sorted(rows, key=lambda row: row["createdAt"], reverse=True)


def read_backup_manifest(archive_path: Path) -> dict:
    """Validate an archive well enough to refuse anything that is not ours.

    Every member must live under ``data/`` and resolve inside the extraction
    root; absolute paths, ``..`` segments and symlink entries are rejected.
    """

    try:
        with zipfile.ZipFile(archive_path) as archive:
            try:
                manifest = json.loads(archive.read(BACKUP_MANIFEST))
            except KeyError as exc:
                raise ValueError("Filen saknar säkerhetskopians innehållsförteckning.") from exc
            if not isinstance(manifest, dict) or manifest.get("schema") != BACKUP_SCHEMA:
                raise ValueError("Filen är inte en säkerhetskopia från Träff.")
            for info in archive.infolist():
                if info.filename == BACKUP_MANIFEST:
                    continue
                name = info.filename
                if not name.startswith(BACKUP_PAYLOAD_PREFIX):
                    raise ValueError(f"Otillåten post i säkerhetskopian: {name!r}")
                if name.endswith("/"):
                    continue
                if _safe_relative(name[len(BACKUP_PAYLOAD_PREFIX):]) is None:
                    raise ValueError(f"Otillåten sökväg i säkerhetskopian: {name!r}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError(f"Symboliska länkar tillåts inte i säkerhetskopian: {name!r}")
    except zipfile.BadZipFile as exc:
        raise ValueError("Filen är inte ett läsbart zip-arkiv.") from exc
    return manifest


def _safe_relative(relative: str) -> str | None:
    """Return ``relative`` when it is a safe, contained relative path."""
    if not relative or relative.startswith("/"):
        return None
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return relative


def stage_restore(archive_path: Path, staging_root: Path) -> dict:
    manifest = read_backup_manifest(archive_path)
    staging_root.mkdir(parents=True, exist_ok=True)
    os.chmod(staging_root, 0o700)
    pending = staging_root / PENDING_RESTORE
    tmp = staging_root / (PENDING_RESTORE + ".part")
    shutil.copyfile(archive_path, tmp)
    os.replace(tmp, pending)
    return manifest


def apply_pending_restore(data_root: Path, staging_root: Path) -> dict | None:
    """Swap a staged backup into place before anything opens the data root.

    The current directory is only removed once the replacement is fully
    extracted and carries an ``auth.db``; any failure leaves the original data
    untouched and records the reason for the UI to show.
    """

    pending = staging_root / PENDING_RESTORE
    if not pending.is_file():
        return None

    incoming = data_root.with_name(data_root.name + ".incoming")
    previous = data_root.with_name(data_root.name + ".previous")
    result: dict
    try:
        manifest = read_backup_manifest(pending)
        shutil.rmtree(incoming, ignore_errors=True)
        incoming.mkdir(parents=True)
        os.chmod(incoming, 0o700)
        with zipfile.ZipFile(pending) as archive:
            for info in archive.infolist():
                if info.filename == BACKUP_MANIFEST or info.filename.endswith("/"):
                    continue
                relative = _safe_relative(info.filename[len(BACKUP_PAYLOAD_PREFIX):])
                if relative is None:
                    raise ValueError(f"Otillåten sökväg i säkerhetskopian: {info.filename!r}")
                target = incoming / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, "wb") as sink:
                    shutil.copyfileobj(source, sink)
        if not (incoming / "auth.db").is_file():
            raise ValueError("Säkerhetskopian saknar auth.db och kan inte återställas.")

        shutil.rmtree(previous, ignore_errors=True)
        if data_root.exists():
            os.replace(data_root, previous)
        os.replace(incoming, data_root)
        shutil.rmtree(previous, ignore_errors=True)
        result = {
            "status": "restored",
            "at": _utc_now().isoformat(),
            "createdAt": manifest.get("createdAt"),
            "appVersion": manifest.get("appVersion"),
        }
    except Exception as exc:
        logger.error("Återställning misslyckades: %s", exc)
        shutil.rmtree(incoming, ignore_errors=True)
        if not data_root.exists() and previous.exists():
            os.replace(previous, data_root)
        result = {"status": "failed", "at": _utc_now().isoformat(), "detail": str(exc)}
    finally:
        pending.unlink(missing_ok=True)

    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / RESTORE_RESULT_FILE).write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    return result


def read_last_restore(staging_root: Path) -> dict | None:
    try:
        return json.loads((staging_root / RESTORE_RESULT_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


def _default_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "brfv2-mockup" / "dist"


def _load_or_create_cookie_name(data_root: Path) -> str:
    """Persist an opaque cookie-name suffix inside the application data root.

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


def slugify_brf_id(name: str) -> str:
    """Derive a stable, BRF_ID_RE-valid id from a Swedish association name."""
    folded = (
        name.strip()
        .lower()
        .replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("é", "e")
        .replace("ü", "u")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:60].strip("-")
    # `val-` is reserved for the public_scraped validation corpus.
    if slug.startswith("val-"):
        slug = f"brf-{slug}"[:60].strip("-")
    if not slug or not BRF_ID_RE.fullmatch(slug):
        slug = "brf-" + secrets.token_hex(6)
    return slug


def _create_tenant(registry: TenantRegistry, name: str) -> str:
    """Create a BRF, disambiguating ids that a different name already took."""
    base = slugify_brf_id(name)
    for candidate in (base, *(f"{base[:55]}-{secrets.token_hex(2)}" for _ in range(4))):
        try:
            return registry.create(name, "customer", candidate)
        except AuthError as exc:
            if "finns redan" not in str(exc):
                raise
    raise AuthError("Kunde inte skapa ett unikt id för föreningen.")


class SetupRequest(BaseModel):
    name: str = ""
    email: str
    password: str
    brfName: str


class BrfRequest(BaseModel):
    name: str


class RuntimeConfigRequest(BaseModel):
    baseUrl: str = ""
    model: str = "gemma4:e12b"
    apiKey: str | None = None
    label: str = ""
    timeoutS: float = 300.0


def create_desktop_app(
    *,
    dist_dir: str | Path | None = None,
    data_root: str | Path,
    expected_origin: str,
    backup_root: str | Path | None = None,
    staging_root: str | Path | None = None,
    request_restart: Callable[[], None] | None = None,
    seed_demo: bool = False,
) -> FastAPI:
    """Create the product app behind an isolated desktop HTTP boundary."""

    dist = Path(dist_dir) if dist_dir is not None else _default_dist_dir()
    dist = dist.resolve()
    if not (dist / "index.html").is_file():
        raise RuntimeError(f"Byggd kanonisk frontend saknas: {dist / 'index.html'}")

    root = Path(data_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    backups = Path(backup_root).resolve() if backup_root is not None else root.parent / "backups"
    staging = Path(staging_root).resolve() if staging_root is not None else root.parent / "restore-staging"

    # "desktop" is neither "dev" (which enables the destructive global
    # /api/reset route) nor "pilot" (which refuses to boot without a reachable
    # self-hosted provider — an installed application must start and *explain*
    # a missing model runtime, not fail to open).
    os.environ["BRF_MODE"] = "desktop"
    config = load_config(root)
    apply_model_runtime(config.llm)

    auth = AuthStore(root / "auth.db")
    # Installations provisioned before this authority existed — including one
    # that arrives through a restored backup — must not end up with nobody who
    # can change the model service.
    adopted = auth.backfill_installation_admin()
    if adopted:
        logger.info("Installationsadministratör adopterad för befintlig installation: %s", adopted)
    registry = TenantRegistry(root, auth)
    if seed_demo and not auth.list_tenants():
        # Test/acceptance-only bootstrap.  The shipped application never passes
        # this: a real installation is provisioned through /api/desktop/setup,
        # so no demo credentials exist in the product.
        from scripts.seed import seed_demo as seed_demo_data

        seed_demo_data(registry, auth)

    cookie_name = _load_or_create_cookie_name(root)
    app = create_app(
        registry=registry,
        auth=auth,
        data_root=root,
        session_cookie_name=cookie_name,
        session_cookie_path=DESKTOP_COOKIE_PATH,
    )
    app.state.desktop_config = config

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

    def current_user(request: Request) -> dict:
        """The signed-in account, from the installation's cookie and nowhere else.

        The desktop routes resolve a session exactly the way
        :func:`app.main.create_app` does: the httpOnly, ``/api/``-scoped cookie
        is the only transport.  An ``Authorization: Bearer`` branch used to sit
        here, from when login still echoed the token in its JSON body.  Nothing
        issues such a token any more, so accepting one would only widen the auth
        surface of the *desktop* routes — the model-service configuration and
        the whole backup/restore surface — for a credential no legitimate client
        can obtain.
        """

        user = auth.resolve_session(request.cookies.get(cookie_name, ""))
        if user is None:
            raise HTTPException(status_code=401, detail="Inloggning krävs.")
        return user

    def installation_admin(user: dict = Depends(current_user)) -> dict:
        """Authority over settings that belong to the installation itself.

        An ordinary application account — a member, or even an admin of every
        association on the machine — cannot repoint the model service that all
        of their documents are sent to.  That is a decision about the installed
        machine, and it is held by whoever provisioned it.
        """

        if not auth.is_installation_admin(user["id"]):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Ändringar av modelltjänsten kräver installationsadministratör — "
                    "det kontot som konfigurerade den här installationen."
                ),
            )
        return user

    def _issue_session(user_id: str, response: Response) -> dict:
        token = auth.create_session(user_id)
        response.set_cookie(
            cookie_name,
            token,
            httponly=True,
            samesite="lax",
            max_age=14 * 24 * 3600,
            path=DESKTOP_COOKIE_PATH,
        )
        # Same shape as /api/auth/login: the session travels as the httpOnly
        # cookie set above and is not echoed here.  First-run provisioning is
        # the one place in the product that signs an account in without a
        # password prompt, so it is exactly the response that must not hand a
        # long-lived credential to page script.
        return {
            "user": auth.get_user(user_id),
            "memberships": auth.memberships_for(user_id),
        }

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

    @app.get("/api/desktop/state", include_in_schema=False)
    def desktop_state(request: Request) -> dict:
        # configured_provider_name(), not get_embedder(): this route gates the
        # whole UI on first paint, and constructing the embedder loads ~500 MB
        # of weights. The desktop application pins BRF_EMBEDDER=model2vec, so
        # the configured name is the name that will be used — and the weights
        # still load lazily on the first ingestion or question.
        from .embeddings import configured_provider_name
        from .llm import pick_provider
        from .ocr import tesseract_available

        provider = pick_provider()
        # The setup screen needs this before any account exists, so the route
        # cannot require a session.  Signed-in callers get the configured
        # address; everyone else only learns whether generation is available at
        # all, so an unauthenticated caller never reads a private network
        # address out of the installation.
        session_user = auth.resolve_session(request.cookies.get(cookie_name, ""))
        signed_in = session_user is not None
        runtime = app.state.desktop_config.llm
        return {
            "schema": STATE_SCHEMA,
            "app": {"name": "Träff", "version": APP_VERSION},
            # Pre-login truth the setup screen needs, and nothing more: a
            # boolean, never an account list.
            "provisioned": bool(auth.list_tenants()),
            "storage": {
                "dataDir": str(root),
                "backupDir": str(backups),
            },
            "ocr": {"available": tesseract_available("swe"), "language": "swe"},
            "embedding": {"provider": configured_provider_name()},
            "modelRuntime": {
                **(runtime.public() if signed_in else {"configured": bool(runtime.baseUrl)}),
                "provider": provider.name,
                "ready": provider.name not in ("none", "fake"),
            },
            # What the UI must know to tell the truth about who may change the
            # model service, and which addresses would be accepted if they did.
            "installationAdmin": bool(
                session_user and auth.is_installation_admin(session_user["id"])
            ),
            "modelEndpointPolicy": policy_document(),
            "lastRestore": read_last_restore(staging),
            "restartSupported": request_restart is not None,
        }

    @app.post("/api/desktop/setup", include_in_schema=False)
    def desktop_setup(req: SetupRequest, response: Response) -> dict:
        # First-run only.  Once any BRF exists this route is permanently shut,
        # so it can never be used to mint a second owner behind the login.
        if auth.list_tenants():
            raise HTTPException(status_code=409, detail="Installationen är redan konfigurerad.")
        email = req.email.strip().lower()
        if "@" not in email or len(email) < 5:
            raise HTTPException(status_code=422, detail="Ange en giltig e-postadress.")
        if len(req.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Lösenordet måste vara minst {MIN_PASSWORD_LENGTH} tecken.",
            )
        brf_name = req.brfName.strip()
        if len(brf_name) < 2:
            raise HTTPException(status_code=422, detail="Ange föreningens namn.")
        try:
            user_id = auth.create_user(email, req.password, req.name.strip() or email.split("@")[0])
            brf_id = _create_tenant(registry, brf_name)
            auth.add_membership(user_id, brf_id, "admin")
            # The account that provisions the machine is the installation
            # administrator.  There is no other way to obtain that authority in
            # the shipped product, and this route is permanently shut once any
            # association exists.
            auth.grant_installation_admin(user_id)
        except (AuthError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.info("Installation konfigurerad: förening %s", brf_id)
        return _issue_session(user_id, response)

    @app.post("/api/desktop/brf", include_in_schema=False)
    def desktop_create_brf(req: BrfRequest, user: dict = Depends(current_user)) -> dict:
        name = req.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="Ange föreningens namn.")
        try:
            brf_id = _create_tenant(registry, name)
            auth.add_membership(user["id"], brf_id, "admin")
        except (AuthError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"brf_id": brf_id, "memberships": auth.memberships_for(user["id"])}

    @app.get("/api/desktop/model-runtime", include_in_schema=False)
    def get_model_runtime(user: dict = Depends(current_user)) -> dict:
        # Readable by any signed-in account: the configured runtime is the
        # provenance shown next to every generated answer.  Changing it is the
        # privileged operation, not seeing it.
        return app.state.desktop_config.llm.public()

    @app.get("/api/desktop/model-endpoint-policy", include_in_schema=False)
    def get_model_endpoint_policy() -> dict:
        return policy_document()

    @app.put("/api/desktop/model-runtime", include_in_schema=False)
    def put_model_runtime(
        req: RuntimeConfigRequest, user: dict = Depends(installation_admin)
    ) -> dict:
        current = app.state.desktop_config.llm
        try:
            updated = ModelRuntimeConfig(
                baseUrl=req.baseUrl,
                model=req.model,
                # `null` keeps the stored token; "" clears it.
                apiKey=current.apiKey if req.apiKey is None else req.apiKey,
                label=req.label,
                timeoutS=req.timeoutS,
            ).normalized()
        except EndpointRejected as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.message,
                headers={"X-Model-Endpoint-Rejection": exc.code},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        config = DesktopConfig(llm=updated)
        save_config(root, config)
        app.state.desktop_config = config
        apply_model_runtime(updated)
        logger.info(
            "Modelltjänsten ändrad av installationsadministratör %s till %s (%s).",
            user["id"],
            updated.baseUrl or "(ingen)",
            updated.endpoint_decision()["deploymentClass"] or "unconfigured",
        )
        return updated.public()

    @app.post("/api/desktop/model-runtime/test", include_in_schema=False)
    def test_model_runtime(user: dict = Depends(installation_admin)) -> dict:
        # A probe is an outbound connection made on request.  It goes only to
        # the already-approved address, and only for the account that is
        # allowed to choose that address in the first place.
        return probe_model_runtime(app.state.desktop_config.llm)

    @app.get("/api/desktop/backups", include_in_schema=False)
    def get_backups(user: dict = Depends(current_user)) -> dict:
        return {"backupDir": str(backups), "backups": list_backups(backups)}

    @app.post("/api/desktop/backups", include_in_schema=False)
    def post_backup(user: dict = Depends(current_user)) -> dict:
        try:
            return create_backup(root, backups)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Säkerhetskopian misslyckades: {exc}") from exc

    @app.delete("/api/desktop/backups/{name}", include_in_schema=False)
    def delete_backup(name: str, user: dict = Depends(current_user)) -> dict:
        if not BACKUP_NAME_RE.fullmatch(name):
            raise HTTPException(status_code=404, detail="Okänd säkerhetskopia.")
        target = backups / name
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Okänd säkerhetskopia.")
        target.unlink()
        return {"deleted": name}

    @app.post("/api/desktop/backups/{name}/restore", include_in_schema=False)
    def post_restore(name: str, user: dict = Depends(current_user)) -> dict:
        if not BACKUP_NAME_RE.fullmatch(name):
            raise HTTPException(status_code=404, detail="Okänd säkerhetskopia.")
        target = backups / name
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Okänd säkerhetskopia.")
        try:
            manifest = stage_restore(target, staging)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # The swap itself happens at the next start, before a single store is
        # opened — never underneath live SQLite handles and cached indexes.
        return {
            "staged": name,
            "restartRequired": True,
            "createdAt": manifest.get("createdAt"),
        }

    @app.post("/api/desktop/restart", include_in_schema=False)
    def post_restart(user: dict = Depends(current_user)) -> dict:
        if request_restart is None:
            raise HTTPException(status_code=501, detail="Omstart stöds inte i detta läge.")
        request_restart()
        return {"restarting": True}

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
    backup_root: str | Path | None = None,
    staging_root: str | Path | None = None,
    seed_demo: bool = False,
) -> int:
    """Bind a random loopback port and serve until the owner terminates us.

    Returns the process exit code: ``RESTART_EXIT_CODE`` when the application
    asked to be restarted (a staged restore), otherwise 0.
    """

    root = Path(data_root).resolve()
    staging = Path(staging_root).resolve() if staging_root is not None else root.parent / "restore-staging"
    backups = Path(backup_root).resolve() if backup_root is not None else root.parent / "backups"

    # Before any store, index or SQLite handle exists.
    restored = apply_pending_restore(root, staging)
    if restored:
        logger.info("Återställning: %s", restored.get("status"))

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

    restart_requested = threading.Event()
    server_holder: dict[str, uvicorn.Server] = {}

    def request_restart() -> None:
        restart_requested.set()

        def _stop() -> None:
            # Let the HTTP response reach the webview before the socket dies.
            time.sleep(0.4)
            server = server_holder.get("server")
            if server is not None:
                server.should_exit = True

        threading.Thread(target=_stop, name="brf-desktop-restart", daemon=True).start()

    app = create_desktop_app(
        dist_dir=dist_dir,
        data_root=root,
        expected_origin=origin,
        backup_root=backups,
        staging_root=staging,
        request_restart=request_restart,
        seed_demo=seed_demo,
    )
    config = uvicorn.Config(
        app,
        host=LOOPBACK_HOST,
        port=port,
        access_log=False,
        log_level="warning",
    )
    server = _ReadinessServer(config, contract)
    server_holder["server"] = server
    server.run(sockets=[listener])
    return RESTART_EXIT_CODE if restart_requested.is_set() else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=_default_dist_dir())
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=None)
    parser.add_argument("--staging-root", type=Path, default=None)
    parser.add_argument("--model2vec", type=Path, default=None, help="Lokal katalog med model2vec-vikter")
    parser.add_argument("--seed-demo", action="store_true", help="Endast test/acceptans")
    args = parser.parse_args()
    if args.model2vec is not None:
        # Bundled weights: the packaged application must never reach
        # huggingface.co, so the path is supplied and downloads are disabled.
        os.environ["BRF_MODEL2VEC_PATH"] = str(args.model2vec)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("BRF_EMBEDDER", "model2vec")
    raise SystemExit(
        run(
            dist_dir=args.dist,
            data_root=args.data_root,
            backup_root=args.backup_root,
            staging_root=args.staging_root,
            seed_demo=args.seed_demo,
        )
    )


if __name__ == "__main__":
    main()
