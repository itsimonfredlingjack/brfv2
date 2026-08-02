"""Manual `.eml` intake — a small, stated format, and a refusal for everything else.

MIME is unbounded. A parser that tries to accept all of it ends up with an
implicit format nobody can write down, and an import that half-works is worse
than one that refuses: the operator believes the board has the attachment.

So this module states what it accepts, in one place, and refuses the rest with
a Swedish reason the operator can act on:

* the file must parse as a MIME message and carry ``From`` and ``Subject``;
* the whole file must be at most :data:`MAX_MESSAGE_BYTES`;
* there must be a readable body — ``text/plain``, or ``text/html`` which is
  reduced to text;
* at most :data:`MAX_ATTACHMENTS` attachments, each at most
  :data:`MAX_ATTACHMENT_BYTES`;
* **every** attachment must be ``application/pdf``. Not "PDFs are ingested and
  the rest is noted" — one unsupported attachment refuses the whole message,
  because an event that silently dropped a `.xlsx` is an event whose
  completeness cannot be trusted.

What counts as an attachment is decided by disposition, not by guessing: a part
is an attachment when ``Content-Disposition: attachment``, or when it carries a
filename and is not the body. An inline signature image with no filename is
message decoration and is neither ingested nor persisted.

Nothing here writes to the store. :func:`parse_eml` returns a
:class:`NormalizedMessage` or raises; the caller decides what to do with it,
which is what keeps the refusal atomic — see :mod:`app.integrations.intake`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

MAX_MESSAGE_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENTS = 10
MAX_BODY_CHARS = 200_000
# A long-running thread legitimately accumulates references, but the header is
# sender-controlled text that is only ever used for grouping — so it is bounded
# rather than trusted to be reasonable.
MAX_REFERENCES = 50

ACCEPTED_ATTACHMENT_TYPES = ("application/pdf",)
ACCEPTED_BODY_TYPES = ("text/plain", "text/html")

_PDF_MAGIC = b"%PDF-"

_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BREAKING_TAG = re.compile(r"</?(br|p|div|tr|li|h[1-6]|table)\b[^>]*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"\n{3,}")
# One ``<local@domain>`` identifier in a References/In-Reply-To header.
_REFERENCE_ID = re.compile(r"<[^<>\s]+>")


class EmlRejected(ValueError):
    """The file is outside the format this version accepts.

    Carries a stable ``code`` next to the Swedish message, so tests and evidence
    can assert *which* rule refused without matching on prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedAttachment:
    filename: str
    media_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class NormalizedMessage:
    """What one accepted `.eml` amounts to, before anything is stored."""

    message_id: str | None
    sender: str
    sender_display: str | None
    recipients: list[str]
    subject: str
    sent_at: str | None
    body_text: str
    attachments: list[ParsedAttachment] = field(default_factory=list)
    # The reply chain, straight out of the headers. Read for grouping only —
    # a sender writes these, so they are treated exactly like ``message_id``:
    # useful, never trusted. See app.integrations.threads.
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)


def accepted_format() -> dict:
    """The accepted format, machine-readable.

    Served to the UI and asserted by the tests, so the dialog that tells an
    operator what may be imported and the code that decides cannot drift apart.
    """
    return {
        "extension": ".eml",
        "maxMessageBytes": MAX_MESSAGE_BYTES,
        "maxAttachments": MAX_ATTACHMENTS,
        "maxAttachmentBytes": MAX_ATTACHMENT_BYTES,
        "bodyTypes": list(ACCEPTED_BODY_TYPES),
        "attachmentTypes": list(ACCEPTED_ATTACHMENT_TYPES),
        "requiredHeaders": ["From", "Subject"],
        "rejections": [
            {"code": "empty", "what": "Tom fil."},
            {"code": "too_large", "what": f"Filen är större än {MAX_MESSAGE_BYTES} byte."},
            {"code": "unparseable", "what": "Filen går inte att tolka som ett mejl."},
            {"code": "missing_header", "what": "Avsändare eller ämne saknas."},
            {"code": "no_readable_body", "what": "Ingen läsbar text i meddelandet."},
            {"code": "too_many_attachments", "what": f"Fler än {MAX_ATTACHMENTS} bilagor."},
            {"code": "attachment_too_large", "what": "En bilaga är för stor."},
            {"code": "unsupported_attachment", "what": "Bilaga som inte är PDF."},
            {"code": "attachment_unreadable", "what": "Bilagan går inte att läsa ur meddelandet."},
            {"code": "not_a_pdf", "what": "Bilagan säger PDF men innehållet är inte en PDF."},
        ],
    }


def _decode_header(value: object) -> str:
    return str(value or "").strip()


def _addresses(message: EmailMessage, header: str) -> list[str]:
    raw = message.get_all(header, [])
    return [addr.lower() for _, addr in getaddresses([str(v) for v in raw]) if addr]


def _html_to_text(html: str) -> str:
    """Reduce HTML to something a human can read in a queue.

    Not a renderer and not sanitisation for display — the result is stored as
    plain text and never returned as markup. Script and style bodies are dropped
    entirely (their contents are not prose), block-level tags become newlines so
    a table of amounts does not collapse into one line, and the remainder is
    unescaped.
    """
    import html as html_mod

    text = _SCRIPT_OR_STYLE.sub(" ", html)
    text = _BREAKING_TAG.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html_mod.unescape(text)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()


def _is_attachment(part: EmailMessage) -> bool:
    if part.get_content_disposition() == "attachment":
        return True
    filename = part.get_filename()
    return bool(filename) and part.get_content_type() not in ACCEPTED_BODY_TYPES


