"""Building, analysing and working an invoice case.

Four things happen in this module and it is worth naming which of them a
machine may do:

* :func:`ensure_cases` — a *projection*. Every invoice snapshot the tenant has
  read gets exactly one case, converged by :mod:`app.invoices.identity`. It is
  idempotent, writes nothing a human would recognise as a decision, and is safe
  to run on every read: that is what makes an invoice read through the older
  integration pane, or before this feature existed, appear in the workspace
  without anyone having to migrate anything.
* :func:`analyse_case` — the engines. The contract review
  (:mod:`app.integrations.review`) and the history comparison
  (:mod:`app.invoices.compare`) run, their findings replace the *open* ones and
  leave decided ones alone, and the case's signals are recomputed from what
  came out.
* :func:`set_review_status`, :func:`assign`, :func:`comment` — people. Each one
  writes a timeline entry with the name of whoever did it.
* :func:`supplier_context` — memory, assembled out of records that already
  exist. No supplier table is introduced here, because a second place supplier
  facts live is a second place they can be wrong.

**A re-analysis cannot overwrite a human.** The two write different fields:
the engines write ``signals`` and findings, a person writes ``review_status``,
``responsible`` and comments. There is no path in this file where the first
touches the second, and the timeline keeps both in one order while marking
which is which (:data:`app.invoices.models.HUMAN_EVENT_KINDS`).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from decimal import Decimal

from ..integrations.models import (
    InvoiceSnapshot,
    ReviewFinding,
    SourceEvent,
    utc_now_iso,
)
from ..integrations.review import review_invoice
from ..integrations.supplier import normalize as normalize_supplier
from ..store import Store
from . import compare
from .identity import case_key_for, email_basis
from .models import (
    ENGINE,
    REVIEW_REASON_REQUIRED,
    REVIEW_STATUS_LABELS,
    SIGNAL_LABELS,
    CaseEvent,
    CaseObservation,
    CaseSignal,
    InvoiceCase,
    SourceRecordStatus,
)

logger = logging.getLogger("brf.invoices.cases")


class CaseError(ValueError):
    """The case cannot be changed as asked, and the message says why."""


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def _event(
    kind: str,
    *,
    by: str,
    summary: str,
    ref_id: str = "",
    note: str = "",
    from_value: str = "",
    to_value: str = "",
    dedupe_key: str = "",
) -> CaseEvent:
    return CaseEvent(
        id=uuid.uuid4().hex[:12],
        at=utc_now_iso(),
        by=by,
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        ref_id=ref_id,
        note=note,
        from_value=from_value,
        to_value=to_value,
        dedupe_key=dedupe_key,
    )


def _appended(case: InvoiceCase, events: list[CaseEvent]) -> InvoiceCase:
    """Add entries the timeline does not already carry.

    A machine entry with a ``dedupe_key`` that is already present is dropped —
    that is what makes pressing "Uppdatera" twice produce one history rather
    than two. A human entry has no key and is always added.
    """
    seen = {e.dedupe_key for e in case.timeline if e.dedupe_key}
    fresh: list[CaseEvent] = []
    for event in events:
        if event.dedupe_key and event.dedupe_key in seen:
            continue
        if event.dedupe_key:
            seen.add(event.dedupe_key)
        fresh.append(event)
    if not fresh:
        return case
    return case.model_copy(update={"timeline": [*case.timeline, *fresh]})


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def _source_status(snapshot: InvoiceSnapshot) -> SourceRecordStatus | None:
    """What the accounting system said about its own record, as a typed thing.

    ``None`` when the source carries no such notion at all — the fixture
    dataset does not, and inventing "Ej bokförd" for it would be this product
    asserting something about a system it never asked.
    """
    raw = snapshot.source_status or {}
    if not raw:
        return None

    def flag(key: str) -> bool | None:
        value = raw.get(key)
        if value is None:
            return None
        return str(value).strip().lower() in ("true", "1", "ja", "yes")

    return SourceRecordStatus(
        adapter=snapshot.adapter,
        external_ref=snapshot.external_ref,
        booked=flag("Booked"),
        cancelled=flag("Cancelled"),
        balance=raw.get("Balance"),
        retrieved_at=snapshot.retrieved_at,
    )


def _snapshot_observation(snapshot: InvoiceSnapshot) -> CaseObservation:
    return CaseObservation(
        kind="accounting_snapshot",
        ref_id=snapshot.id,
        label=(
            f"{snapshot.adapter} {snapshot.external_ref}"
            + (f" — faktura {snapshot.invoice_number}" if snapshot.invoice_number else "")
        ),
        adapter=snapshot.adapter,
        external_ref=snapshot.external_ref,
        occurred_at=snapshot.invoice_date or "",
        retrieved_at=snapshot.retrieved_at,
        basis=f"Läst read-only ur {snapshot.source_dataset}.",
        content_sha256=snapshot.content_sha256,
    )


def _email_observations(
    store: Store, snapshot: InvoiceSnapshot
) -> list[CaseObservation]:
    """The mail this invoice arrived with, and the file that came in it.

    Both are observations of the same case, and neither replaces the other:
    the mail is the envelope with its sender, date and provenance, and the
    attachment is the original document — the thing the citation machinery can
    actually open. A rendered preview never stands in for either.
    """
    try:
        events: list[SourceEvent] = store.integrations.list_source_events()
    except Exception as exc:  # a broken queue must not take the workspace down
        logger.error("Kunde inte läsa källhändelser för fakturaärende: %s", exc)
        return []

    out: list[CaseObservation] = []
    for event in events:
        basis = email_basis(event, snapshot)
        if basis is None:
            continue
        out.append(
            CaseObservation(
                kind="email",
                ref_id=event.id,
                label=f"{event.subject or '(utan ämne)'} — från {event.origin}",
                adapter=event.provenance.adapter,
                external_ref=event.external_ref or "",
                occurred_at=event.occurred_at or event.received_at,
                retrieved_at=event.received_at,
                basis=basis,
                content_sha256=event.content_sha256,
            )
        )
        for attachment in event.attachments:
            if not attachment.document_id:
                continue
            out.append(
                CaseObservation(
                    kind="document",
                    ref_id=attachment.id,
                    label=attachment.filename,
                    adapter=event.provenance.adapter,
                    occurred_at=event.occurred_at or event.received_at,
                    retrieved_at=event.received_at,
                    basis=(
                        f"Bilaga i det meddelande som knutits till ärendet. {basis}"
                        + (
                            ""
                            if attachment.archived
                            else " Ligger kvar som material under granskning — den är det som "
                            "granskas, inte det som granskas mot."
                        )
                    ),
                    content_sha256=attachment.sha256,
                    document_id=attachment.document_id,
                )
            )
    return out


def _merge_observations(
    case: InvoiceCase, found: list[CaseObservation]
) -> tuple[list[CaseObservation], list[CaseEvent]]:
    """Keep one row per (kind, ref), and say when a new one appeared."""
    by_key = {(o.kind, o.ref_id): o for o in case.observations}
    events: list[CaseEvent] = []
    for observation in found:
        key = (observation.kind, observation.ref_id)
        if key not in by_key:
            events.append(
                _event(
                    "observation_added",
                    by=ENGINE,
                    summary=f"Källa kopplad: {observation.label}",
                    ref_id=observation.ref_id,
                    note=observation.basis,
                    dedupe_key=f"obs:{observation.kind}:{observation.ref_id}",
                )
            )
        by_key[key] = observation
    order = {"accounting_snapshot": 0, "email": 1, "document": 2}
    merged = sorted(by_key.values(), key=lambda o: (order.get(o.kind, 9), o.occurred_at, o.ref_id))
    return merged, events


def _primary(store: Store, case: InvoiceCase, snapshot: InvoiceSnapshot) -> InvoiceSnapshot:
    """Which reading the case describes itself by, when several converged on it.

    The most recently retrieved one, ties broken by id. It has to be decided
    somewhere and it has to be decided the same way every time: two sources
    reading the same invoice would otherwise take turns owning the case's
    fields, and a supplier name that changed every time somebody pressed
    refresh would be worse than either answer.
    """
    current = (
        store.integrations.get_invoice(case.primary_invoice_id)
        if case.primary_invoice_id
        else None
    )
    if current is None or current.id == snapshot.id:
        return snapshot
    return max((current, snapshot), key=lambda s: (s.retrieved_at, s.id))


def _sync(store: Store, case: InvoiceCase, snapshot: InvoiceSnapshot) -> InvoiceCase:
    """Bring a case in step with the snapshot and the queue, without deciding anything."""
    observations, events = _merge_observations(
        case, [_snapshot_observation(snapshot), *_email_observations(store, snapshot)]
    )
    primary = _primary(store, case, snapshot)
    updated = case.model_copy(
        update={
            "supplier_name": primary.supplier_name,
            "supplier_key": normalize_supplier(primary.supplier_name),
            "supplier_ref": primary.supplier_ref,
            "invoice_number": primary.invoice_number,
            "invoice_date": primary.invoice_date,
            "due_date": primary.due_date,
            "period_start": primary.period_start,
            "period_end": primary.period_end,
            "total_amount": primary.total_amount,
            "currency": primary.currency or "SEK",
            "vat_amount": primary.vat_amount,
            "primary_invoice_id": primary.id,
            "observations": observations,
            "source_status": _source_status(primary),
            # Recomputed from whatever findings are stored right now. Cheap,
            # deterministic, and it means an invoice reviewed through the older
            # pane shows its signals here without a re-run.
            "signals": signals_for(findings_for_invoice(store, primary.id)),
        }
    )
    return _appended(updated, events)


def case_for_snapshot(store: Store, snapshot: InvoiceSnapshot) -> InvoiceCase:
    """The case this reading belongs to, created if it is the first one.

    Idempotent: the same snapshot read again lands on the same case, adds no
    second observation and writes no second "ärendet öppnat".
    """
    key, basis = case_key_for(snapshot)
    stored = store.integrations.find_invoice_case(key)
    if stored is None:
        # A re-read that filled in a missing invoice number changes the key.
        # Following the snapshot rather than the key here is what stops the
        # association's review notes being orphaned on a case nothing points at
        # any more.
        stored = next(
            (
                c
                for c in store.integrations.list_invoice_cases()
                if c.primary_invoice_id == snapshot.id
            ),
            None,
        )
    before = stored.model_dump(mode="json") if stored is not None else None
    existing = stored.model_copy(update={"case_key": key}) if stored is not None else None
    if existing is None:
        existing = InvoiceCase(
            id=uuid.uuid4().hex[:12],
            tenant_id=store.tenant_id,
            case_key=key,
            identity_basis=basis,
            created_at=utc_now_iso(),
        )
        existing = _appended(
            existing,
            [
                _event(
                    "case_opened",
                    by=ENGINE,
                    summary=(
                        f"Fakturaärende öppnat för {snapshot.supplier_name} "
                        f"{snapshot.invoice_number or snapshot.external_ref}."
                    ),
                    note=basis,
                    dedupe_key=f"open:{key}",
                )
            ],
        )

    if existing.identity_basis != basis:
        existing = existing.model_copy(update={"identity_basis": basis})
    synced = _sync(store, existing, snapshot)
    # Only write when something actually differs from what is on disk, so a
    # plain read of the workspace does not churn the file on every request.
    if before is not None and synced.model_dump(mode="json") == before:
        return existing
    return store.integrations.upsert_invoice_case(synced)


def ensure_cases(store: Store) -> list[InvoiceCase]:
    """One case per invoice snapshot, converged and up to date.

    Safe to call on a plain read. Nothing here records a decision: a projected
    case starts at ``not_reviewed`` with an empty note and no responsible, which
    is an accurate statement that nobody has looked at it yet. Writing happens
    only when something actually differs, so repeated reads do not churn the
    file.
    """
    for snapshot in store.integrations.list_invoices():
        case_for_snapshot(store, snapshot)
    return store.integrations.list_invoice_cases()


# ---------------------------------------------------------------------------
# Findings and signals
# ---------------------------------------------------------------------------


def findings_for_invoice(store: Store, invoice_id: str) -> list[ReviewFinding]:
    if not invoice_id:
        return []
    return [f for f in store.integrations.list_findings() if f.invoice_id == invoice_id]


def _change_detail(finding: ReviewFinding) -> str:
    for fact in finding.verified_facts:
        if fact.label == "Förändring":
            return fact.value
    return finding.suggestion[:120]


def signals_for(findings: list[ReviewFinding]) -> list[CaseSignal]:
    """What a queue row should say, derived from findings and nothing else.

    A dismissed finding produces no signal: somebody looked at it and said it
    was not a thing, and a queue that kept flagging it would be teaching people
    to ignore the column.
    """
    active = [f for f in findings if f.status != "dismissed"]
    out: list[CaseSignal] = []
    seen: set[str] = set()

    def add(kind: str, detail: str, finding_id: str = "") -> None:
        if kind in seen:
            return
        seen.add(kind)
        out.append(
            CaseSignal(
                kind=kind,  # type: ignore[arg-type]
                label=SIGNAL_LABELS[kind],
                detail=detail,
                finding_id=finding_id,
            )
        )

    for f in active:
        if f.finding_type == "invoice_possible_duplicate":
            add("possible_duplicate", f.suggestion[:160], f.id)
        elif f.finding_type == "invoice_without_contract":
            add(
                "missing_contract",
                "Inget dokument i arkivet namnger leverantören, så fakturan går inte att "
                "granska mot något.",
                f.id,
            )
        elif f.finding_type == "invoice_previous_comparison" and f.verdict == "possible_deviation":
            add("price_change", _change_detail(f), f.id)
        elif f.finding_type == "invoice_new_line":
            add("new_line", f.suggestion[:160], f.id)
        elif f.finding_type == "invoice_credit_relation":
            add("credit_relation", f.suggestion[:160], f.id)
        if f.alias_proposal is not None:
            add(
                "unresolved_supplier",
                f"Fakturans \"{f.alias_proposal.invoice_name}\" och dokumentets "
                f"\"{f.alias_proposal.document_name}\" är inte bekräftade som samma leverantör.",
                f.id,
            )

    if active and not out and all(f.verdict == "matches" for f in active):
        add(
            "no_deviation_found",
            "Granskningen hittade ingen avvikelse. Det är inte ett godkännande och säger "
            "ingenting om bokföring eller betalning.",
        )
    return out


def _fingerprint(findings: list[ReviewFinding], signals: list[CaseSignal]) -> str:
    """What an analysis run *said*, independent of when it ran.

    Used as the run's dedupe key so a re-run over unchanged data adds no second
    "granskning körd" to the timeline, while a run that found something new
    does. Finding ids are deliberately not part of it — they are fresh on every
    run and would make every fingerprint unique, which is the bug this avoids.
    """
    payload = "|".join(
        sorted(f"{f.finding_type}:{f.verdict}:{f.suggestion}" for f in findings)
    ) + "||" + "|".join(sorted(f"{s.kind}:{s.detail}" for s in signals))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def analyse_case(store: Store, case: InvoiceCase) -> InvoiceCase:
    """Run both engines over the case's invoice and record what came out.

    Open findings are replaced; findings a human already decided on are kept
    untouched by :meth:`IntegrationStore.replace_findings_for_invoice`. Nothing
    a human wrote on the *case* is touched at all.
    """
    snapshot = store.integrations.get_invoice(case.primary_invoice_id)
    if snapshot is None:
        raise CaseError("Ärendet har ingen inläst faktura att granska.")

    history = store.integrations.list_invoices()
    keys = {row.id: case_key_for(row)[0] for row in history}

    produced = list(review_invoice(store, snapshot))
    produced.extend(
        compare.analyse_history(
            snapshot, history, case=case, key_of=lambda row: keys.get(row.id, "")
        )
    )
    store.integrations.replace_findings_for_invoice(snapshot.id, produced)

    findings = findings_for_invoice(store, snapshot.id)
    signals = signals_for(findings)
    fingerprint = _fingerprint(findings, signals)

    events = [
        _event(
            "analysis_run",
            by=ENGINE,
            summary=(
                f"Granskning körd: {len(findings)} fynd, "
                + (
                    ", ".join(s.label for s in signals)
                    if signals
                    else "ingen signal att lyfta"
                )
                + "."
            ),
            dedupe_key=f"analysis:{fingerprint}",
        )
    ]
    for f in findings:
        events.append(
            _event(
                "finding_recorded",
                by=f.suggested_by or ENGINE,
                summary=f"{f.verdict_label}: {f.suggestion[:160]}",
                ref_id=f.id,
                dedupe_key="finding:"
                + hashlib.sha256(
                    f"{f.finding_type}:{f.verdict}:{f.suggestion}".encode("utf-8")
                ).hexdigest()[:16],
            )
        )

    updated = _appended(
        case.model_copy(update={"signals": signals, "analysis_at": utc_now_iso()}),
        events,
    )
    return store.integrations.upsert_invoice_case(updated)


# ---------------------------------------------------------------------------
# What people do
# ---------------------------------------------------------------------------


def set_review_status(
    store: Store, case: InvoiceCase, *, status: str, note: str, user_id: str
) -> InvoiceCase:
    """Record this association's own position on the invoice.

    Not an approval anywhere else. Three of the statuses require a sentence,
    for the same reason blocking a task does: "Behöver utredas" with no note
    records that somebody clicked and nothing about what needs looking at.
    """
    if status not in REVIEW_STATUS_LABELS:
        raise CaseError(
            f"Okänd granskningsstatus. Tillåtna: {', '.join(REVIEW_STATUS_LABELS)}."
        )
    reason = (note or "").strip()
    if status in REVIEW_REASON_REQUIRED and not reason:
        raise CaseError(
            "Skriv vad som ska utredas, vilket underlag som saknas eller vad frågan gäller."
        )
    if status == case.review_status and not reason:
        raise CaseError("Statusen är redan satt till det. Inget att spara.")

    updated = case.model_copy(
        update={
            "review_status": status,
            "review_status_note": reason,
            "review_status_by": user_id,
            "review_status_at": utc_now_iso(),
        }
    )
    return store.integrations.upsert_invoice_case(
        _appended(
            updated,
            [
                _event(
                    "status_changed",
                    by=user_id,
                    summary=f"Granskningsstatus: {REVIEW_STATUS_LABELS[status]}",
                    from_value=REVIEW_STATUS_LABELS[case.review_status],
                    to_value=REVIEW_STATUS_LABELS[status],
                    note=reason,
                )
            ],
        )
    )


def assign(store: Store, case: InvoiceCase, *, responsible: str, user_id: str) -> InvoiceCase:
    name = (responsible or "").strip()
    if name == case.responsible:
        raise CaseError("Ansvarig är redan satt till det.")
    updated = case.model_copy(update={"responsible": name})
    return store.integrations.upsert_invoice_case(
        _appended(
            updated,
            [
                _event(
                    "assigned",
                    by=user_id,
                    summary=f"Ansvarig: {name or 'ej utsedd'}",
                    from_value=case.responsible,
                    to_value=name,
                )
            ],
        )
    )


def comment(store: Store, case: InvoiceCase, *, text: str, user_id: str) -> InvoiceCase:
    """Say something about the invoice without changing anything about it."""
    said = (text or "").strip()
    if not said:
        raise CaseError("Tom kommentar.")
    return store.integrations.upsert_invoice_case(
        _appended(
            case,
            [_event("commented", by=user_id, summary=said[:160], note=said)],
        )
    )


def note_task(store: Store, case: InvoiceCase, *, task, user_id: str) -> InvoiceCase:
    """Put the work somebody took on into the case's own history."""
    return store.integrations.upsert_invoice_case(
        _appended(
            case,
            [
                _event(
                    "task_created",
                    by=user_id,
                    summary=f"Uppgift skapad: {task.title}",
                    ref_id=task.id,
                    note=f"Ansvarig: {task.responsible or 'ej utsedd'}",
                )
            ],
        )
    )


