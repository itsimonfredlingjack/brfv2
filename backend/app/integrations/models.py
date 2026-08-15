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

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..schemas import CitationOut

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# What kind of thing arrived. Deliberately about the *shape* of the source, not
# the product that produced it: an .eml exported from any mail client is
# "email", and a future mailbox adapter adds no member here.
SourceType = Literal["email"]
SOURCE_TYPES: tuple[SourceType, ...] = ("email",)

# How the material got here. A vocabulary rather than free text, because the
# queue's provenance is read by people deciding whether to trust an entry, and
# "manuell fil" and "läst ur brevlådan styrelsen@…" are different assurances.
IntakeMethod = Literal["manual-file-import", "graph-mailbox-import"]
INTAKE_METHOD_LABELS: dict[str, str] = {
    "manual-file-import": "Manuellt vald .eml-fil",
    "graph-mailbox-import": "Hämtad ur ansluten brevlåda",
}

# Did the import land? There is no "partial": an import either produced a
# complete SourceEvent with every attachment accounted for, or it was refused
# and nothing was written. See app.integrations.eml for why.
ImportStatus = Literal["imported", "rejected"]

# Where a source event stands in the human queue.
ReviewStatus = Literal["open", "approved", "dismissed", "corrected"]

# What the triage believes one piece of incoming post is about.
#
# Seven members, deliberately few and deliberately overlapping-free at the
# level a board acts on: each one leads somewhere different in this product.
# "unclear" is a first-class member and not a failure — a queue that guesses a
# category for a message it could read nothing in has started teaching its
# users that the label means nothing.
TriageCategory = Literal[
    "invoice",
    "contract_or_quote",
    "authority_or_manager",
    "decision_or_approval",
    "question_awaiting_reply",
    "information",
    "unclear",
]

TRIAGE_CATEGORY_LABELS: dict[str, str] = {
    "invoice": "Faktura",
    "contract_or_quote": "Avtal eller offert",
    "authority_or_manager": "Myndighet eller förvaltare",
    "decision_or_approval": "Beslut eller godkännande",
    "question_awaiting_reply": "Fråga som väntar svar",
    "information": "Information",
    "unclear": "Oklart",
}

# What a human decided to do about a queue item. Five outcomes, and every one
# of them lands in a domain this product already has — there is no "email
# archive" here, because a second archive is how the association ends up with
# two answers to the same question.
#
#   take_in           preserve the message text and/or chosen attachments
#   create_task       somebody is going to do something (app.tasks)
#   monitor           a date or an awaited answer to come back to (app.watches)
#   already_handled   it mattered, and nothing further is needed
#   not_relevant      out of the queue, untouched in the mailbox
ResolutionKind = Literal[
    "take_in",
    "create_task",
    "monitor",
    "already_handled",
    "not_relevant",
]

RESOLUTION_LABELS: dict[str, str] = {
    "take_in": "Ta in",
    "create_task": "Skapa uppgift",
    "monitor": "Bevaka",
    "already_handled": "Redan hanterat",
    "not_relevant": "Inte relevant",
}

# Which of them may be combined with which. Preserving a message and creating
# work from it is one act a board performs constantly; declaring something
# irrelevant *and* preserving it is a contradiction, and the route refuses it
# rather than storing a record that says both.
EXCLUSIVE_RESOLUTIONS: tuple[str, ...] = ("already_handled", "not_relevant")

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
    # A term was read and cited but is not of a kind that can be compared to
    # anything on an invoice — an index-regulated price, a duration counted
    # from a signing date nobody recorded, a notice period. Its own type
    # because "we read this and it does not answer your question" is different
    # information from "we found nothing".
    "contract_term_not_comparable",
    # The four below compare an invoice against the association's **own invoice
    # history** rather than against a document (:mod:`app.invoices.compare`).
    # They carry no citations, and that absence is deliberate: a citation in
    # this product means a verbatim-verified passage in a document, and a
    # comparison against last month's invoice has no such passage. What stands
    # behind them is a stored invoice record, named by number and date among
    # the verified facts.
    "invoice_previous_comparison",
    "invoice_possible_duplicate",
    "invoice_credit_relation",
    "invoice_new_line",
]

