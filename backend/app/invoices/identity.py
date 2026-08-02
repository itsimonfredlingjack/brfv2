"""Which observations are the same invoice, and which are only near each other.

A real invoice can be seen three ways: read out of the accounting system, sent
as a PDF attached to a mail, and preserved as a document in the archive. The
product's job is to converge those on **one** case where it can say why, and to
refuse to merge them where it cannot.

The refusal half is the load-bearing one. Two competing records for one invoice
is a nuisance; one record that silently merged two different invoices from the
same supplier is a wrong number in front of a board. So identity here is
deterministic, conservative, and always carries the sentence it was decided on:

* **Supplier and invoice number.** Two readings that agree on both are the same
  invoice. This is what makes the same invoice read from the fixture set and
  from Fortnox land on one case instead of two.
* **Otherwise, the source's own reference.** An invoice with no number gets a
  case keyed on ``adapter:external_ref``, which is unique per source and merges
  with nothing. That is the honest outcome: we cannot tell, so we do not claim.

Attaching a *mail* to a case is a separate and stricter question, because an
email is attacker-controlled text. It is attached only when the invoice was
literally read out of it, or when the message writes the invoice number
verbatim **and** independently names the supplier. Anything weaker is left
unattached rather than recorded as a link somebody might act on.
"""

from __future__ import annotations

import re

from ..integrations.models import InvoiceSnapshot, SourceEvent
from ..integrations.supplier import core_tokens, is_distinctive, normalize, tokens_of

# Below this, an "invoice number" is too short to be evidence of anything. "12"
# appears in every other sentence of a mail; "2026-131" does not.
MIN_NUMBER_LENGTH = 4

_NON_ALNUM = re.compile(r"[^0-9a-zA-ZåäöÅÄÖ]+")


def number_key(value: str | None) -> str:
    """An invoice number reduced to what is stable about it.

    ``2026-131``, ``2026/131`` and ``2026 131`` are one number written three
    ways. Separators are dropped and case is folded; nothing else is, so
    ``2026-131`` and ``2026-1310`` stay different.
    """
    return _NON_ALNUM.sub("", (value or "")).lower()


def case_key_for(snapshot: InvoiceSnapshot) -> tuple[str, str]:
    """``(case key, why)`` for one snapshot.

    Never raises and never returns an empty key: an invoice with neither a
    supplier nor a number still gets a case of its own, because the alternative
    is dropping it.
    """
    supplier = normalize(snapshot.supplier_name)
    number = number_key(snapshot.invoice_number)
    if supplier and len(number) >= MIN_NUMBER_LENGTH:
        return (
            f"{supplier}#{number}",
            (
                f"Leverantör ({snapshot.supplier_name}) och fakturanummer "
                f"({snapshot.invoice_number}) är båda kända, så varje läsning av den här "
                "fakturan hamnar på samma ärende."
            ),
        )
    reason = (
        "Fakturan saknar fakturanummer"
        if not number
        else "Fakturan saknar läsbart leverantörsnamn"
    )
    return (
        f"{snapshot.adapter}:{snapshot.external_ref}",
        (
            f"{reason}, så ärendet är knutet till källans egen referens "
            f"({snapshot.adapter} {snapshot.external_ref}) och slås inte ihop med något annat."
        ),
    )


def _haystack(event: SourceEvent) -> str:
    parts = [event.subject or "", event.body_text or ""]
    parts.extend(a.filename for a in event.attachments)
    return _NON_ALNUM.sub("", " ".join(parts)).lower()


def _names_supplier(event: SourceEvent, supplier_name: str) -> bool:
    """Does the message independently point at this supplier?

    Independently means: not from the invoice we are trying to attach it to.
    The sender address, the display name, the subject, the body, and — when the
    triage read one — the supplier it read. A distinctive token has to match;
    "AB" and "Svenska" name nobody.
    """
    distinctive = {t for t in core_tokens(supplier_name) if is_distinctive(t)}
    if not distinctive:
        return False
    if event.triage is not None and event.triage.supplier_name:
        if normalize(event.triage.supplier_name) == normalize(supplier_name):
            return True
    text = " ".join(
        [
            event.origin or "",
            event.origin_display or "",
            event.subject or "",
            event.body_text or "",
        ]
    )
    words: set[str] = set()
    for raw in re.split(r"[\s@.<>_/\\-]+", text):
        words.update(tokens_of(raw))
    return bool(distinctive & words)


def email_basis(
    event: SourceEvent, snapshot: InvoiceSnapshot
) -> str | None:
    """Why this message belongs to this invoice's case, or ``None``.

    Two ways in, and no third:

    1. the invoice was read out of this very message
       (``InvoiceSnapshot.source_event_id``);
    2. the message writes the invoice number verbatim **and** names the
       supplier by something distinctive.

    A message that merely arrived from the same supplier around the same time
    is not attached. It may well be the covering mail — but "may well be" is
    the kind of link that ends up quoted back as though somebody checked it.
    """
    if snapshot.source_event_id and snapshot.source_event_id == event.id:
        return "Fakturan lästes in ur det här meddelandet."
    number = number_key(snapshot.invoice_number)
    if len(number) < MIN_NUMBER_LENGTH:
        return None
    if number not in _haystack(event):
        # The source system's own reference is worth a second try: a mail
        # frequently quotes "SI-2026-131" where the invoice's own number field
        # says "2026-131".
        external = number_key(snapshot.external_ref)
        if len(external) < MIN_NUMBER_LENGTH or external not in _haystack(event):
            return None
        number = external
    if not _names_supplier(event, snapshot.supplier_name):
        return None
    return (
        f"Meddelandet skriver fakturanumret {snapshot.invoice_number or snapshot.external_ref} "
        f"ordagrant och namnger {snapshot.supplier_name}."
    )


__all__ = ["MIN_NUMBER_LENGTH", "case_key_for", "email_basis", "number_key"]