# ---------------------------------------------------------------------------
# Supplier memory
# ---------------------------------------------------------------------------


def supplier_context(store: Store, case: InvoiceCase, today: date) -> dict:
    """What the association already knows about this supplier.

    Assembled out of records that exist anyway — earlier cases, the documents
    findings have cited, confirmed name aliases, open work. Nothing is stored:
    a supplier table would be a second place these facts live, and the second
    one is the one nobody maintains.
    """
    key = case.supplier_key
    cases = [
        c
        for c in store.integrations.list_invoice_cases()
        if c.supplier_key == key and c.id != case.id
    ]
    cases.sort(key=lambda c: (c.invoice_date or "", c.created_at), reverse=True)

    amounts = [c.total_amount for c in cases if c.total_amount is not None]
    if case.total_amount is not None:
        amounts.append(case.total_amount)

    documents: dict[str, str] = {}
    deviations = 0
    for related in [case, *cases]:
        for f in findings_for_invoice(store, related.primary_invoice_id):
            if f.verdict == "possible_deviation" and f.status != "dismissed":
                deviations += 1
            for citation in f.citations:
                documents.setdefault(citation.document_id, citation.document_name)

    tasks = []
    for related in [case, *cases]:
        for task in store.tasks.tasks_for_origin("invoice_case", related.id):
            tasks.append(task.public(today))

    aliases = [
        a.model_dump(mode="json")
        for a in store.integrations.list_supplier_aliases()
        if a.normalized_key == key
    ]

    org_numbers = sorted(
        {c.supplier_ref for c in [case, *cases] if c.supplier_ref}
    )

    return {
        "supplier_name": case.supplier_name,
        "supplier_key": key,
        "org_numbers": org_numbers,
        "invoice_count": len(cases) + 1,
        "amount_low": str(min(amounts)) if amounts else None,
        "amount_high": str(max(amounts)) if amounts else None,
        "currency": case.currency,
        "previous": [
            {
                "id": c.id,
                "invoice_number": c.invoice_number,
                "invoice_date": c.invoice_date,
                "total_amount": str(c.total_amount) if c.total_amount is not None else None,
                "currency": c.currency,
                "review_status": c.review_status,
                "review_status_label": REVIEW_STATUS_LABELS[c.review_status],
                "responsible": c.responsible,
            }
            for c in cases[:12]
        ],
        "documents": [{"id": doc_id, "name": name} for doc_id, name in documents.items()],
        "deviation_count": deviations,
        "aliases": aliases,
        "tasks": tasks,
        "responsibles": sorted({c.responsible for c in [case, *cases] if c.responsible}),
    }