# What each kind of finding is *about*, in one noun phrase. Used wherever a
# finding has to be named without being shown — an analysis run's change list,
# a filter, a heading — so those places do not each invent their own wording
# for the same thing.
FINDING_TYPE_LABELS: dict[str, str] = {
    "invoice_contract_amount": "Belopp mot avtal",
    "invoice_contract_period": "Period mot avtal",
    "invoice_without_contract": "Inget avtal att jämföra mot",
    "contract_term_not_comparable": "Avtalsvillkor som inte går att jämföra",
    "invoice_previous_comparison": "Jämförelse med föregående faktura",
    "invoice_possible_duplicate": "Möjlig dubblett",
    "invoice_credit_relation": "Möjlig kreditfaktura",
    "invoice_new_line": "Ny post på fakturan",
}

# How a document was tied to an invoice's supplier, in words. Same vocabulary
# the case view shows, so a change from one to another can be *described*
# rather than left as two codes the reader has to know.
ANCHOR_LABELS: dict[str, str] = {
    "org_number": "organisationsnummer",
    "exact": "leverantörens namn ordagrant",
    "alias": "ett namn någon här har bekräftat",
    "legal_form": "samma namn, annan bolagsform",
    "partial": "delvis namnlikhet",
}

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

    # An attachment starts as *material under review* and is not evidence
    # about anything. A named administrator can adopt it into the
    # association's own archive, and only then may the review engine cite it
    # (app.integrations.review.evidence_excluded_document_ids). The three
    # fields are one decision: what was adopted, by whom, when.
    archived: bool = False
    archived_by: str | None = None
    archived_at: str | None = None
    # Why a person said this belongs in the archive. Free text, and required
    # by the route: adopting a document into the evidence base is exactly the
    # kind of act that should be uncomfortable to do silently.
    archive_note: str | None = None


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


class TriageSignal(BaseModel):
    """One thing the triage read, and the words it read it from.

    Every signal carries its own ``quote``, taken verbatim out of the text it
    was read from. That is the same discipline the review engine and the watch
    engine live by, applied to a queue: a card that says "förfallodatum
    2026-09-30" without the sentence it came from is a claim, and a reviewer
    has no way to check it short of opening the message and searching.

    A signal is *not* a citation. Until the message text is preserved as a
    document there is no page to open, so this deliberately carries a quote and
    not a :class:`~app.schemas.CitationOut` — see
    :mod:`app.integrations.preserve` for where the two meet.
    """

    kind: Literal[
        "date",
        "deadline",
        "amount",
        "supplier",
        "decision",
        "question",
        "renewal",
        "reference",
    ]
    label: str
    value: str
    quote: str
    source: Literal["subject", "body", "attachment"]
    # The attachment id when ``source`` is "attachment"; empty otherwise. The
    # attachment, not the document: a reader wants to know which file said it.
    source_ref: str = ""


class AnchorQuestion(BaseModel):
    """A deadline whose start date is not in the text and must not be guessed.

    Feature 1 anchors day-counts to ``receivedDateTime``. This is the other
    path: "inom tre månader" has no calendar start, and applying the receipt
    date would be the guess that makes the date wrong. The hit stays a
    question until a human types the missing date; only then does
    :func:`app.terms.anchor_relative` compute a due date.
    """

    quote: str
    count: int
    unit: Literal["month", "week", "year"]
    before: bool = False
    source: Literal["subject", "body", "attachment"]
    source_ref: str = ""
    label: str = "Från vilket datum?"


