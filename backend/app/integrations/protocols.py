"""Adapter boundaries — and the reason none of them can write.

This product sits *beside* the systems a board already uses. It reads from them
so it can compare, cite and ask a human. It does not send mail, archive
messages, book entries, attest invoices or move money, and the way to keep that
true over time is not to remember it.

:func:`assert_read_only` walks a protocol's members and raises at **import
time** if any of them is named like an outward write. Adding
``def send_reply(...)`` to :class:`MailImportAdapter` does not produce a review
comment six weeks later; it produces an ImportError the first time anything in
this package is imported, including every test run.

The check is on names, which is a real limitation and stated as one: a method
called ``fetch`` that happens to POST would pass it. It is a tripwire against
the drift that actually happens — someone extends an adapter because the data
is right there — not a proof of network behaviour. The proof that no write
*endpoint* exists is that no adapter in this package constructs a request with
a method other than GET, which the tests assert separately.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import InvoiceSnapshot


class ReadOnlyAdapterError(TypeError):
    """An adapter protocol declared a method that would write to a foreign system."""


# The first snake_case token of a method name. `list_invoices` → `list` (fine);
# `send_reply` → `send` (refused). Chosen over substring matching so that
# `get_invoice` is not refused for containing "et", and over an allowlist so
# that a genuinely new *read* verb does not require editing this file.
FORBIDDEN_METHOD_STEMS = frozenset(
    {
        "acknowledge",
        "add",
        "approve",
        "archive",
        "attest",
        "book",
        "bookkeep",
        "cancel",
        "clear",
        "close",
        "create",
        "delete",
        "deliver",
        "destroy",
        "edit",
        "flag",
        "forward",
        "insert",
        "mark",
        "modify",
        "move",
        "patch",
        "pay",
        "post",
        "publish",
        "purge",
        "push",
        "put",
        "register",
        "remove",
        "reply",
        "reset",
        "save",
        "send",
        "set",
        "settle",
        "submit",
        "sync",
        "trash",
        "unsend",
        "update",
        "upload",
        "void",
        "write",
    }
)


def _declared_methods(protocol: type) -> list[str]:
    """Method names the protocol itself declares, excluding typing machinery."""
    own = set(vars(protocol))
    return sorted(
        name
        for name in own
        if not name.startswith("_") and callable(getattr(protocol, name, None))
    )


def assert_read_only(protocol: type) -> type:
    """Refuse a protocol carrying an outward-write method. Returns it unchanged."""
    for name in _declared_methods(protocol):
        stem = name.split("_", 1)[0]
        if stem in FORBIDDEN_METHOD_STEMS:
            raise ReadOnlyAdapterError(
                f"{protocol.__name__}.{name}: '{stem}' är en skrivande verb-stam. "
                "Adaptrar i det här blocket får bara läsa och importera — inte "
                "skicka, arkivera, uppdatera, bokföra, attestera eller betala."
            )
    return protocol


@runtime_checkable
class MailImportAdapter(Protocol):
    """Turn one bounded message into normalised material.

    The adapter does not decide anything. It parses, validates and hands back a
    :class:`~app.integrations.eml.NormalizedMessage`; whether that becomes a
    ``SourceEvent`` — and whether its attachments are ingested — is the
    importer's call, made inside the tenant's own store.

    There is no ``list_messages`` here, because a file adapter has nothing to
    list — the operator chose the file. Listing a *mailbox* is
    :class:`MailboxReadAdapter`, and the distinction is the point: this
    protocol cannot reach a mailbox at all, so the manual path stays available,
    unchanged and credential-free even on an installation that has connected
    one.
    """

    name: str

    def parse_message(self, raw: bytes, *, filename: str) -> object:
        """Parse and validate ``raw``. Raise on anything outside the accepted format."""
        ...


@runtime_checkable
class MailboxReadAdapter(Protocol):
    """Read a connected mailbox: list what is there, fetch one message's MIME.

    Added when the live Microsoft Graph integration replaced the fixture-only
    path. An earlier version of this file argued that no mailbox listing should
    exist because "a mailbox listing is the first step of continuous sync". The
    first half of that was wrong and the second half was the real point, so the
    rule is now stated as what it always meant:

        **Every read happens because a person asked for it.**

    There is no polling loop, no webhook subscription, no delta token and no
    background thread anywhere in this package, and the test suite asserts
    that. What an operator gets is a list they asked to see and a message they
    chose to import — which is the same shape as picking a file, with the
    file-picking step done against the mailbox instead of the filesystem.

    ``get_message_mime`` returns the message exactly as it exists on the wire,
    so it can go through the same parser and the same atomic importer as a
    manually exported `.eml`. Nothing here marks a message read, moves it,
    replies to it or deletes it: the verb check below would refuse a method
    named for any of those, and the adapter issues nothing but GETs.
    """

    name: str

    def list_messages(self, *, limit: int, only_with_attachments: bool) -> list:
        """Recent messages in the configured folder. Headers only, never bodies."""
        ...

    def get_message_mime(self, message_id: str) -> bytes:
        """One message's raw MIME, for the ordinary `.eml` import path."""
        ...

    def account_label(self) -> str:
        """Whose authority this connection reads under, for the operator to see."""
        ...


@runtime_checkable
class AccountingReadAdapter(Protocol):
    """Read invoices out of an accounting system that this product does not own."""

    name: str

    def list_invoices(self, tenant_id: str) -> list[dict]:
        """Lightweight rows for a picker: external_ref, supplier, date, total."""
        ...

    def get_invoice(self, tenant_id: str, external_ref: str) -> InvoiceSnapshot:
        """One full snapshot. Raises LookupError when the reference is unknown."""
        ...


# Enforced here, at import, for every protocol this module defines. A new
# adapter protocol that is not passed through this call is the one hole in the
# scheme, so the test suite asserts that every Protocol in this module is.
assert_read_only(MailImportAdapter)
assert_read_only(MailboxReadAdapter)
assert_read_only(AccountingReadAdapter)
