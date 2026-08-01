"""OAuth 2.0 for a desktop application that must not open a listening port.

Two flows, chosen by what the provider supports rather than by preference:

**Device code** (Microsoft). The application asks the authority for a code, the
operator types it into their own browser on any device, and the application
polls until the sign-in completes. No redirect URI, no inbound socket, no
secret in the client. This is the flow the installed desktop product uses.

**Authorization code with a pasted code** (Fortnox, and Microsoft where an
administrator has disabled device code). The application builds the authorize
URL, the operator opens it, and the provider redirects to the URI the
integration owner registered. The operator copies the ``code`` from that
address bar back into the application, which redeems it.

The pasted-code variant exists because the alternative is worse. Catching the
redirect ourselves means binding a port and accepting connections *into* a
desktop application that otherwise listens only on a random loopback port for
its own UI — a real attack surface, added so an operator can avoid one
copy-paste. ``state`` is generated per login and verified on the way back, and
PKCE is used wherever the provider accepts it, so the pasted value alone is not
enough to complete somebody else's login.

Pending logins live in memory (:class:`PendingLogins`), never on disk. A device
code and a PKCE verifier are single-use credentials with a lifetime measured in
minutes; writing them down to survive a restart would trade a real secret for a
convenience nobody asked for. A restart during sign-in means signing in again.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

from .egress import ReadOnlyEgress, RemoteError, read_json

logger = logging.getLogger("brf.integrations.oauth")

# How long an operator has to finish a sign-in before the application forgets
# what it was doing. Microsoft's device code expires in 15 minutes and a
# Fortnox authorization code in 10; 20 minutes is past both.
PENDING_TTL_S = 20 * 60

LoginKind = Literal["device", "code"]


class OAuthError(RuntimeError):
    """A sign-in could not be completed. The message is shown to an operator."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OAuthApp:
    """The registered application this installation signs in as.

    ``client_secret`` is empty for a public client (Microsoft desktop). A
    provider that requires a confidential client — Fortnox — puts its secret
    here, and it comes from the tenant's secret file, never from configuration
    that a backup would carry.
    """

    provider: str
    client_id: str
    authority_base: str
    authorize_path: str
    token_path: str
    scopes: tuple[str, ...]
    client_secret: str = ""
    device_code_path: str = ""
    redirect_uri: str = ""
    use_pkce: bool = True
    # Extra query parameters the provider requires on the authorize URL and
    # nowhere else (Fortnox: access_type=offline, account_type=service).
    extra_authorize_params: tuple[tuple[str, str], ...] = ()

    @property
    def scope_string(self) -> str:
        return " ".join(self.scopes)

    def url(self, path: str) -> str:
        return f"{self.authority_base.rstrip('/')}{path}"

    def basic_auth(self) -> str | None:
        if not self.client_secret:
            return None
        raw = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")


@dataclass
class PendingLogin:
    id: str
    provider: str
    tenant_id: str
    kind: LoginKind
    created_at: float
    expires_at: float
    # device flow
    device_code: str = ""
    user_code: str = ""
    verification_uri: str = ""
    interval_s: int = 5
    next_poll_at: float = 0.0
    # authorization-code flow
    state: str = ""
    code_verifier: str = ""
    authorize_url: str = ""

    def public(self) -> dict:
        """What the UI is told. Never ``device_code`` or ``code_verifier``.

        ``user_code`` is here and ``device_code`` is not, which is the whole
        point of the pair: the short one is meant to be read aloud and typed,
        the long one is the credential that redeems the login.
        """
        return {
            "id": self.id,
            "provider": self.provider,
            "kind": self.kind,
            "userCode": self.user_code,
            "verificationUri": self.verification_uri,
            "authorizeUrl": self.authorize_url,
            "expiresInS": max(0, int(self.expires_at - time.time())),
            "intervalS": self.interval_s,
        }