class RelatedRecord(BaseModel):
    """Something already in this association's records that this may concern.

    A proposal, always. ``basis`` says why the engine thinks so in words a
    reviewer can check and disagree with — "samma leverantörsnamn som fakturan
    SI-2026-114" is checkable; a similarity score is not.
    """

    kind: Literal["document", "invoice", "source_event", "task", "watch"]
    ref_id: str
    label: str
    basis: str


class TriageSuggestion(BaseModel):
    """What the product believes about one piece of incoming post.

    A suggestion, and stored in a type named as one. Three properties make it
    safe to show next to real records:

    1. **Nothing here is a decision.** The queue displays it, a human confirms
       or changes the category (:class:`TriageConfirmation`), and only a
       resolution moves anything into the association's own records.
    2. **Everything asserted carries its words.** ``signals`` is what was read
       and where; ``headline`` and ``why_it_matters`` are written from those
       signals and from nothing else.
    3. **It says who produced it.** ``suggested_by`` is "regelmotor" for the
       deterministic reader and names the model when one refined it. The
       product has never called a rule engine "AI" and does not start here.
    """

    category: TriageCategory = "unclear"
    category_label: str = ""

    # What the app believes the message is about, and why it may matter. Both
    # short, both written from `signals`, both prefixed by nothing that claims
    # more certainty than the signals carry.
    headline: str = ""
    why_it_matters: str = ""
    # What may need doing. Empty is a real answer and reads as one in the UI.
    action_hint: str = ""

    # Two questions a board asks of every message, kept as their own fields
    # because they drive what the card offers to do next.
    awaiting_reply: bool = False
    contains_decision: bool = False

    supplier_name: str = ""

    signals: list[TriageSignal] = Field(default_factory=list)
    related: list[RelatedRecord] = Field(default_factory=list)
    # Feature 2: frists with no calendar start. Empty is the usual case, and
    # an unanswered question here is not a bevakning — see resolve.py.
    anchor_questions: list[AnchorQuestion] = Field(default_factory=list)

    suggested_by: str = "regelmotor"
    # What could not be established. Required in spirit for anything but a
    # clean read: a suggestion that expresses no doubt about a message it
    # barely understood is the one that gets believed.
    uncertainty: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class TriageConfirmation(BaseModel):
    """A human's statement about what the message actually is.

    Kept beside the suggestion rather than overwriting it. Both are worth
    having: the pair is the only record of where the engine was wrong, and a
    product that silently replaces its own guess with the correction learns
    nothing and lets nobody audit it either.
    """

    category: TriageCategory
    category_label: str = ""
    confirmed_by: str
    confirmed_at: str = Field(default_factory=utc_now_iso)
    note: str = ""


class ResolutionOutcome(BaseModel):
    """One thing that happened because a human resolved a queue item.

    ``ref_id`` points into the domain that now owns it — a task id, a watch id,
    a document id — so the queue can say "det blev uppgift X" instead of
    "hanterad", which is the difference between a record and a feeling.
    """

    kind: ResolutionKind
    label: str = ""
    ref_id: str = ""
    ref_label: str = ""


class Resolution(BaseModel):
    """How a queue item was settled, by whom, and what it produced."""

    outcomes: list[ResolutionOutcome] = Field(default_factory=list)
    decided_by: str
    decided_at: str = Field(default_factory=utc_now_iso)
    note: str = ""
    # The idempotency key of the act that produced this — a digest of the event,
    # the outcomes asked for, the note and the task/watch specifications
    # (:func:`app.integrations.resolve.resolution_key`). Stored so that the same
    # request arriving twice — a retried POST, a double-click, a client that
    # replayed after a timeout — is recognised as the *same* act and returns
    # what it already did, instead of making a second task out of one decision.
    # Empty on rows written before this existed, which correctly means "we
    # cannot tell", not "this was a different act".
    key: str = ""