def documents_for(store: Store, case: InvoiceCase) -> list[dict]:
    """The openable original material behind this case.

    Only files the association actually holds: an attachment that was ingested,
    and the preserved text of the mail when somebody kept it. A derived preview
    is never listed here, because the point of the column is the original.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for observation in case.observations:
        if observation.kind == "document" and observation.document_id:
            meta = store.documents.get(observation.document_id)
            if meta is None or observation.document_id in seen:
                continue
            seen.add(observation.document_id)
            out.append(
                {
                    "id": observation.document_id,
                    "name": meta.name,
                    "pages": meta.pages,
                    "role": "Originalfil ur meddelandet",
                    "basis": observation.basis,
                }
            )
        if observation.kind == "email":
            event = store.integrations.get_source_event(observation.ref_id)
            if event is None or not event.preserved_document_id:
                continue
            meta = store.documents.get(event.preserved_document_id)
            if meta is None or event.preserved_document_id in seen:
                continue
            seen.add(event.preserved_document_id)
            out.append(
                {
                    "id": event.preserved_document_id,
                    "name": meta.name,
                    "pages": meta.pages,
                    "role": "Meddelandets bevarade text",
                    "basis": event.preservation_note or "",
                }
            )
    return out


def totals(cases: list[InvoiceCase], today: date) -> dict:
    """Counts the queue header shows. Computed once, server-side.

    Server-side for the same reason the watch board's are: the desktop and any
    other client must not be able to disagree about what is open or overdue.
    """
    openish = [c for c in cases if c.open]
    return {
        "total": len(cases),
        "open": len(openish),
        "overdue": len([c for c in openish if c.overdue(today)]),
        "unassigned": len([c for c in openish if not c.responsible]),
        "withSignal": len(
            [c for c in openish if any(s.severity() != "info" for s in c.all_signals(today))]
        ),
        "amountOpen": str(
            sum((c.total_amount or Decimal(0) for c in openish), Decimal(0))
        ),
    }


__all__ = [
    "CaseError",
    "analyse_case",
    "assign",
    "case_for_snapshot",
    "comment",
    "documents_for",
    "ensure_cases",
    "findings_for_invoice",
    "note_task",
    "set_review_status",
    "signals_for",
    "supplier_context",
    "totals",
]
