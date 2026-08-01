"""Where an integration's credentials live, and where they deliberately do not.

Two records per connected provider, kept apart on purpose:

* :class:`Connection` — everything the UI, the API and a support conversation
  may see: which account, which scopes, who connected it and when, when the
  access token expires. No secret is in this type, so no route has to remember
  to strip one.
* the **secret file** — the access token, the refresh token and, for a
  provider that requires a confidential client, its client secret. Read only
  by the module that needs to sign a request.

Both live in the tenant's own ``integrations/`` directory, which is what makes
tenant isolation inherited rather than argued: ``registry.delete()`` sweeps a
tenant's credentials with everything else, and no code had to remember they
existed. The secret file is ``0600`` inside a ``0700`` directory.

**Backups do not carry credentials.** ``app.desktop.create_backup`` skips
:data:`SECRET_DIRNAME` by name, so a backup archive — the artefact most likely
to be copied to a USB stick, mailed to a consultant or restored on a different
machine — contains connection metadata and no token. The consequence is stated
rather than hidden: after a restore, the integrations are listed as connected
but unusable, and an administrator signs in again. That is the right way round.
A refresh token in an archive nobody treats as a secret is a standing grant to
read a mailbox, and it outlives every conversation about who was allowed to.

There is no encryption layer here, and that is a decision rather than an
omission. A key stored beside its ciphertext protects against exactly one
thing — someone reading the file without being able to read the key — and on a
single-user desktop installation the key would have to sit in the same home
directory, under the same permissions, as the file it protects. What actually
keeps these bytes safe is the filesystem mode, which is the same protection
``auth.db`` gets for password hashes and live sessions. Rolling a cipher to
make that look stronger than it is would be worse than saying it plainly.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .models import utc_now_iso

logger = logging.getLogger("brf.integrations.credentials")

SECRET_DIRNAME = "credentials"
CONNECTIONS_FILE = "connections.json"

ProviderId = Literal["microsoft-graph", "fortnox"]
PROVIDER_IDS: tuple[str, ...] = ("microsoft-graph", "fortnox")

# "configured" is a real state and not a placeholder: an administrator saves
# which app registration and which mailbox this installation will use, and only
# then — possibly on another day, possibly by another person — signs in. Folding
# the two into one step would mean either storing configuration nobody has
# agreed to yet, or asking for credentials before anyone knows where they point.
ConnectionStatus = Literal["configured", "connected", "expired", "revoked", "error"]


class ConnectionError_(RuntimeError):
    """The connection cannot be used, and the message says what to do about it."""


class Connection(BaseModel):
    """A live, human-authorised link to one external system. No secrets here."""

    provider: str
    tenant_id: str

    status: ConnectionStatus = "configured"
    # What the remote system calls the identity that authorised this. A
    # mailbox address, a Fortnox company name — shown so a board can see whose
    # authority the reading happens under, which is the question that actually
    # matters when a queue shows someone's mail.
    account_label: str = ""
    # Exactly the scopes the token carries, as the authority reported them
    # back — not what we asked for. The two differ often enough that recording
    # the request would be recording an intention.
    granted_scopes: list[str] = Field(default_factory=list)

    # Non-secret configuration this connection was made with, so a support
    # question can be answered without opening the secret file.
    client_id: str = ""
    authority: str = ""
    mailbox: str = ""
    folder: str = ""
    redirect_uri: str = ""
    read_supplier_register: bool = False

    configured_by: str = ""
    configured_at: str | None = None
    connected_by: str = ""
    connected_at: str | None = None
    access_expires_at: str | None = None
    last_used_at: str | None = None
    last_error: str | None = None

    def public(self) -> dict:
        return self.model_dump(mode="json")


class Secrets(BaseModel):
    """The part that never leaves this process except as an Authorization header."""

    access_token: str = ""
    refresh_token: str = ""
    client_secret: str = ""
    # Unix seconds. Compared against time.time() rather than parsed from the
    # ISO string on the Connection, so a clock format change cannot silently
    # make every token look fresh.
    access_expires_epoch: float = 0.0


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class CredentialStore:
    """Connections and secrets for exactly one tenant."""

    def __init__(self, base_dir: str | Path, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.dir = Path(base_dir)
        self.secret_dir = self.dir / SECRET_DIRNAME
        self.lock = threading.RLock()

    # ---------- connections (public) ----------

    def _read_connections(self) -> list[Connection]:
        path = self.dir / CONNECTIONS_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectionError_(f"{path} går inte att läsa: {exc}") from exc
        rows: list[Connection] = []
        for entry in raw if isinstance(raw, list) else []:
            record = Connection.model_validate(entry)
            if record.tenant_id != self.tenant_id:
                raise ConnectionError_(
                    f"{path} innehåller en anslutning för {record.tenant_id!r} i "
                    f"{self.tenant_id!r}s katalog."
                )
            rows.append(record)
        return rows

    def list_connections(self) -> list[Connection]:
        with self.lock:
            return sorted(self._read_connections(), key=lambda c: c.provider)

    def get_connection(self, provider: str) -> Connection | None:
        return next((c for c in self.list_connections() if c.provider == provider), None)

    def put_connection(self, connection: Connection) -> Connection:
        with self.lock:
            record = connection.model_copy(update={"tenant_id": self.tenant_id})
            rows = [c for c in self._read_connections() if c.provider != record.provider]
            rows.append(record)
            _atomic_write_json(
                self.dir / CONNECTIONS_FILE, [c.model_dump(mode="json") for c in rows]
            )
        return record

    # ---------- secrets ----------

    def _secret_path(self, provider: str) -> Path:
        if provider not in PROVIDER_IDS:
            raise ConnectionError_(f"Okänd leverantör: {provider!r}.")
        return self.secret_dir / f"{provider}.json"

    def read_secrets(self, provider: str) -> Secrets | None:
        path = self._secret_path(provider)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt secret file must not read as "no credentials" — that
            # would silently downgrade a connected integration to a login
            # prompt and invite someone to paste a fresh token over a file
            # nobody looked at.
            raise ConnectionError_(
                f"Hemligheterna för {provider} går inte att läsa ({exc}). Undersök "
                f"{path} manuellt eller koppla bort och anslut igen."
            ) from exc
        return Secrets.model_validate(raw)

    def write_secrets(self, provider: str, secrets: Secrets) -> None:
        path = self._secret_path(provider)
        self.secret_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.secret_dir, 0o700)
        except OSError:  # pragma: no cover - a filesystem that will not take the mode
            logger.debug("Kunde inte sätta 0700 på %s", self.secret_dir)
        with self.lock:
            _atomic_write_json(path, secrets.model_dump(mode="json"))

    def forget(self, provider: str) -> bool:
        """Disconnect: remove the secrets first, then the connection record.

        That order matters. If the process dies between the two, what is left
        is a connection the UI shows as broken — not a secret file with no
        record that anything is using it.
        """
        removed = False
        with self.lock:
            path = self._secret_path(provider)
            if path.exists():
                path.unlink()
                removed = True
            rows = [c for c in self._read_connections() if c.provider != provider]
            _atomic_write_json(
                self.dir / CONNECTIONS_FILE, [c.model_dump(mode="json") for c in rows]
            )
        return removed


__all__ = [
    "CONNECTIONS_FILE",
    "Connection",
    "ConnectionError_",
    "CredentialStore",
    "PROVIDER_IDS",
    "SECRET_DIRNAME",
    "Secrets",
]