class DecisionRecord(BaseModel):
    """A settlement that was later undone, kept because it happened.

    Reopening a queue item used to set ``resolution`` to ``None`` and null the
    decider and the date. What that erased was not a draft: it was a named
    person's decision, its stated reason, and the list of tasks, watches and
    documents it produced. After a reopen nothing anywhere said the association
    had ever settled the item — and the tasks it created were still sitting in
    Uppgifter with an origin pointing back at a card that denied making them.

    So a reopen now *files* the settlement here instead of deleting it, and
    ``resolution`` goes back to ``None`` as before. The queue reads the same;
    the history survives. This is a field on the source event and not a second
    store, for the reason :mod:`app.integrations.resolve` states as a
    prohibition: there is no email archive in this product, and adding one to
    hold decision history would be building it by another name.
    """

    # Derived from what the record *is*, not minted, and filled in below when a
    # caller leaves it empty. It exists so the history can be checked as
    # append-only by :func:`app.history.check_append_only`, which compares
    # entries by identity rather than by length — the check that stops a stale
    # event object from dropping a filed settlement on its way past.
    id: str = ""

    # What was decided, exactly as it stood — outcomes, note, decider, key.
    resolution: Resolution
    # The coarse status that accompanied it, so a reader does not have to infer
    # "not relevant" from the absence of outcomes.
    review_status: ReviewStatus
    # When this record was filed, and by whom — the reopen, not the decision.
    superseded_at: str = Field(default_factory=utc_now_iso)
    superseded_by: str = ""
    # Why it was reopened, when the reopening said.
    note: str = ""

    @model_validator(mode="after")
    def _derive_id(self) -> "DecisionRecord":
        if not self.id:
            basis = "\x00".join(
                [
                    self.resolution.key,
                    self.resolution.decided_by,
                    self.resolution.decided_at,
                    self.superseded_at,
                ]
            )
            object.__setattr__(
                self, "id", hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
            )
        return self


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

    # What the message says it is a reply to, and the chain above it. Read
    # straight out of the headers and used for grouping only — same caveat as
    # ``external_ref``: a sender controls these, so they may join two things
    # that are not related, and they may be absent when two things are. The
    # grouping in :mod:`app.integrations.threads` is therefore a *reading* of
    # the mailbox and never a claim about it.
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    # The conversation this belongs to, computed at import from the headers
    # above and the normalised subject. Stored rather than recomputed on every
    # read so that a card cannot silently regroup itself under a reader.
    thread_key: str = ""
    # The subject with the reply and forward prefixes stripped, which is what
    # a thread is named after.
    thread_subject: str = ""

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

    # What the product believes this is, and what a human said it is. Both
    # optional: a queue entry imported by an older build has neither, and a
    # message nobody has looked at has only the first.
    triage: TriageSuggestion | None = None
    triage_confirmation: TriageConfirmation | None = None

    # How it was settled, and what that produced.
    resolution: Resolution | None = None
    # Settlements that were reopened, oldest first. Append-only: a reopen files
    # the current resolution here rather than deleting it, so "did we ever
    # decide this, and what did it create" stays answerable after somebody puts
    # the card back in the queue. See :class:`DecisionRecord`.
    decision_history: list[DecisionRecord] = Field(default_factory=list)

    # The message text, preserved as an ordinary document of the
    # association's. This is what makes an attachment-less mail answerable
    # later: a decision, an accepted quote or a stated notice period that
    # arrived as prose becomes a page the ordinary retrieval finds and the
    # ordinary citation machinery opens at the right line.
    #
    # Set only by a human act (:mod:`app.integrations.preserve`), never at
    # import: the mailbox is raw material, and preserving every message that
    # arrived would be importing the mailbox into the archive under another
    # name.
    preserved_document_id: str | None = None
    preserved_by: str | None = None
    preserved_at: str | None = None
    preservation_note: str | None = None

    def category(self) -> str:
        """What this is, human decision first.

        One place decides, so a card, a thread header and a filter cannot
        disagree about the same message.
        """
        if self.triage_confirmation is not None:
            return self.triage_confirmation.category
        if self.triage is not None:
            return self.triage.category
        return "unclear"

    def resolved(self) -> bool:
        return self.resolution is not None


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

    # What the source system says about its own record — booked, cancelled, the
    # remaining balance. Read and shown so a reviewer can see the accounting
    # system's state without leaving this product; never sent anywhere, because
    # there is no adapter method and no egress verb that could send it. This is
    # the one exception the class docstring above allows for: the snapshot may
    # *record* what the source system said. It owns none of it.
    source_status: dict[str, str] = Field(default_factory=dict)


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


