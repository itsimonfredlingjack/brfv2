"""One place that knows how a live integration is configured, signed in and used.

The adapters (:mod:`.graph_mail`, :mod:`.fortnox`) are deliberately ignorant:
each is handed an access token and a configuration and can do nothing else. All
the state that makes those objects possible — which app registration, whose
sign-in, which token, when it expires, when it stopped working — lives here, so
there is exactly one answer to "may this installation read that mailbox right
now", and exactly one place that can change it.

The lifecycle is three separate human acts, kept separate because they are
answerable by different people at different times:

``configure`` → ``connect`` → ``use``

Configuration says *where* to look and needs no credential. Connecting is a
named administrator signing in to a system the association does not own, and it
is recorded with their id. Using it refreshes silently and records the failure
when it cannot, because a connection that quietly stops working is worse than
one that says so.

Refresh is where the care is. A refreshed token is written **before** it is
returned, and a provider that rotates its refresh token has the new one
persisted in the same write — losing a rotated refresh token means the
connection is dead with no way back but signing in again, and it is the one
bug in an OAuth client that cannot be recovered from at runtime.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from . import fortnox as fortnox_mod
from . import graph_mail as graph_mod
from .credentials import Connection, ConnectionError_, CredentialStore, Secrets
from .egress import EgressPolicy, ReadOnlyEgress, RemoteError, Transport
from .models import utc_now_iso
from .oauth import (
    OAuthApp,
    OAuthError,
    PendingLogin,
    PendingLogins,
    TokenSet,
    begin_code_login,
    begin_device_login,
    poll_device_login,
    redeem_code,
    refresh_tokens,
)

logger = logging.getLogger("brf.integrations.connections")

PROVIDER_GRAPH = graph_mod.PROVIDER
PROVIDER_FORTNOX = fortnox_mod.PROVIDER


class NotConnected(RuntimeError):
    """There is no usable connection for this provider, and the message says why."""


def _iso_at(epoch: float) -> str:
    """A unix instant as the ISO string the rest of the domain uses."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProviderRuntime:
    """Everything that differs between two providers, in one object.

    Written as data rather than as branches in the manager so that adding a
    third provider is a new entry here — and so the read-only egress policy,
    the scope list and the flow are declared next to each other where a
    reviewer can see all three at once.
    """

    provider: str
    policy: EgressPolicy
    login_kind: str  # "device" or "code"
    needs_client_secret: bool


RUNTIMES: dict[str, ProviderRuntime] = {
    PROVIDER_GRAPH: ProviderRuntime(
        provider=PROVIDER_GRAPH,
        policy=graph_mod.policy(),
        login_kind="device",
        needs_client_secret=False,
    ),
    PROVIDER_FORTNOX: ProviderRuntime(
        provider=PROVIDER_FORTNOX,
        policy=fortnox_mod.policy(),
        login_kind="code",
        needs_client_secret=True,
    ),
}


