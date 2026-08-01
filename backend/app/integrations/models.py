"""The three domain records, and nothing that names a vendor.

Amounts are :class:`~decimal.Decimal`, never float. An invoice total is money
someone will be asked about; ``12500.10 != 12500.099999999999`` matters when a
comparison decides whether a finding says "överensstämmer" or "möjlig
avvikelse". Pydantic serialises ``Decimal`` as a JSON *string*, which is also
what keeps the value exact across the HTTP boundary and back out of disk.

Timestamps are ISO-8601 strings with an explicit offset, produced by
:func:`utc_now_iso`. They are stored as text because that is what the rest of
this backend does (``DocumentMeta.uploaded_at``), and a second convention would
only create a second thing to get wrong.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CitationOut

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# What kind of thing arrived. Deliberately about the *shape* of the source, not
# the product that produced it: an .eml exported from any mail client is
# "email", and a future mailbox adapter adds no member here.
SourceType = Literal["email"]
SOURCE_TYPES: tuple[SourceType, ...] = ("email",)

# Did the import land? There is no "partial": an import either produced a
# complete SourceEvent with every attachment accounted for, or it was refused
# and nothing was written. See app.integrations.eml for why.
ImportStatus = Literal["imported", "rejected"]

# Where a source event stands in the human queue.
ReviewStatus = Literal["open", "approved", "dismissed", "corrected"]

# Where a finding stands. Same words as ReviewStatus on purpose — a reviewer
# does the same four things to both, and two vocabularies for one gesture is
# how UIs start disagreeing with their backend.
FindingStatus = Literal["open", "approved", "dismissed", "corrected"]

FindingType = Literal[
    # An invoice amount was compared against a cited contract term.
    "invoice_contract_amount",
    # An invoice period was compared against a cited contract period.
    "invoice_contract_period",
    # No candidate contract passage could be verified for this invoice at all.
    "invoice_without_contract",
]

# The three answers this product is allowed to give. There is no fourth, and in
# particular there is no "avviker" — asserting a deviation as fact would claim
# the contract says something it may simply not say on the page that was found.
#
#   matches               a verbatim-verified contract passage carries a value
#                         that equals the invoice's
#   possible_deviation    a verbatim-verified passage carries a comparable
#                         value, and it differs
#   cannot_be_verified    nothing comparable was verified — the honest answer,
#                         and the default whenever verification fails
Verdict = Literal["matches", "possible_deviation", "cannot_be_verified"]

VERDICT_LABELS: dict[str, str] = {
    "matches": "överensstämmer",
    "possible_deviation": "möjlig avvikelse",
    "cannot_be_verified": "kan inte verifieras",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# SourceEvent
# ---------------------------------------------------------------------------


class Attachment(BaseModel):
    """One file that arrived with a source event.

    ``document_id`` is the link into the tenant's ordinary document store: an
    ingested PDF is a normal document, indexed and citable exactly like an
    uploaded one. There is no second ingestion path and no second place
    document bytes live — which is also why deleting the tenant deletes these.
    """

    id: str
    filename: str
    media_type: str
    bytes: int
    sha256: str
    # Set when the attachment went through Store.add_document(); None when the
    # format is one this version accepts but does not ingest.
    document_id: str | None = None
    ingested: bool = False
    # True when these exact bytes had already arrived on an earlier event and
    # the existing document was linked instead of ingesting a second copy.
    # The pilot journal recorded the product accepting five bit-identical
    # duplicates "utan varning eller dedupliceringsfråga"; a queue that
    # forwards the same defect into the document archive is worse, because the
    # copies then compete in retrieval.
    reused_existing_document: bool = False


class Provenance(BaseModel):
    """How this record came to exist, in enough detail to re-derive it.

    ``method`` says which code path produced the event, ``origin_filename`` and
    ``origin_bytes`` describe the artefact the operator actually picked, and
    ``imported_by`` names the account that took responsibility for pointing at
    it. Together they answer "where did this come from" without needing the
    original file to still be on disk.
    """

    method: str
    adapter: str
    origin_filename: str
    origin_bytes: int
    imported_by: str
    imported_at: str = Field(default_factory=utc_now_iso)


class SourceEvent(BaseModel):
    """Something that arrived and may deserve the board's attention."""

    id: str
    tenant_id: str
    source_type: SourceType

    # When we took it in, and when the source says it happened. They are
    # different questions and a mail imported six weeks late must not look
    # like it arrived today.
    received_at: str
    occurred_at: str | None = None

    # The source system's own identifier, when it has one (Message-ID for
    # mail). Used for duplicate detection alongside the content hash, never as
    # a trust anchor — it is attacker-controlled text.
    external_ref: str | None = None

    # SHA-256 of the original bytes exactly as they were handed to us. This is
    # the duplicate check that actually holds, and the value that lets someone
    # later ask "is this the same message I was shown".
    content_sha256: str

    provenance: Provenance

    # Who or what it came from, and what it says it is about.
    origin: str
    origin_display: str | None = None
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body_text: str = ""

    attachments: list[Attachment] = Field(default_factory=list)

    import_status: ImportStatus = "imported"
    review_status: ReviewStatus = "open"
    error: str | None = None

    # Documents a human has confirmed this event belongs with, and documents
    # the system proposes. Kept apart on purpose: the first is a decision, the
    # second is a guess, and a queue that blends them teaches its users to
    # trust guesses.
    linked_document_ids: list[str] = Field(default_factory=list)
    suggested_document_ids: list[str] = Field(default_factory=list)

    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None