class SupplierAlias(BaseModel):
    """A human's statement that two supplier names are one supplier.

    The review can *guess* this — "Snösvängen AB" and "Snösvängen Entreprenad
    AB" share a distinctive head — but a guess is only ever allowed to produce
    a weak anchor that says so. An alias is the same claim made by a named
    person at the association, recorded once and strong thereafter. That is the
    difference between a system that learns and a system that assumes.
    """

    id: str
    tenant_id: str
    # As the invoice writes it, and as the document writes it. Both stored as
    # typed, plus a normalised key so lookup does not depend on spacing or
    # legal form.
    invoice_name: str
    document_name: str
    normalized_key: str
    created_by: str
    created_at: str = Field(default_factory=utc_now_iso)
    note: str | None = None


class AliasProposal(BaseModel):
    """The alias a weak anchor would like a human to confirm or reject."""

    invoice_name: str
    document_name: str
    document_id: str
    # Why the engine thinks they are the same, in words a reviewer can check.
    basis: str


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

    # How the document under citation was tied to this invoice's supplier:
    # "org_number", "exact", "alias", "legal_form" or "partial". Carried on the
    # finding rather than left implicit, because a reviewer weighing a "möjlig
    # avvikelse" needs to know whether the two papers are certainly about the
    # same company or merely probably.
    anchor_strength: str | None = None
    anchor_note: str | None = None
    # Present only for a weak anchor: the alias the engine would like confirmed.
    alias_proposal: AliasProposal | None = None

    status: FindingStatus = "open"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None

    def with_label(self) -> "ReviewFinding":
        return self.model_copy(update={"verdict_label": VERDICT_LABELS[self.verdict]})


def finding_content_key(finding: ReviewFinding) -> str:
    """What a finding *says*, independent of when it was produced.

    Two findings with the same key are the same statement about the same
    invoice, made by two runs. The id is deliberately not part of it: an engine
    mints a fresh id every run, so keying on it would make every finding unique
    and every re-run look like a change.

    The **verified facts are part of what it says**, and leaving them out was a
    real hole: an invoice whose total changed while the surrounding prose
    happened not to — the "no contract names this supplier" finding is the
    obvious case — would have compared as unchanged, and the amount would have
    moved under the reader with nothing recording it. The citations are in for
    the same reason: a finding that now rests on a different passage is a
    different finding, whatever it reads like.

    Used in three places that must agree with each other: deciding whether a
    re-run may append a second copy of something a human already decided on
    (:meth:`IntegrationStore.replace_findings_for_invoice`), diffing one
    analysis run against the previous one (:mod:`app.invoices.audit`), and
    deduplicating a case's timeline.
    """
    facts = "|".join(
        f"{fact.label}={fact.value}@{fact.source}" for fact in finding.verified_facts
    )
    # Not the score and not the rects: those are retrieval mechanics, and a
    # rounding difference in one is not a change in what was established.
    citations = "|".join(
        f"{c.document_id}#{c.page}:{c.quote}" for c in finding.citations
    )
    return "\x00".join(
        [
            finding.finding_type,
            finding.verdict,
            finding.suggestion,
            finding.uncertainty or "",
            finding.anchor_strength or "",
            facts,
            citations,
        ]
    )


