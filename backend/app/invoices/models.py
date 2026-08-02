"""The invoice case, and the vocabulary it is allowed to use.

Three separations run through every type in this module, and each one exists
because blurring it would produce a screen that lies:

1. **The source system's status is not ours.** ``SourceRecordStatus`` is what
   Fortnox says about its own record. It is read, shown, and never written —
   there is no code path in this product that could. ``LocalReviewStatus`` is
   what *this* association's reviewer decided, and none of its members is an
   approval, an attest or a payment. "Godkänn faktura" does not appear in this
   file for that reason.

2. **A reading is not a decision.** ``CaseSignal`` is derived from findings a
   rule engine produced; ``review_status``, ``responsible`` and every comment
   are written by a named person. They live in different fields and are written
   by different code paths, so a re-analysis physically cannot overwrite a
   human's answer.

3. **A case is not its observations.** An invoice can be seen in Fortnox, in
   the mail it arrived with, and as a PDF in the archive. Those are three
   ``CaseObservation`` rows on one case, each with the basis on which it was
   attached — not three competing records, and not one record that quietly
   forgot where its parts came from.

Amounts are :class:`~decimal.Decimal`, serialised as JSON strings, for the same
reason as everywhere else in this domain: a comparison decides whether a case
says "ingen förändring" or "möjlig avvikelse", and ``12500.10`` must not become
``12500.099999999999`` on the way to disk.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..integrations.models import utc_now_iso
from ..terms import parse_iso

# ---------------------------------------------------------------------------
# What this product's own review says
# ---------------------------------------------------------------------------

# Seven states, none of which is an approval anywhere but here.
#
# There is deliberately no "godkänd" and no "attesterad": a board member who
# read "Godkänd" on this screen would reasonably believe something happened in
# the accounting system, and nothing did. Every label below says what the
# association *did* — looked at it, asked about it, is waiting for something —
# and stops there.
LocalReviewStatus = Literal[
    "not_reviewed",
    "reviewed_no_objection",
    "needs_investigation",
    "awaiting_documentation",
    "question_sent",
    "action_created",
    "closed",
]

REVIEW_STATUS_LABELS: dict[str, str] = {
    "not_reviewed": "Ej granskad",
    "reviewed_no_objection": "Granskad – ingen invändning",
    "needs_investigation": "Behöver utredas",
    "awaiting_documentation": "Väntar på underlag",
    "question_sent": "Fråga ställd",
    "action_created": "Åtgärd skapad",
    "closed": "Granskning avslutad",
}

# What the label does *not* mean, carried next to it so a screen cannot show
# one without the other.
REVIEW_STATUS_CAVEATS: dict[str, str] = {
    "not_reviewed": "Ingen här har tagit ställning till fakturan ännu.",
    "reviewed_no_objection": (
        "En människa här har läst fakturan och inte haft någon invändning. Det är "
        "inte ett godkännande, en attest eller en bokföringsåtgärd — ingenting har "
        "ändrats i ekonomisystemet."
    ),
    "needs_investigation": "Något behöver kontrolleras innan fakturan kan bedömas.",
    "awaiting_documentation": "Bedömningen väntar på underlag som föreningen inte har.",
    "question_sent": (
        "Någon här har ställt en fråga till leverantören utanför appen. Produkten "
        "skickar ingenting — det här är anteckningen om att frågan är ställd."
    ),
    "action_created": "Arbetet ligger som en uppgift under Uppgifter.",
    "closed": "Granskningen är avslutad här. Ingenting har ändrats i ekonomisystemet.",
}

# States that still want somebody's attention. "action_created" is one of them
# on purpose: the work exists, so the case is not finished.
OPEN_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "needs_investigation",
    "awaiting_documentation",
    "question_sent",
    "action_created",
)

# Where a bare status change would record that somebody clicked and nothing
# about what is actually going on. Same argument as
# :data:`app.tasks.models.REASON_REQUIRED`: the missing sentence is the one
# somebody later wishes had been written.
REVIEW_REASON_REQUIRED: tuple[str, ...] = (
    "needs_investigation",
    "awaiting_documentation",
    "question_sent",
)


class SourceRecordStatus(BaseModel):
    """What the source system says about its own record. Never written back.

    Read from the accounting system and displayed so a reviewer can tell a
    booked invoice from an unbooked one without leaving this screen. There is
    no setter, no route and no adapter method that could change any of it —
    see :mod:`app.integrations.protocols`.
    """

    adapter: str = ""
    external_ref: str = ""
    booked: bool | None = None
    cancelled: bool | None = None
    balance: str | None = None
    retrieved_at: str = ""

    def label(self) -> str:
        if self.cancelled:
            return "Annullerad i ekonomisystemet"
        if self.booked is True:
            return "Bokförd i ekonomisystemet"
        if self.booked is False:
            return "Ej bokförd i ekonomisystemet"
        return "Bokföringsstatus okänd"


# ---------------------------------------------------------------------------
# What the case is made of
# ---------------------------------------------------------------------------


class CaseObservation(BaseModel):
    """One sighting of this invoice, and why it was attached to this case.

    ``basis`` is a sentence a reviewer can check and disagree with — "Fakturan
    lästes in ur det här meddelandet" or "Meddelandet skriver fakturanumret
    2026-131 ordagrant". A similarity score would not be checkable, and a case
    that merged two invoices on one would be worse than a case that merged
    nothing.
    """

    kind: Literal["accounting_snapshot", "email", "document"]
    ref_id: str
    label: str
    adapter: str = ""
    external_ref: str = ""
    # When the source says it happened, and when we read it. Two questions.
    occurred_at: str = ""
    retrieved_at: str = ""
    basis: str = ""
    content_sha256: str = ""
    # The document this observation can be opened as, when one exists. The
    # original file, never a derived preview: a rendered summary that replaced
    # the invoice PDF would be this product citing itself.
    document_id: str = ""


# What a queue reader needs to see at a glance. Every member is derived from
# something checkable — a finding, a stored date, a status somebody set — and
# carries the evidence it came from.
CaseSignalKind = Literal[
    "possible_duplicate",
    "missing_contract",
    "price_change",
    "new_line",
    "credit_relation",
    "unresolved_supplier",
    "open_question",
    "due_soon",
    "overdue",
    "no_deviation_found",
]

SIGNAL_LABELS: dict[str, str] = {
    "possible_duplicate": "Möjlig dubblett",
    "missing_contract": "Avtal saknas",
    "price_change": "Prisförändring",
    "new_line": "Ny post på fakturan",
    "credit_relation": "Möjlig kreditfaktura",
    "unresolved_supplier": "Leverantörsidentitet obekräftad",
    "open_question": "Fråga väntar svar",
    "due_soon": "Förfaller snart",
    "overdue": "Förfallen",
    "no_deviation_found": "Ingen avvikelse hittad",
}

# Ordered worst-first. Used to pick the one signal a queue row shows, so two
# clients cannot disagree about which one that is.
SIGNAL_SEVERITY: dict[str, str] = {
    "possible_duplicate": "warning",
    "overdue": "warning",
    "price_change": "warning",
    "missing_contract": "attention",
    "unresolved_supplier": "attention",
    "new_line": "attention",
    "due_soon": "attention",
    "open_question": "attention",
    "credit_relation": "info",
    "no_deviation_found": "info",
}

SEVERITY_RANK: dict[str, int] = {"warning": 0, "attention": 1, "info": 2}


class CaseSignal(BaseModel):
    """One thing worth noticing, with what it was read from."""

    kind: CaseSignalKind
    label: str = ""
    detail: str = ""
    # The finding this came out of, when it came out of one. A signal with no
    # evidence reference is one derived from a stored date or a status a person
    # set — never from a guess.
    finding_id: str = ""

    def severity(self) -> str:
        return SIGNAL_SEVERITY.get(self.kind, "info")

    def public(self) -> dict:
        return {
            **self.model_dump(mode="json"),
            "label": self.label or SIGNAL_LABELS.get(self.kind, self.kind),
            "severity": self.severity(),
        }


CaseEventKind = Literal[
    "case_opened",
    "observation_added",
    "analysis_run",
    "finding_recorded",
    "status_changed",
    "assigned",
    "commented",
    "task_created",
    "source_refreshed",
]

EVENT_LABELS: dict[str, str] = {
    "case_opened": "ärendet öppnat",
    "observation_added": "källa kopplad",
    "analysis_run": "granskning körd",
    "finding_recorded": "fynd",
    "status_changed": "status ändrad",
    "assigned": "ansvarig ändrad",
    "commented": "kommentar",
    "task_created": "uppgift skapad",
    "source_refreshed": "källa omläst",
}

# Which timeline entries were written by a person. The UI reads this rather
# than inferring from `by`, so a future machine actor cannot accidentally be
# rendered as a human decision.
HUMAN_EVENT_KINDS: tuple[str, ...] = (
    "status_changed",
    "assigned",
    "commented",
    "task_created",
)

# What `by` says when nothing human wrote the entry. The product has never
# called its rule engine "AI" and does not start here.
ENGINE = "regelmotor"


class CaseEvent(BaseModel):
    """One thing that happened to this case. Written once, never edited.

    ``dedupe_key`` is what makes a re-analysis idempotent. A machine-written
    entry carries a key derived from what it says, so running the analysis
    again over unchanged data adds nothing. Human entries carry none: saying
    the same thing twice is two acts, and a comment that silently vanished
    because somebody had written it before would be a comment nobody could
    trust.
    """

    id: str
    at: str
    by: str
    kind: CaseEventKind
    summary: str = ""
    ref_id: str = ""
    note: str = ""
    from_value: str = ""
    to_value: str = ""
    dedupe_key: str = ""

    @property
    def human(self) -> bool:
        return self.kind in HUMAN_EVENT_KINDS

    def public(self) -> dict:
        return {
            **self.model_dump(mode="json"),
            "kind_label": EVENT_LABELS.get(self.kind, self.kind),
            "human": self.human,
        }


# How many days ahead counts as "förfaller snart". A week: long enough that a
# board that meets weekly sees it once, short enough that it means something.
DUE_SOON_DAYS = 7


class InvoiceCase(BaseModel):
    """One invoice, as a case somebody works on."""

    id: str
    tenant_id: str

    # The deterministic identity several observations converge on, and the
    # sentence explaining why they were allowed to. See
    # :mod:`app.invoices.identity`.
    case_key: str
    identity_basis: str = ""

    supplier_name: str = ""
    supplier_key: str = ""
    supplier_ref: str | None = None

    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None

    total_amount: Decimal | None = None
    currency: str = "SEK"
    vat_amount: Decimal | None = None

    # The snapshot this case's fields were read from. One, not many: a case
    # shows what the source system says *now*, and the observations record
    # every time we looked.
    primary_invoice_id: str = ""
    observations: list[CaseObservation] = Field(default_factory=list)
    source_status: SourceRecordStatus | None = None

    review_status: LocalReviewStatus = "not_reviewed"
    review_status_note: str = ""
    review_status_by: str = ""
    review_status_at: str = ""
    responsible: str = ""

    # Derived from findings, replaced wholesale by an analysis run. Nothing a
    # human wrote is stored here.
    signals: list[CaseSignal] = Field(default_factory=list)
    analysis_at: str = ""

    timeline: list[CaseEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)

    # -- derived ---------------------------------------------------------

    def days_until_due(self, today: date) -> int | None:
        due = parse_iso(self.due_date or "")
        return (due - today).days if due else None

    def overdue(self, today: date) -> bool:
        """Past its date and nobody has finished looking at it.

        A closed case is never overdue: the question a board asks about a case
        it has settled is what it decided, not whether the date held.
        """
        left = self.days_until_due(today)
        return bool(self.open and left is not None and left < 0)

    @property
    def open(self) -> bool:
        return self.review_status in OPEN_REVIEW_STATUSES

    def last_activity_at(self) -> str:
        return self.timeline[-1].at if self.timeline else self.created_at

    def comments(self) -> list[CaseEvent]:
        return [e for e in self.timeline if e.kind == "commented"]

    def dated_signals(self, today: date) -> list[CaseSignal]:
        """Signals that depend on what day it is, never stored.

        A stored "förfaller snart" is a stored lie the morning after. These are
        computed on the way out, the same way a task's ``overdue`` is.
        """
        out: list[CaseSignal] = []
        left = self.days_until_due(today)
        if self.open and left is not None:
            if left < 0:
                out.append(
                    CaseSignal(
                        kind="overdue",
                        detail=f"Förföll {self.due_date} — {abs(left)} dagar sedan.",
                    )
                )
            elif left <= DUE_SOON_DAYS:
                out.append(
                    CaseSignal(
                        kind="due_soon",
                        detail=f"Förfaller {self.due_date} om {left} dagar.",
                    )
                )
        if self.review_status == "question_sent":
            out.append(
                CaseSignal(
                    kind="open_question",
                    detail=self.review_status_note or "En fråga är ställd och inget svar är noterat.",
                )
            )
        return out

    def all_signals(self, today: date) -> list[CaseSignal]:
        merged = [*self.signals, *self.dated_signals(today)]
        merged.sort(key=lambda s: SEVERITY_RANK.get(s.severity(), 3))
        return merged

    def public(self, today: date) -> dict:
        signals = self.all_signals(today)
        return {
            **self.model_dump(mode="json"),
            "review_status_label": REVIEW_STATUS_LABELS[self.review_status],
            "review_status_caveat": REVIEW_STATUS_CAVEATS[self.review_status],
            "source_status_label": self.source_status.label() if self.source_status else "",
            "signals": [s.public() for s in signals],
            "top_signal": signals[0].public() if signals else None,
            "timeline": [e.public() for e in self.timeline],
            "comments": [e.public() for e in self.comments()],
            "open": self.open,
            "overdue": self.overdue(today),
            "days_until_due": self.days_until_due(today),
            "last_activity_at": self.last_activity_at(),
            "observation_kinds": sorted({o.kind for o in self.observations}),
        }


__all__ = [
    "CaseEvent",
    "CaseEventKind",
    "CaseObservation",
    "CaseSignal",
    "CaseSignalKind",
    "DUE_SOON_DAYS",
    "ENGINE",
    "EVENT_LABELS",
    "HUMAN_EVENT_KINDS",
    "InvoiceCase",
    "LocalReviewStatus",
    "OPEN_REVIEW_STATUSES",
    "REVIEW_REASON_REQUIRED",
    "REVIEW_STATUS_CAVEATS",
    "REVIEW_STATUS_LABELS",
    "SEVERITY_RANK",
    "SIGNAL_LABELS",
    "SIGNAL_SEVERITY",
    "SourceRecordStatus",
]