# ---------------------------------------------------------------------------
# InvoiceSnapshot
# ---------------------------------------------------------------------------


class InvoiceLine(BaseModel):
    description: str = ""
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    vat_amount: Decimal | None = None


class InvoiceSnapshot(BaseModel):
    """A read-only picture of an invoice in someone else's system.

    Deliberately absent: any bookkeeping, approval or payment status this
    application could change. The snapshot may record what the source system
    said, but there is no field here that this product owns, because there is
    no code path in this product that may write one back.
    """

    id: str
    tenant_id: str

    # Which adapter produced this and what it called the record over there.
    adapter: str
    external_ref: str

    supplier_name: str
    supplier_ref: str | None = None

    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None

    total_amount: Decimal | None = None
    currency: str = "SEK"
    vat_amount: Decimal | None = None
    lines: list[InvoiceLine] = Field(default_factory=list)

    # Provenance of the snapshot itself: what was read, when, and the hash of
    # the exact payload it was derived from.
    retrieved_at: str
    source_dataset: str
    content_sha256: str

    # Optional link to the SourceEvent that brought the same invoice in as a
    # PDF, when one exists. Never required: an invoice may be read from an
    # accounting system with no mail behind it.
    source_event_id: str | None = None


# ---------------------------------------------------------------------------
# ReviewFinding
# ---------------------------------------------------------------------------


class VerifiedFact(BaseModel):
    """One thing that is true, and where it is true.

    ``source`` is ``"invoice"`` for a normalised field read out of an
    :class:`InvoiceSnapshot`, and ``"document"`` for a value read out of a
    passage that verified verbatim against the tenant's own document. Nothing
    that the system merely inferred goes in here — that is what ``suggestion``
    on the finding is for.
    """

    label: str
    value: str
    source: Literal["invoice", "document"]
    citation_index: int | None = None


class ReviewFinding(BaseModel):
    """Something worth a human's attention. Not a decision, and not an answer."""

    id: str
    tenant_id: str
    finding_type: FindingType
    created_at: str

    invoice_id: str | None = None
    source_event_id: str | None = None

    verdict: Verdict
    verdict_label: str = ""

    # What is actually established, separated from what is proposed.
    verified_facts: list[VerifiedFact] = Field(default_factory=list)
    suggestion: str = ""
    # Who produced `suggestion`. Named honestly: today it is a deterministic
    # rule engine, and calling that "AI" in a product whose whole point is not
    # overclaiming would be the first lie in the chain.
    suggested_by: str = "regelmotor"
    # What could NOT be established. Required for anything but a clean match:
    # a finding that expresses no uncertainty and is not a match is a finding
    # that is hiding something.
    uncertainty: str | None = None

    # Exact citations, verified verbatim through app.citations — same machinery,
    # same rects, same all-or-nothing rule as an answer's citations.
    citations: list[CitationOut] = Field(default_factory=list)

    status: FindingStatus = "open"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None

    def with_label(self) -> "ReviewFinding":
        return self.model_copy(update={"verdict_label": VERDICT_LABELS[self.verdict]})
