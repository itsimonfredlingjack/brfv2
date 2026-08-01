"""Read-only Microsoft Graph mail: list a mailbox, fetch one message as MIME.

This is the live counterpart to :class:`~app.integrations.eml.EmlFileAdapter`,
and it deliberately produces the *same* artefact: the raw MIME bytes of one
message. Those bytes then go through :func:`app.integrations.eml.parse_eml` and
:func:`app.integrations.intake.import_eml` unchanged — the same format ceiling,
the same all-or-nothing attachment rule, the same content hash, the same
rollback. A live mailbox therefore cannot import anything the manual `.eml`
path would have refused, and there is exactly one importer to keep correct.

**Read-only is structural, not configured.** :data:`READ_SCOPES` is a constant
in this file. Nothing an operator can type — no settings field, no config file,
no restored backup — adds ``Mail.Send`` or ``Mail.ReadWrite`` to a token
request, because the scope list is not read from anywhere. The adapter's two
methods are ``list_messages`` and ``get_message_mime``; the read-only check in
:mod:`app.integrations.protocols` refuses a protocol that grows a third with a
writing verb, and there is no code path in this module that issues anything but
a GET (:mod:`app.integrations.egress` enforces that as well).

**Nothing is moved, marked or deleted.** Graph offers ``isRead``, ``move`` and
``delete``, and this product uses none of them: reading a message here does not
change the mailbox, so the board sees exactly what the mailbox owner sees. That
also means the same message can be imported twice — which is what the content
hash in the intake path is for.

**No sync.** No webhook subscription, no delta query, no polling loop, no
background thread. Every call in this module happens because a person clicked
something. A mailbox the product watches by itself is a different product with
a different consent conversation behind it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

from .egress import EgressPolicy, ReadOnlyEgress, read_json

logger = logging.getLogger("brf.integrations.graph")

PROVIDER = "microsoft-graph"

GRAPH_HOST = "graph.microsoft.com"
AUTHORITY_HOST = "login.microsoftonline.com"
GRAPH_BASE = f"https://{GRAPH_HOST}/v1.0"

# The complete set of scopes this product will ever ask Microsoft for.
#
#   offline_access   a refresh token, so an operator signs in once
#   User.Read        the signed-in account's own name, to show whose authority
#                    the reading happens under
#   Mail.Read        read messages and their attachments in that mailbox
#
# Mail.ReadBasic is deliberately not enough: it excludes the body and the
# attachments, which is the entire payload here. Mail.ReadWrite and Mail.Send
# are absent and unreachable — this tuple is the only thing the token request
# is built from.
READ_SCOPES: tuple[str, ...] = ("offline_access", "User.Read", "Mail.Read")
# Added only when a *shared* mailbox is configured. Still read-only.
SHARED_SCOPE = "Mail.Read.Shared"

# Well-known mail folders an operator may pick, plus the id shape Graph uses.
# A closed list rather than free text: the folder becomes a URL path segment.
WELL_KNOWN_FOLDERS = (
    "inbox",
    "archive",
    "junkemail",
    "sentitems",
    "drafts",
    "deleteditems",
)
_FOLDER_ID_RE = re.compile(r"^[A-Za-z0-9_=+/-]{20,512}$")
_MAILBOX_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def policy() -> EgressPolicy:
    return EgressPolicy(
        provider=PROVIDER,
        api_hosts=frozenset({GRAPH_HOST}),
        authority_host=AUTHORITY_HOST,
        token_paths=(
            "/common/oauth2/v2.0/token",
            "/consumers/oauth2/v2.0/token",
            "/organizations/oauth2/v2.0/token",
        ),
        login_paths=(
            "/common/oauth2/v2.0/devicecode",
            "/consumers/oauth2/v2.0/devicecode",
            "/organizations/oauth2/v2.0/devicecode",
        ),
    )


class GraphConfigError(ValueError):
    """The Graph configuration is not usable, and the message says why."""


@dataclass(frozen=True)
class GraphConfig:
    """What an installation needs to reach one mailbox.

    ``authority`` is the sign-in audience: ``consumers`` for a personal
    Microsoft account, ``organizations`` or a tenant GUID for a work account,
    ``common`` for either. It is *not* a free URL — see :func:`authority_path`.

    ``mailbox`` empty means the signed-in account's own mailbox. A value means
    a shared mailbox the account has been granted delegated access to, which is
    the shape a board actually wants: a ``styrelsen@``-address several people
    can read, rather than one member's private mail.
    """

    client_id: str
    authority: str = "consumers"
    mailbox: str = ""
    folder: str = "inbox"

    def validated(self) -> "GraphConfig":
        client_id = self.client_id.strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", client_id):
            raise GraphConfigError(
                "Klient-id ska vara app-registreringens GUID (36 tecken)."
            )
        authority = self.authority.strip().lower() or "consumers"
        if authority not in ("common", "consumers", "organizations") and not re.fullmatch(
            r"[0-9a-f-]{36}", authority
        ):
            raise GraphConfigError(
                "Katalog ska vara 'consumers', 'organizations', 'common' eller ett tenant-GUID."
            )
        mailbox = self.mailbox.strip().lower()
        if mailbox and not _MAILBOX_RE.fullmatch(mailbox):
            raise GraphConfigError("Brevlådan ska vara en e-postadress, eller lämnas tom.")
        folder = self.folder.strip() or "inbox"
        if folder.lower() not in WELL_KNOWN_FOLDERS and not _FOLDER_ID_RE.fullmatch(folder):
            raise GraphConfigError(
                "Mapp ska vara en känd mapp ("
                + ", ".join(WELL_KNOWN_FOLDERS)
                + ") eller ett mapp-id från Graph."
            )
        return GraphConfig(
            client_id=client_id, authority=authority, mailbox=mailbox, folder=folder
        )

    def scopes(self) -> tuple[str, ...]:
        """Read scopes, plus the shared-mailbox one only when one is configured."""
        return READ_SCOPES + ((SHARED_SCOPE,) if self.mailbox else ())

    def authority_path(self, endpoint: str) -> str:
        return f"/{self.authority}/oauth2/v2.0/{endpoint}"

    def mailbox_root(self) -> str:
        """The Graph path prefix for the mailbox being read."""
        if self.mailbox:
            return f"/users/{quote(self.mailbox, safe='@.')}"
        return "/me"

    def public(self) -> dict:
        return {
            "clientId": self.client_id,
            "authority": self.authority,
            "mailbox": self.mailbox,
            "folder": self.folder,
            "scopes": list(self.scopes()),
        }


@dataclass(frozen=True)
class MailboxMessage:
    """One row in the operator's picker. Never the body, never an attachment."""

    id: str
    subject: str
    from_address: str
    from_display: str
    received_at: str
    has_attachments: bool
    internet_message_id: str
    preview: str

    def public(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "from": self.from_address,
            "fromDisplay": self.from_display,
            "receivedAt": self.received_at,
            "hasAttachments": self.has_attachments,
            "internetMessageId": self.internet_message_id,
            "preview": self.preview,
        }