# ---------------------------------------------------------------------------
# MailboxCheckpoint
# ---------------------------------------------------------------------------


class SkippedMessage(BaseModel):
    """A message the fetch saw and did not take in, with the reason.

    This type exists because the alternative is silence. The `.eml` format is
    deliberately narrow — one attachment that is not a PDF refuses the whole
    message, so that nothing is ever half-imported — and a batch fetch that
    quietly dropped those messages would leave the operator believing the queue
    is the mailbox. It is not, and this is how the queue says so.

    Nothing is written to the queue for a skipped message and nothing is
    touched in the mailbox: it is still there, still unread, and can be
    exported by hand if it matters.
    """

    external_ref: str
    subject: str
    sender: str
    received_at: str = ""
    code: str
    reason: str


class MailboxCheckpoint(BaseModel):
    """Where the last fetch got to, so the next one asks for what is new.

    A checkpoint, not a sync cursor: this product still has no polling loop, no
    webhook and no background thread — every fetch happens because a person
    pressed something (:mod:`app.integrations.protocols`). What this removes is
    only the *re-presentation* of material already dealt with, which is what
    made the first version of the inbox unusable after a fortnight.

    ``high_water_mark`` is the ``receivedDateTime`` of the newest message the
    last successful fetch actually saw, and the next fetch asks the mailbox for
    everything at or after it. At-or-after rather than strictly-after on
    purpose: two messages can share a timestamp to the second, and the content
    hash already makes re-seeing one harmless, whereas skipping one is not.
    """

    provider: str = ""
    folder: str = ""
    # Empty until a first successful fetch. Empty means "everything the folder
    # will give us", which is the correct first-run behaviour.
    #
    # **Monotonic.** :meth:`app.integrations.store.IntegrationStore.put_mailbox_checkpoint`
    # merges rather than replaces, so this only ever moves forward. Two fetches
    # overlapping — a slow one started first, a fast one that finished while it
    # was still reading — used to leave whichever *finished* last, and the older
    # mark winning meant the queue re-presented a fortnight of settled material.
    high_water_mark: str = ""
    # The oldest message this folder still owes us, when the last fetch could
    # not read one. Monotonicity alone would be the wrong fix: clamping the mark
    # back below a failed message is exactly how the old code re-offered it, and
    # a mark that can only rise would have skipped it permanently and silently.
    #
    # So the two questions are separated. ``high_water_mark`` answers "how far
    # have we definitely got", and only rises. ``retry_from`` answers "what do we
    # still owe", is set to the timestamp of the oldest message a fetch failed
    # on, and is what the next fetch actually asks the mailbox from. It is
    # cleared by a fetch that stalls on nothing. Re-reading is free: the content
    # hash and ``external_ref`` already make a second sight of a message a
    # no-op.
    retry_from: str = ""
    last_fetched_at: str = ""
    last_fetch_by: str = ""
    # What the last fetch produced, kept so the UI can say it without the
    # operator having to have been watching when it happened.
    last_new_count: int = 0
    last_seen_count: int = 0
    last_skipped: list[SkippedMessage] = Field(default_factory=list)
    # Set when the last attempt failed, cleared by the next success. A
    # checkpoint that silently kept its old timestamp through a failure would
    # make a fetch that never ran look like one that found nothing.
    last_error: str = ""

    def fetch_from(self) -> str:
        """Where the next fetch asks the mailbox to start.

        The retry floor when there is one, otherwise the high-water mark. Never
        the later of the two: the whole point of the floor is that it is behind
        the mark, holding the window open over a message that has not been taken
        in yet.
        """
        if self.retry_from and (not self.high_water_mark or self.retry_from < self.high_water_mark):
            return self.retry_from
        return self.high_water_mark

    def public(self) -> dict:
        return {
            **self.model_dump(mode="json"),
            "hasFetched": bool(self.last_fetched_at),
            "fetchFrom": self.fetch_from(),
        }