class ConnectionManager:
    """Configure, connect and use the live integrations for exactly one tenant."""

    def __init__(
        self,
        credentials: CredentialStore,
        *,
        pending: PendingLogins,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.credentials = credentials
        self.pending = pending
        self._transport = transport
        self._sleep = sleep

    # ---------- plumbing ----------

    def egress(self, provider: str) -> ReadOnlyEgress:
        runtime = RUNTIMES.get(provider)
        if runtime is None:
            raise NotConnected(f"Okänd leverantör: {provider!r}.")
        kwargs = {}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        if self._sleep is not None:
            kwargs["sleep"] = self._sleep
        return ReadOnlyEgress(policy=runtime.policy, **kwargs)

    def _oauth_app(self, connection: Connection, secrets: Secrets | None) -> OAuthApp:
        if connection.provider == PROVIDER_GRAPH:
            config = graph_mod.GraphConfig(
                client_id=connection.client_id,
                authority=connection.authority,
                mailbox=connection.mailbox,
                folder=connection.folder,
            ).validated()
            return OAuthApp(
                provider=PROVIDER_GRAPH,
                client_id=config.client_id,
                authority_base=f"https://{graph_mod.AUTHORITY_HOST}",
                authorize_path=config.authority_path("authorize"),
                token_path=config.authority_path("token"),
                device_code_path=config.authority_path("devicecode"),
                scopes=config.scopes(),
                use_pkce=True,
            )
        if connection.provider == PROVIDER_FORTNOX:
            config = fortnox_mod.FortnoxConfig(
                client_id=connection.client_id,
                redirect_uri=connection.redirect_uri,
                read_supplier_register=connection.read_supplier_register,
            ).validated()
            return OAuthApp(
                provider=PROVIDER_FORTNOX,
                client_id=config.client_id,
                client_secret=(secrets.client_secret if secrets else ""),
                authority_base=f"https://{fortnox_mod.AUTHORITY_HOST}",
                authorize_path=fortnox_mod.AUTHORIZE_PATH,
                token_path=fortnox_mod.TOKEN_PATH,
                scopes=config.scopes(),
                redirect_uri=config.redirect_uri,
                # Fortnox authenticates the client with HTTP Basic and does not
                # document PKCE. Sending an unrecognised code_challenge is a
                # good way to have an authorize request rejected for a reason
                # nobody can see, so it is off for this provider and on for the
                # public client where it is the actual protection.
                use_pkce=False,
                extra_authorize_params=(("access_type", "offline"), ("account_type", "service")),
            )
        raise NotConnected(f"Okänd leverantör: {connection.provider!r}.")

    # ---------- configure ----------

    def configure_graph(
        self, config: graph_mod.GraphConfig, *, user_id: str
    ) -> Connection:
        checked = config.validated()
        existing = self.credentials.get_connection(PROVIDER_GRAPH)
        changed = existing is None or (
            existing.client_id != checked.client_id
            or existing.authority != checked.authority
            or existing.mailbox != checked.mailbox
        )
        connection = Connection(
            provider=PROVIDER_GRAPH,
            tenant_id=self.credentials.tenant_id,
            status="configured" if changed else (existing.status if existing else "configured"),
            client_id=checked.client_id,
            authority=checked.authority,
            mailbox=checked.mailbox,
            folder=checked.folder,
            configured_by=user_id,
            configured_at=utc_now_iso(),
            account_label="" if changed else (existing.account_label if existing else ""),
            granted_scopes=[] if changed else (existing.granted_scopes if existing else []),
            connected_by="" if changed else (existing.connected_by if existing else ""),
            connected_at=None if changed else (existing.connected_at if existing else None),
        )
        if changed and existing is not None:
            # Pointing at a different app registration or mailbox invalidates
            # the sign-in that was made against the old one. Dropping the token
            # here means the UI cannot show "connected" next to a mailbox
            # nobody signed in to.
            self.credentials.forget(PROVIDER_GRAPH)
        return self.credentials.put_connection(connection)

    def configure_fortnox(
        self, config: fortnox_mod.FortnoxConfig, *, client_secret: str, user_id: str
    ) -> Connection:
        checked = config.validated()
        secret = client_secret.strip()
        existing = self.credentials.get_connection(PROVIDER_FORTNOX)
        stored = self.credentials.read_secrets(PROVIDER_FORTNOX)
        if not secret and not (stored and stored.client_secret):
            raise ConnectionError_(
                "Fortnox kräver en klienthemlighet från integrationen. Den lagras lokalt "
                "och lämnar aldrig den här datorn."
            )
        changed = existing is None or (
            existing.client_id != checked.client_id
            or existing.redirect_uri != checked.redirect_uri
            or existing.read_supplier_register != checked.read_supplier_register
            or bool(secret)
        )
        if changed and existing is not None:
            self.credentials.forget(PROVIDER_FORTNOX)
            stored = None
        self.credentials.write_secrets(
            PROVIDER_FORTNOX,
            Secrets(client_secret=secret or (stored.client_secret if stored else "")),
        )
        return self.credentials.put_connection(
            Connection(
                provider=PROVIDER_FORTNOX,
                tenant_id=self.credentials.tenant_id,
                status="configured" if changed else (existing.status if existing else "configured"),
                client_id=checked.client_id,
                redirect_uri=checked.redirect_uri,
                read_supplier_register=checked.read_supplier_register,
                configured_by=user_id,
                configured_at=utc_now_iso(),
                account_label="" if changed else (existing.account_label if existing else ""),
                granted_scopes=[] if changed else (existing.granted_scopes if existing else []),
                connected_by="" if changed else (existing.connected_by if existing else ""),
                connected_at=None if changed else (existing.connected_at if existing else None),
            )
        )

    # ---------- connect ----------

    def _require_configured(self, provider: str) -> Connection:
        connection = self.credentials.get_connection(provider)
        if connection is None:
            raise NotConnected(
                f"{provider} är inte konfigurerad. Ange app-registrering och brevlåda först."
            )
        return connection

    def begin_login(self, provider: str) -> PendingLogin:
        connection = self._require_configured(provider)
        secrets = self.credentials.read_secrets(provider)
        app = self._oauth_app(connection, secrets)
        runtime = RUNTIMES[provider]
        if runtime.login_kind == "device":
            pending = begin_device_login(
                self.egress(provider), app, tenant_id=self.credentials.tenant_id
            )
        else:
            pending = begin_code_login(app, tenant_id=self.credentials.tenant_id)
        return self.pending.start(pending)

    def complete_code_login(
        self, provider: str, *, code: str, state: str, user_id: str
    ) -> Connection:
        pending = self.pending.get(self.credentials.tenant_id, provider)
        if pending is None:
            raise OAuthError(
                "no_pending_login",
                "Ingen påbörjad inloggning, eller så har den gått ut. Starta om anslutningen.",
            )
        connection = self._require_configured(provider)
        app = self._oauth_app(connection, self.credentials.read_secrets(provider))
        tokens = redeem_code(self.egress(provider), app, pending, code=code, state=state)
        self.pending.clear(self.credentials.tenant_id, provider)
        return self._store_tokens(connection, tokens, user_id=user_id)

    def finish_device_login(self, provider: str, *, user_id: str) -> Connection | None:
        """:meth:`poll_login`, with the administrator recorded on success."""
        pending = self.pending.get(self.credentials.tenant_id, provider)
        if pending is None:
            raise OAuthError(
                "no_pending_login",
                "Ingen påbörjad inloggning, eller så har den gått ut. Starta om anslutningen.",
            )
        connection = self._require_configured(provider)
        app = self._oauth_app(connection, self.credentials.read_secrets(provider))
        tokens = poll_device_login(self.egress(provider), app, pending)
        if tokens is None:
            return None
        self.pending.clear(self.credentials.tenant_id, provider)
        return self._store_tokens(connection, tokens, user_id=user_id)

    def _store_tokens(
        self, connection: Connection, tokens: TokenSet, *, user_id: str
    ) -> Connection:
        # The client secret is read and written back in one locked step. Read
        # outside the lock, a disconnect landing in between would have this
        # write resurrect a secret file somebody had just removed.
        with self.credentials.lock:
            stored = self.credentials.read_secrets(connection.provider)
            self.credentials.write_secrets(
                connection.provider,
                Secrets(
                    access_token=tokens.access_token,
                    refresh_token=tokens.refresh_token,
                    client_secret=(stored.client_secret if stored else ""),
                    access_expires_epoch=tokens.expires_epoch,
                ),
            )
            updated = connection.model_copy(
                update={
                    "status": "connected",
                    "granted_scopes": tokens.granted_scopes,
                    "connected_by": user_id or connection.connected_by,
                    "connected_at": utc_now_iso(),
                    "access_expires_at": _iso_at(tokens.expires_epoch),
                    "last_error": None,
                }
            )
            updated = self.credentials.put_connection(updated)
        # The label is a nice-to-have that requires a live call, so it is taken
        # after the connection is already saved: failing to read a display name
        # must never lose a sign-in that succeeded.
        label = self._read_account_label(updated)
        if label:
            updated = self.credentials.put_connection(
                updated.model_copy(update={"account_label": label})
            )
        return updated

    def _read_account_label(self, connection: Connection) -> str:
        try:
            token = self.access_token(connection.provider)
            if connection.provider == PROVIDER_GRAPH:
                return self.graph_adapter(token=token).account_label()
            return self.fortnox_adapter(token=token).account_label()
        except Exception as exc:  # pragma: no cover - best effort by design
            logger.info("Kunde inte läsa kontonamn för %s: %s", connection.provider, exc)
            return ""

    def disconnect(self, provider: str) -> bool:
        """Forget the credentials. The configuration and the record of who
        connected it stay, because "this was connected and then disconnected"
        is a fact about the association's data that should survive."""
        self.pending.clear(self.credentials.tenant_id, provider)
        connection = self.credentials.get_connection(provider)
        removed = self.credentials.forget(provider)
        if connection is not None:
            self.credentials.put_connection(
                connection.model_copy(
                    update={
                        "status": "revoked",
                        "granted_scopes": [],
                        "access_expires_at": None,
                        "last_error": None,
                    }
                )
            )
        return removed

    # ---------- use ----------

    def access_token(self, provider: str) -> str:
        """A token that is valid right now, refreshing first if it is not.

        **One refresh at a time, per tenant and provider.** Two live calls whose
        tokens expire in the same minute — an invoice read and a mailbox fetch,
        which is exactly the pair an operator triggers together — would each see
        an expired token, and each would redeem the refresh token. Microsoft and
        Fortnox both *rotate* refresh tokens: redeeming one invalidates it. So
        the second refresh would present a token the authority had already
        retired, fail, and mark a perfectly good connection ``expired`` —
        sending an administrator to sign in again for no reason.

        The lock is held across the network call, which is deliberate and worth
        the cost. It is one short token request, it is the same lock the
        secrets file already uses, and serialising two refreshes is precisely
        the point: the second one arrives after the first has written, sees a
        token that is valid again, and returns it without asking the authority
        anything.
        """
        with self.credentials.lock:
            connection = self.credentials.get_connection(provider)
            if connection is None:
                raise NotConnected(f"{provider} är inte konfigurerad.")
            secrets = self.credentials.read_secrets(provider)
            if secrets is None or not secrets.access_token:
                raise NotConnected(
                    f"{provider} är inte ansluten. En administratör behöver logga in."
                )
            # Re-read under the lock: whoever held it before us may have just
            # refreshed, in which case there is nothing left to do.
            if secrets.access_expires_epoch > time.time():
                return secrets.access_token
            app = self._oauth_app(connection, secrets)
            try:
                tokens = refresh_tokens(
                    self.egress(provider), app, refresh_token=secrets.refresh_token
                )
            except OAuthError as exc:
                self.credentials.put_connection(
                    connection.model_copy(
                        update={"status": "expired", "last_error": exc.message}
                    )
                )
                raise NotConnected(exc.message) from exc
            self.credentials.write_secrets(
                provider,
                Secrets(
                    access_token=tokens.access_token,
                    refresh_token=tokens.refresh_token,
                    client_secret=secrets.client_secret,
                    access_expires_epoch=tokens.expires_epoch,
                ),
            )
            self.credentials.put_connection(
                connection.model_copy(
                    update={
                        "status": "connected",
                        "granted_scopes": tokens.granted_scopes or connection.granted_scopes,
                        "access_expires_at": _iso_at(tokens.expires_epoch),
                        "last_used_at": utc_now_iso(),
                        "last_error": None,
                    }
                )
            )
            return tokens.access_token

    def note_failure(self, provider: str, exc: Exception) -> None:
        """Record why a live call failed, so the UI can stop guessing.

        A 401 after a successful refresh means consent was withdrawn on the
        other side; anything else is left as an error the operator can retry.
        """
        connection = self.credentials.get_connection(provider)
        if connection is None:
            return
        status = "revoked" if isinstance(exc, RemoteError) and exc.status in (401, 403) else "error"
        self.credentials.put_connection(
            connection.model_copy(update={"status": status, "last_error": str(exc)[:300]})
        )

    # ---------- adapters ----------

    def graph_adapter(self, *, token: str | None = None) -> graph_mod.GraphMailAdapter:
        connection = self._require_configured(PROVIDER_GRAPH)
        return graph_mod.GraphMailAdapter(
            graph_mod.GraphConfig(
                client_id=connection.client_id,
                authority=connection.authority,
                mailbox=connection.mailbox,
                folder=connection.folder,
            ),
            access_token=token or self.access_token(PROVIDER_GRAPH),
            egress=self.egress(PROVIDER_GRAPH),
        )

    def fortnox_adapter(self, *, token: str | None = None) -> fortnox_mod.FortnoxAccountingAdapter:
        connection = self._require_configured(PROVIDER_FORTNOX)
        return fortnox_mod.FortnoxAccountingAdapter(
            fortnox_mod.FortnoxConfig(
                client_id=connection.client_id,
                redirect_uri=connection.redirect_uri,
                read_supplier_register=connection.read_supplier_register,
            ),
            access_token=token or self.access_token(PROVIDER_FORTNOX),
            egress=self.egress(PROVIDER_FORTNOX),
        )

    # ---------- status ----------

    def status(self) -> dict:
        """What the UI shows. Contains no secret, by construction of :class:`Connection`."""
        by_provider = {c.provider: c for c in self.credentials.list_connections()}
        out = {}
        for provider in (PROVIDER_GRAPH, PROVIDER_FORTNOX):
            connection = by_provider.get(provider)
            pending = self.pending.get(self.credentials.tenant_id, provider)
            out[provider] = {
                "provider": provider,
                "configured": connection is not None,
                "connection": connection.public() if connection else None,
                "pendingLogin": pending.public() if pending else None,
                "loginKind": RUNTIMES[provider].login_kind,
                "scopes": list(
                    graph_mod.READ_SCOPES
                    if provider == PROVIDER_GRAPH
                    else fortnox_mod.BASE_SCOPES
                ),
                "hosts": sorted(RUNTIMES[provider].policy.all_hosts()),
            }
        return out


__all__ = [
    "ConnectionManager",
    "NotConnected",
    "PROVIDER_FORTNOX",
    "PROVIDER_GRAPH",
    "ProviderRuntime",
    "RUNTIMES",
]