def _address(entry: Any) -> tuple[str, str]:
    if not isinstance(entry, dict):
        return "", ""
    inner = entry.get("emailAddress")
    if not isinstance(inner, dict):
        return "", ""
    return str(inner.get("address") or "").lower(), str(inner.get("name") or "")


class GraphMailAdapter:
    """Satisfies :class:`~app.integrations.protocols.MailboxReadAdapter`.

    Constructed per request with a live access token. It holds no credential of
    its own and has no way to obtain one — refreshing is the connection
    manager's job, so this class cannot keep using a token past its life.
    """

    name = PROVIDER

    def __init__(
        self,
        config: GraphConfig,
        *,
        access_token: str,
        egress: ReadOnlyEgress | None = None,
    ) -> None:
        self.config = config.validated()
        self._token = access_token
        self.egress = egress or ReadOnlyEgress(policy=policy())

    # ---------- reads ----------

    def account_label(self) -> str:
        """Whose authority this connection reads under.

        Shown in the UI beside the queue. A board looking at imported mail
        should be able to see which account it was read with without asking
        anyone, because that is the consent question in one line.
        """
        reply = self.egress.get(f"{GRAPH_BASE}/me?$select=displayName,userPrincipalName,mail", access_token=self._token)
        payload = read_json(reply, provider=PROVIDER)
        if not isinstance(payload, dict):
            return ""
        address = str(payload.get("mail") or payload.get("userPrincipalName") or "")
        name = str(payload.get("displayName") or "")
        if self.config.mailbox:
            return f"{self.config.mailbox} (läses av {address or name})"
        return f"{address or name}"

    def list_messages(
        self, *, limit: int = DEFAULT_PAGE_SIZE, only_with_attachments: bool = True
    ) -> list[MailboxMessage]:
        """The newest messages in the configured folder.

        ``$select`` is narrow on purpose: an id, who it is from, when it
        arrived, whether it has attachments and a short preview. The body is
        not requested, because listing a mailbox in order to choose one message
        does not require reading everyone's mail into this application's
        memory — and ``bodyPreview`` is what Outlook itself shows in a list.

        The attachment filter is applied here rather than as ``$filter``:
        Graph refuses several ``$filter``/``$orderby`` combinations on messages
        with "The restriction or sort order is too complex", and an operator
        browsing a mailbox should not meet that error because of a convenience.
        """
        size = max(1, min(int(limit), MAX_PAGE_SIZE))
        query = urlencode(
            {
                "$select": "id,subject,from,receivedDateTime,hasAttachments,internetMessageId,bodyPreview",
                "$top": str(size if not only_with_attachments else min(MAX_PAGE_SIZE, size * 3)),
                "$orderby": "receivedDateTime desc",
            }
        )
        folder = quote(self.config.folder, safe="")
        url = f"{GRAPH_BASE}{self.config.mailbox_root()}/mailFolders/{folder}/messages?{query}"
        payload = read_json(self.egress.get(url, access_token=self._token), provider=PROVIDER)
        rows: list[MailboxMessage] = []
        for entry in (payload or {}).get("value") or []:
            if not isinstance(entry, dict):
                continue
            has_attachments = bool(entry.get("hasAttachments"))
            if only_with_attachments and not has_attachments:
                continue
            address, display = _address(entry.get("from"))
            rows.append(
                MailboxMessage(
                    id=str(entry.get("id") or ""),
                    subject=str(entry.get("subject") or "(utan ämne)"),
                    from_address=address,
                    from_display=display,
                    received_at=str(entry.get("receivedDateTime") or ""),
                    has_attachments=has_attachments,
                    internet_message_id=str(entry.get("internetMessageId") or ""),
                    preview=str(entry.get("bodyPreview") or "")[:280],
                )
            )
            if len(rows) >= size:
                break
        return rows

    def get_message_mime(self, message_id: str) -> bytes:
        """The message exactly as it exists on the wire, for the `.eml` parser.

        ``/$value`` rather than reassembling from the JSON representation:
        anything this product built out of parsed fields would be a message it
        wrote, not the one that arrived, and the content hash that carries
        duplicate detection has to be over what actually came in.
        """
        ident = message_id.strip()
        if not ident:
            raise ValueError("Meddelande-id saknas.")
        url = f"{GRAPH_BASE}{self.config.mailbox_root()}/messages/{quote(ident, safe='')}/$value"
        reply = self.egress.get(url, access_token=self._token, accept="*/*")
        if not 200 <= reply.status < 300:
            read_json(reply, provider=PROVIDER)  # raises RemoteError with the detail
        return reply.content


__all__ = [
    "AUTHORITY_HOST",
    "DEFAULT_PAGE_SIZE",
    "GRAPH_BASE",
    "GRAPH_HOST",
    "GraphConfig",
    "GraphConfigError",
    "GraphMailAdapter",
    "MailboxMessage",
    "PROVIDER",
    "READ_SCOPES",
    "SHARED_SCOPE",
    "WELL_KNOWN_FOLDERS",
    "policy",
]