class PendingLogins:
    """In-memory, per (tenant, provider). One sign-in at a time, deliberately."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_key: dict[tuple[str, str], PendingLogin] = {}

    def start(self, pending: PendingLogin) -> PendingLogin:
        with self._lock:
            self._by_key[(pending.tenant_id, pending.provider)] = pending
        return pending

    def get(self, tenant_id: str, provider: str) -> PendingLogin | None:
        with self._lock:
            found = self._by_key.get((tenant_id, provider))
            if found is None:
                return None
            if found.expires_at <= time.time():
                self._by_key.pop((tenant_id, provider), None)
                return None
            return found

    def clear(self, tenant_id: str, provider: str) -> None:
        with self._lock:
            self._by_key.pop((tenant_id, provider), None)


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int
    granted_scopes: list[str] = field(default_factory=list)

    @property
    def expires_epoch(self) -> float:
        # 60 seconds of slack. A token that expires while a request is in
        # flight is a failure an operator sees; refreshing a minute early is
        # one they never do.
        return time.time() + max(0, self.expires_in - 60)


def _number(value: object, fallback: float) -> float:
    """A numeric field, where a legitimate zero is not the same as an absent one."""
    if value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _token_set(payload: dict, *, previous_refresh: str = "") -> TokenSet:
    access = str(payload.get("access_token") or "")
    if not access:
        raise OAuthError("no_access_token", "Svaret från inloggningen saknar access_token.")
    # Providers that rotate refresh tokens return a new one every time and
    # invalidate the old. Providers that do not, omit the field — and dropping
    # the one we already hold would silently turn a durable connection into a
    # one-hour one.
    refresh = str(payload.get("refresh_token") or "") or previous_refresh
    scope = str(payload.get("scope") or "")
    return TokenSet(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(_number(payload.get("expires_in"), 3600)),
        granted_scopes=[s for s in scope.replace(",", " ").split() if s],
    )


# ---------------------------------------------------------------------------
# Device code
# ---------------------------------------------------------------------------


def begin_device_login(
    egress: ReadOnlyEgress, app: OAuthApp, *, tenant_id: str
) -> PendingLogin:
    if not app.device_code_path:
        raise OAuthError(
            "device_flow_unsupported",
            f"{app.provider} har ingen device code-endpoint konfigurerad.",
        )
    reply = egress.token_post(
        app.url(app.device_code_path),
        {"client_id": app.client_id, "scope": app.scope_string},
        purpose="login",
    )
    payload = read_json(reply, provider=app.provider)
    if not isinstance(payload, dict) or not payload.get("device_code"):
        raise OAuthError("device_flow_failed", "Inloggningen kunde inte startas.")
    now = time.time()
    # `or` would be wrong here: an authority that answers ``"interval": 0``
    # means "poll as fast as you like", and `0 or 5` turns that into a
    # five-second wait before the first poll — which reads to an operator as
    # the application ignoring them.
    lifetime = float(_number(payload.get("expires_in"), 900))
    interval = int(_number(payload.get("interval"), 5))
    return PendingLogin(
        id=secrets.token_hex(8),
        provider=app.provider,
        tenant_id=tenant_id,
        kind="device",
        created_at=now,
        expires_at=now + min(lifetime, PENDING_TTL_S),
        device_code=str(payload["device_code"]),
        user_code=str(payload.get("user_code") or ""),
        verification_uri=str(
            payload.get("verification_uri_complete") or payload.get("verification_uri") or ""
        ),
        interval_s=interval,
        next_poll_at=now + interval,
    )


def poll_device_login(
    egress: ReadOnlyEgress, app: OAuthApp, pending: PendingLogin
) -> TokenSet | None:
    """One poll. ``None`` means "still waiting", an exception means it failed.

    The authority's own ``interval`` is respected: polling faster earns a
    ``slow_down`` and, kept up, a refused login.
    """
    now = time.time()
    if now < pending.next_poll_at:
        return None
    pending.next_poll_at = now + pending.interval_s
    reply = egress.token_post(
        app.url(app.token_path),
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": app.client_id,
            "device_code": pending.device_code,
        },
        purpose="token",
    )
    if 200 <= reply.status < 300:
        return _token_set(reply.json() or {})
    payload = {}
    try:
        payload = reply.json() or {}
    except ValueError:
        pass
    error = str(payload.get("error") or "")
    if error == "authorization_pending":
        return None
    if error == "slow_down":
        pending.interval_s += 5
        pending.next_poll_at = now + pending.interval_s
        return None
    if error == "expired_token":
        raise OAuthError("expired", "Inloggningskoden hann gå ut. Starta om anslutningen.")
    if error == "authorization_declined":
        raise OAuthError("declined", "Inloggningen avbröts i webbläsaren.")
    raise OAuthError(
        "device_flow_failed",
        str(payload.get("error_description") or error or f"HTTP {reply.status}"),
    )


# ---------------------------------------------------------------------------
# Authorization code
# ---------------------------------------------------------------------------


def begin_code_login(app: OAuthApp, *, tenant_id: str) -> PendingLogin:
    """Build the authorize URL. Nothing leaves the process here."""
    if not app.redirect_uri:
        raise OAuthError(
            "missing_redirect_uri",
            "Ange samma redirect-URI som är registrerad hos leverantören.",
        )
    now = time.time()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)[:128] if app.use_pkce else ""
    params: list[tuple[str, str]] = [
        ("client_id", app.client_id),
        ("response_type", "code"),
        ("redirect_uri", app.redirect_uri),
        ("scope", app.scope_string),
        ("state", state),
    ]
    if verifier:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        params += [("code_challenge", challenge), ("code_challenge_method", "S256")]
    params += list(app.extra_authorize_params)
    return PendingLogin(
        id=secrets.token_hex(8),
        provider=app.provider,
        tenant_id=tenant_id,
        kind="code",
        created_at=now,
        expires_at=now + PENDING_TTL_S,
        state=state,
        code_verifier=verifier,
        authorize_url=f"{app.url(app.authorize_path)}?{urlencode(params)}",
    )


def redeem_code(
    egress: ReadOnlyEgress,
    app: OAuthApp,
    pending: PendingLogin,
    *,
    code: str,
    state: str = "",
) -> TokenSet:
    """Exchange a pasted authorization code for tokens.

    ``state`` is compared in constant time when the operator supplied it —
    pasting the whole redirect URL is the common case and carries it. A blank
    state is accepted only because some providers drop the parameter from the
    address bar, and the code is still single-use and bound to this client.
    """
    if state:
        if not secrets.compare_digest(state, pending.state):
            raise OAuthError(
                "state_mismatch",
                "Adressen hör inte till den här inloggningen (state stämmer inte). "
                "Starta om anslutningen.",
            )
    form = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": app.redirect_uri,
    }
    basic = app.basic_auth()
    if basic is None:
        form["client_id"] = app.client_id
    if pending.code_verifier:
        form["code_verifier"] = pending.code_verifier
    reply = egress.token_post(app.url(app.token_path), form, basic_auth=basic, purpose="token")
    try:
        payload = read_json(reply, provider=app.provider)
    except RemoteError as exc:
        raise OAuthError("code_rejected", f"Koden accepterades inte: {exc.detail}") from exc
    return _token_set(payload if isinstance(payload, dict) else {})


def refresh_tokens(egress: ReadOnlyEgress, app: OAuthApp, *, refresh_token: str) -> TokenSet:
    if not refresh_token:
        raise OAuthError(
            "no_refresh_token",
            "Anslutningen har ingen refresh-token kvar. Anslut igen.",
        )
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    basic = app.basic_auth()
    if basic is None:
        form["client_id"] = app.client_id
        form["scope"] = app.scope_string
    reply = egress.token_post(app.url(app.token_path), form, basic_auth=basic, purpose="token")
    try:
        payload = read_json(reply, provider=app.provider)
    except RemoteError as exc:
        # A refused refresh is not a transient error: consent was withdrawn,
        # the token rotated out from under us, or the app registration
        # changed. Saying "anslut igen" is the only useful instruction.
        raise OAuthError(
            "refresh_rejected",
            f"Anslutningen kunde inte förnyas ({exc.detail}). Anslut igen.",
        ) from exc
    return _token_set(payload if isinstance(payload, dict) else {}, previous_refresh=refresh_token)


__all__ = [
    "OAuthApp",
    "OAuthError",
    "PENDING_TTL_S",
    "PendingLogin",
    "PendingLogins",
    "TokenSet",
    "begin_code_login",
    "begin_device_login",
    "poll_device_login",
    "redeem_code",
    "refresh_tokens",
]