def _body_text(message: EmailMessage) -> str:
    """The message body, preferring plain text over reduced HTML."""
    plain = message.get_body(preferencelist=("plain",))
    if plain is not None:
        try:
            return str(plain.get_content()).strip()
        except (LookupError, UnicodeDecodeError):
            pass
    html_part = message.get_body(preferencelist=("html",))
    if html_part is not None:
        try:
            return _html_to_text(str(html_part.get_content()))
        except (LookupError, UnicodeDecodeError):
            pass
    # get_body() declines when every part is an attachment or the structure is
    # unusual; walk for a text part before giving up.
    for part in message.walk():
        if part.get_content_type() == "text/plain" and not _is_attachment(part):
            try:
                return str(part.get_content()).strip()
            except (LookupError, UnicodeDecodeError):
                continue
    return ""


def parse_eml(raw: bytes, *, filename: str = "meddelande.eml") -> NormalizedMessage:
    """Parse and validate one `.eml`. Raises :class:`EmlRejected` for anything else."""

    if not raw:
        raise EmlRejected("empty", "Filen är tom.")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise EmlRejected(
            "too_large",
            f"Filen är {len(raw)} byte — högst {MAX_MESSAGE_BYTES} byte tas emot.",
        )

    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:  # the stdlib parser raises a wide range here
        raise EmlRejected("unparseable", f"Filen går inte att tolka som ett mejl: {exc}") from exc

    if not isinstance(message, EmailMessage):  # pragma: no cover - policy.default guarantees it
        raise EmlRejected("unparseable", "Filen går inte att tolka som ett mejl.")

    senders = _addresses(message, "From")
    subject = _decode_header(message.get("Subject"))
    if not senders:
        raise EmlRejected("missing_header", "Meddelandet saknar avsändare (From).")
    if not subject:
        raise EmlRejected("missing_header", "Meddelandet saknar ämne (Subject).")

    display = None
    from_raw = _decode_header(message.get("From"))
    named = getaddresses([from_raw])
    if named and named[0][0]:
        display = named[0][0].strip()

    sent_at = None
    date_header = message.get("Date")
    if date_header is not None:
        try:
            sent_at = parsedate_to_datetime(str(date_header)).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            # A malformed Date is not a reason to refuse a message: the
            # received-at stamp is ours and always exists. The source time is
            # simply unknown, and unknown is a value the domain has.
            sent_at = None

    attachments: list[ParsedAttachment] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart" or not _is_attachment(part):
            continue
        media_type = part.get_content_type()
        name = part.get_filename() or "bilaga"
        if media_type not in ACCEPTED_ATTACHMENT_TYPES:
            raise EmlRejected(
                "unsupported_attachment",
                f"Bilagan {name!r} är {media_type}. Den här versionen tar bara emot "
                f"{', '.join(ACCEPTED_ATTACHMENT_TYPES)} — meddelandet importeras inte alls, "
                "så ingenting halvimporteras.",
            )
        try:
            data = part.get_payload(decode=True)
        except Exception as exc:
            raise EmlRejected(
                "attachment_unreadable", f"Bilagan {name!r} går inte att läsa: {exc}"
            ) from exc
        if not data:
            raise EmlRejected("attachment_unreadable", f"Bilagan {name!r} är tom.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise EmlRejected(
                "attachment_too_large",
                f"Bilagan {name!r} är {len(data)} byte — högst {MAX_ATTACHMENT_BYTES} byte.",
            )
        if not data.startswith(_PDF_MAGIC):
            # A declared content type is a claim by the sender. The board is
            # going to be shown this as a document; check the bytes.
            raise EmlRejected(
                "not_a_pdf",
                f"Bilagan {name!r} anges som PDF men innehållet börjar inte med %PDF-.",
            )
        attachments.append(ParsedAttachment(filename=name, media_type=media_type, data=data))
        if len(attachments) > MAX_ATTACHMENTS:
            raise EmlRejected(
                "too_many_attachments",
                f"Meddelandet har fler än {MAX_ATTACHMENTS} bilagor.",
            )

    body = _body_text(message)
    if not body and not attachments:
        raise EmlRejected(
            "no_readable_body",
            "Meddelandet har varken läsbar text eller bilagor.",
        )
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n\n[…texten är avkortad vid import…]"

    message_id = _decode_header(message.get("Message-ID")) or None

    return NormalizedMessage(
        message_id=message_id,
        sender=senders[0],
        sender_display=display,
        recipients=_addresses(message, "To") + _addresses(message, "Cc"),
        subject=subject,
        sent_at=sent_at,
        body_text=body,
        attachments=attachments,
        in_reply_to=_decode_header(message.get("In-Reply-To")) or None,
        references=_message_ids(_decode_header(message.get("References"))),
    )


def _message_ids(header: str) -> list[str]:
    """The ``<...>`` tokens in a References header, in order, deduplicated.

    Whitespace-splitting is not enough: the header is folded across lines by
    every mail system that touches it, and a malformed one is common enough
    that refusing a message over it would be refusing ordinary mail. Anything
    that is not a bracketed identifier is simply not a reference.
    """
    seen: list[str] = []
    for token in _REFERENCE_ID.findall(header or ""):
        if token not in seen:
            seen.append(token)
    return seen[:MAX_REFERENCES]


class EmlFileAdapter:
    """The one :class:`~app.integrations.protocols.MailImportAdapter` this block ships.

    It reads a file the operator picked. It has no mailbox, no credential, no
    folder and no schedule — which is the whole point of calling it a *file*
    adapter rather than a mail adapter.
    """

    name = "eml-file"

    def parse_message(self, raw: bytes, *, filename: str) -> NormalizedMessage:
        return parse_eml(raw, filename=filename)
