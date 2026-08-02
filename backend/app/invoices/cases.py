"""Building, analysing and working an invoice case.

The split that matters in this module is **which functions write**, and it is
deliberately narrow:

* :func:`project` and :func:`project_one` are **pure**. They read snapshots,
  findings and queue events, and return the cases those imply. They write
  nothing, take no lock, and calling one twice changes nothing — so a plain
  ``GET`` of the workspace has no side effects at all. That is what makes an
  invoice read through the older integration pane, or before this workspace
  existed, appear here without a migration step and without a read quietly
  creating records.
* :func:`mutate` is the **only** writer, and every write goes through it: it
  holds the tenant's store lock across read-modify-write, so two requests
  cannot interleave into a lost comment or a duplicated case.
* :func:`analyse_case`, :func:`set_review_status`, :func:`assign`,
  :func:`comment` and :func:`note_task` are all thin wrappers over
  :func:`mutate`. None of them takes an :class:`InvoiceCase` — they take an
  **id**, so the version being modified is always the one on disk right now
  rather than whatever the caller read a moment ago.

**Identity is the idempotency key.** A case's ``id`` is derived from
``(tenant_id, case_key)`` (:func:`case_id_for`), not minted randomly. That is
what makes the write path safe: :meth:`IntegrationStore.upsert_invoice_case`
upserts on ``id``, so two racing writers converge on one row instead of
appending two. An earlier version used ``uuid4`` here and eight concurrent reads
of four invoices produced thirty-one cases.

**A re-analysis cannot overwrite a human.** The engines write ``signals`` and
findings; a person writes ``review_status``, ``responsible`` and comments. No
path here lets the first touch the second, and the timeline keeps both in one
order while marking which is which
(:data:`app.invoices.models.HUMAN_EVENT_KINDS`).

**Nor can it silently overwrite itself.** A run that replaces the engine's own
open findings writes down what it replaced, what it read, and under which
rules (:mod:`app.invoices.audit`). "Nobody had formally decided on it" is not
the same as "nobody was working from it", so the superseded version stays
findable in the audit trail even though it stops being a card on the screen.

**Where this stops.** The lock is a threading lock over one process's cached
per-tenant :class:`~app.store.Store`, which is the concurrency model this whole
backend already has (see :mod:`app.integrations.store`). It makes concurrent
requests safe; it would not make two *processes* safe. The deterministic id
still holds there — two processes cannot create duplicate cases — but a
simultaneous comment from each could still lose one. Saying so is cheaper than
implying a guarantee the file layout cannot give.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable

from ..integrations.models import (
    InvoiceSnapshot,
    ReviewFinding,
    SourceEvent,
    finding_content_key,
    utc_now_iso,
)
from ..integrations.review import review_invoice
from ..integrations.supplier import normalize as normalize_supplier
from ..store import Store
from . import audit, compare
from .identity import case_key_for, email_basis
from .models import (
    ENGINE,
    REVIEW_REASON_REQUIRED,
    REVIEW_STATUS_LABELS,
    SIGNAL_LABELS,
    AnalysisRun,
    CaseEvent,
    CaseObservation,
    CaseSignal,
    InvoiceCase,
    SourceRecordStatus,
)

logger = logging.getLogger("brf.invoices.cases")


class CaseError(ValueError):
    """The case cannot be changed as asked, and the message says why."""


def case_id_for(tenant_id: str, case_key: str) -> str:
    """The case's identity, derived rather than minted.

    Deriving it is what makes every write idempotent: the store upserts on
    ``id``, so two requests that independently decide the same invoice needs a
    case converge on one row. A random id would make them two rows, and no
    amount of locking downstream would merge them afterwards.

    The tenant is in the digest so two associations that happen to share a
    supplier and an invoice number never share an id — the stores are already
    separate, but an id that collided across them would be a trap for any
    future code that looked one up without its tenant.
    """
    digest = hashlib.sha256(f"{tenant_id}\x00{case_key}".encode("utf-8")).hexdigest()
    return digest[:12]


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def _machine_event(
    kind: str,
    *,
    at: str,
    summary: str,
    dedupe_key: str,
    ref_id: str = "",
    note: str = "",
    by: str = ENGINE,
) -> CaseEvent:
    """An entry a machine wrote, reproducible from the data it describes.

    Both the id and the timestamp are derived, not generated. That is what lets
    the same entry be *computed* during a pure projection and later *persisted*
    by a write without the two disagreeing — and it means "källa kopplad" is
    stamped with when the source was actually read, rather than with when
    somebody happened to open the screen.
    """
    return CaseEvent(
        id=hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:12],
        at=at,
        by=by,
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        ref_id=ref_id,
        note=note,
        dedupe_key=dedupe_key,
    )


def _human_event(
    kind: str,
    *,
    by: str,
    summary: str,
    ref_id: str = "",
    note: str = "",
    from_value: str = "",
    to_value: str = "",
) -> CaseEvent:
    """An entry a person wrote. Never deduplicated: saying a thing twice is two acts."""
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
    )


# Causal order within one second. Timestamps here are second-resolution
# (:func:`app.integrations.models.utc_now_iso`), so ties are the normal case
# rather than the exception, and the tie-break is what the reader actually
# sees. It runs cause before effect: the case is opened before its sources are
# attached, the sources before the analysis that read them, the analysis before
# its findings, and all of that before a person reacts to any of it. Sorting
# alphabetically by kind instead would put "granskning körd" above "ärendet
# öppnat" and read as though the engine ran before the case existed.
_EVENT_ORDER: dict[str, int] = {
    "case_opened": 0,
    "observation_added": 1,
    "source_refreshed": 2,
    "analysis_run": 3,
    "finding_recorded": 4,
}
_HUMAN_RANK = 5


def _merged_timeline(stored: Iterable[CaseEvent], computed: Iterable[CaseEvent]) -> list[CaseEvent]:
    """What is on disk, plus anything the data implies that is not there yet.

    Sorted by time so the reader gets a chronology rather than a write order —
    a machine entry stamped with when the source was read belongs before a
    comment written this morning, whichever was persisted first.

    The sort is **stable** and the key deliberately excludes the id, so two
    entries the key cannot separate keep the order they were appended in. That
    is what makes two comments written in the same second read in the order
    they were actually written, instead of in the order their random ids happen
    to sort.
    """
    out = list(stored)
    seen = {event.dedupe_key for event in out if event.dedupe_key}
    for event in computed:
        if event.dedupe_key and event.dedupe_key in seen:
            continue
        if event.dedupe_key:
            seen.add(event.dedupe_key)
        out.append(event)
    return sorted(out, key=lambda e: (e.at, _EVENT_ORDER.get(e.kind, _HUMAN_RANK)))


# ---------------------------------------------------------------------------
# The pure projection
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
    events: list[SourceEvent], snapshot: InvoiceSnapshot
) -> list[CaseObservation]:
    """The mail this invoice arrived with, and the file that came in it.

    Both are observations of the same case, and neither replaces the other: the
    mail is the envelope with its sender, date and provenance, and the
    attachment is the original document — the thing the citation machinery can
    actually open. A rendered preview never stands in for either.
    """
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


def _project_case(
    *,
    tenant_id: str,
    case_key: str,
    basis: str,
    snapshots: list[InvoiceSnapshot],
    events: list[SourceEvent],
    findings: list[ReviewFinding],
    stored: InvoiceCase | None,
) -> InvoiceCase:
    """One case, computed from the records that imply it. Writes nothing.

    ``stored`` contributes exactly the fields a human owns — the review status
    and its note, who is responsible, and the timeline as persisted. Everything
    else is derived, so a case that has never been written to disk renders
    identically to one that has.
    """
    # Which reading the case describes itself by, when several converged on it:
    # the most recently retrieved, ties broken by id. It has to be decided the
    # same way every time or a supplier name would change under the reader
    # every time somebody pressed refresh.
    primary = max(snapshots, key=lambda s: (s.retrieved_at, s.id))

    observations: list[CaseObservation] = []
    for snapshot in snapshots:
        observations.append(_snapshot_observation(snapshot))
        observations.extend(_email_observations(events, snapshot))
    by_key = {(o.kind, o.ref_id): o for o in observations}
    order = {"accounting_snapshot": 0, "email": 1, "document": 2}
    observations = sorted(
        by_key.values(), key=lambda o: (order.get(o.kind, 9), o.occurred_at, o.ref_id)
    )

    computed = [
        _machine_event(
            "case_opened",
            at=min(s.retrieved_at for s in snapshots),
            summary=(
                f"Fakturaärende öppnat för {primary.supplier_name} "
                f"{primary.invoice_number or primary.external_ref}."
            ),
            note=basis,
            dedupe_key=f"open:{case_key}",
        )
    ]
    computed.extend(
        _machine_event(
            "observation_added",
            at=observation.retrieved_at or observation.occurred_at,
            summary=f"Källa kopplad: {observation.label}",
            ref_id=observation.ref_id,
            note=observation.basis,
            dedupe_key=f"obs:{observation.kind}:{observation.ref_id}",
        )
        for observation in observations
    )

    relevant = [f for f in findings if f.invoice_id == primary.id]
    base = stored or InvoiceCase(
        id=case_id_for(tenant_id, case_key),
        tenant_id=tenant_id,
        case_key=case_key,
        created_at=min(s.retrieved_at for s in snapshots),
    )
    return base.model_copy(
        update={
            "id": case_id_for(tenant_id, case_key),
            "tenant_id": tenant_id,
            "case_key": case_key,
            "identity_basis": basis,
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
            "signals": signals_for(relevant),
            "timeline": _merged_timeline(base.timeline if stored else [], computed),
        }
    )


def project(store: Store) -> list[InvoiceCase]:
    """Every invoice case this tenant's records imply. **Pure.**

    Reads four collections once each and joins them in memory. Nothing is
    written, so this is safe on a plain ``GET`` and safe to run concurrently —
    two callers compute the same answer and neither leaves a trace.
    """
    snapshots = store.integrations.list_invoices()
    if not snapshots:
        return []
    try:
        events = store.integrations.list_source_events()
    except Exception as exc:  # a broken queue must not take the workspace down
        logger.error("Kunde inte läsa källhändelser för fakturaärenden: %s", exc)
        events = []
    findings = store.integrations.list_findings()
    stored = {c.id: c for c in store.integrations.list_invoice_cases()}

    grouped: dict[str, tuple[str, list[InvoiceSnapshot]]] = {}
    for snapshot in snapshots:
        key, basis = case_key_for(snapshot)
        grouped.setdefault(key, (basis, []))[1].append(snapshot)

    # A re-read can *change* a case's identity: an invoice that arrived with no
    # number, and therefore keyed on its source reference, gets a real key the
    # day somebody fills the number in over in the accounting system. The
    # derived id moves with it, and without this the association's review notes
    # would be left on a row nothing points at any more.
    #
    # So a stored case is also findable by the reading it describes. This is
    # still a pure computation — the adoption happens in memory, and the row is
    # rewritten under the new id the next time somebody actually changes
    # something. Repairing it *by writing* during a read is exactly the thing
    # this module stopped doing.
    by_primary = {c.primary_invoice_id: c for c in stored.values() if c.primary_invoice_id}

    def _stored_for(key: str, rows: list[InvoiceSnapshot]) -> InvoiceCase | None:
        found = stored.get(case_id_for(store.tenant_id, key))
        if found is not None:
            return found
        for snapshot in rows:
            previous = by_primary.get(snapshot.id)
            if previous is not None:
                return previous
        return None

    cases = [
        _project_case(
            tenant_id=store.tenant_id,
            case_key=key,
            basis=basis,
            snapshots=rows,
            events=events,
            findings=findings,
            stored=_stored_for(key, rows),
        )
        for key, (basis, rows) in grouped.items()
    ]
    cases.sort(key=lambda c: c.last_activity_at(), reverse=True)
    return cases


def project_one(store: Store, case_id: str) -> InvoiceCase | None:
    """One projected case by id, or ``None``. **Pure.**"""
    return next((c for c in project(store) if c.id == case_id), None)


# ---------------------------------------------------------------------------
# The only writer
# ---------------------------------------------------------------------------


def mutate(
    store: Store, case_id: str, apply: Callable[[InvoiceCase], InvoiceCase]
) -> InvoiceCase:
    """Change one case, safely against every other request.

    The lock is held across the whole read-modify-write, and the version handed
    to ``apply`` is projected *inside* it — so a caller that read the case a
    second ago cannot write back a version that has since been commented on.
    The deterministic id means the write is an upsert onto one row no matter
    how many callers decide the case needs creating at the same moment.
    """
    with store.integrations.lock:
        current = project_one(store, case_id)
        if current is None:
            raise CaseError("Okänt fakturaärende.")
        return store.integrations.upsert_invoice_case(apply(current))


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


def analysis_runs(store: Store, case: InvoiceCase) -> list[AnalysisRun]:
    """The case's recorded analyses, newest first — how a reader looks at them."""
    return list(reversed(store.integrations.list_analysis_runs(case.primary_invoice_id)))


def analyse_case(store: Store, case_id: str) -> InvoiceCase:
    """Run both engines over the case's invoice and record what came out.

    Held under the same lock as every other write, because it replaces
    findings, writes an audit record and appends to the timeline, and those
    three must not be observed half-done.

    Open findings are replaced; findings a human already decided on are kept
    untouched by :meth:`IntegrationStore.replace_findings_for_invoice`. Nothing
    a human wrote on the *case* is touched at all.

    **Replaced is not gone.** A run that changes anything is written down as an
    :class:`~app.invoices.models.AnalysisRun`: which reading it was built on,
    which rules produced it, what differed from the previous run in plain
    Swedish, and the superseded findings themselves. An open finding may have
    been the reason somebody rang the supplier even though nobody ever formally
    decided on it, so replacing it silently would be this product rewriting its
    own conclusions. A run that reproduces the previous one exactly is not a
    version and is not recorded — see :mod:`app.invoices.audit`.
    """
    with store.integrations.lock:
        case = project_one(store, case_id)
        if case is None:
            raise CaseError("Okänt fakturaärende.")
        snapshot = store.integrations.get_invoice(case.primary_invoice_id)
        if snapshot is None:
            raise CaseError("Ärendet har ingen inläst faktura att granska.")

        history = store.integrations.list_invoices()
        keys = {row.id: case_key_for(row)[0] for row in history}

        # Captured before anything is written: this is the version about to be
        # replaced, and after the write it is not recoverable from the store.
        before = findings_for_invoice(store, snapshot.id)
        open_before = [f for f in before if f.status == "open"]
        kept = [f for f in before if f.status != "open"]
        decided_keys = {finding_content_key(f) for f in kept}

        produced = list(review_invoice(store, snapshot))
        produced.extend(
            compare.analyse_history(
                snapshot, history, case=case, key_of=lambda row: keys.get(row.id, "")
            )
        )
        already_decided = [f for f in produced if finding_content_key(f) in decided_keys]
        written = store.integrations.replace_findings_for_invoice(snapshot.id, produced)

        at = utc_now_iso()
        run = audit.build_run(
            case=case,
            snapshot=snapshot,
            previous=store.integrations.latest_analysis_run(snapshot.id),
            open_before=open_before,
            kept=kept,
            written=written,
            already_decided=already_decided,
            at=at,
        )
        if run is not None:
            run = store.integrations.append_analysis_run(run)

        findings = findings_for_invoice(store, snapshot.id)
        signals = signals_for(findings)
        events: list[CaseEvent] = []
        if run is not None:
            # Only when there was a run to record. A refresh that read the same
            # bytes and reached the same conclusion has nothing to say, and a
            # timeline entry saying it would push the entries that do matter
            # off the top of the panel.
            events.append(
                _machine_event(
                    "analysis_run",
                    at=at,
                    summary=(
                        f"Granskning körd (version {run.sequence}): {len(findings)} fynd, "
                        + (
                            ", ".join(s.label for s in signals)
                            if signals
                            else "ingen signal att lyfta"
                        )
                        + "."
                    ),
                    note=(
                        f"{run.summary} Källversion: {snapshot.adapter} "
                        f"{snapshot.external_ref}, läst {snapshot.retrieved_at}, "
                        f"innehållshash {snapshot.content_sha256[:16]}…. "
                        f"Regelversion: {run.engine} {run.engine_version}."
                    ),
                    ref_id=run.id,
                    dedupe_key=f"analysis:{run.id}",
                )
            )
        events.extend(
            _machine_event(
                "finding_recorded",
                at=at,
                summary=f"{f.verdict_label}: {f.suggestion[:160]}",
                ref_id=f.id,
                by=f.suggested_by or ENGINE,
                dedupe_key="finding:"
                + hashlib.sha256(finding_content_key(f).encode("utf-8")).hexdigest()[:16],
            )
            for f in findings
        )
        # Re-project so the freshly written findings are reflected, then append.
        case = project_one(store, case_id) or case
        stamp = (
            {
                # When *these* findings were produced, not when somebody last
                # pressed a button that changed nothing.
                "analysis_at": run.ran_at,
                "analysis_run_id": run.id,
                "analysis_sequence": run.sequence,
                "analysis_engine_version": run.engine_version,
            }
            if run is not None
            else {}
        )
        return store.integrations.upsert_invoice_case(
            case.model_copy(
                update={
                    "signals": signals,
                    **stamp,
                    "timeline": _merged_timeline(case.timeline, events),
                }
            )
        )


# ---------------------------------------------------------------------------
# What people do
# ---------------------------------------------------------------------------


def set_review_status(
    store: Store, case_id: str, *, status: str, note: str, user_id: str
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

    def apply(case: InvoiceCase) -> InvoiceCase:
        if status == case.review_status and not reason:
            raise CaseError("Statusen är redan satt till det. Inget att spara.")
        return case.model_copy(
            update={
                "review_status": status,
                "review_status_note": reason,
                "review_status_by": user_id,
                "review_status_at": utc_now_iso(),
                "timeline": [
                    *case.timeline,
                    _human_event(
                        "status_changed",
                        by=user_id,
                        summary=f"Granskningsstatus: {REVIEW_STATUS_LABELS[status]}",
                        from_value=REVIEW_STATUS_LABELS[case.review_status],
                        to_value=REVIEW_STATUS_LABELS[status],
                        note=reason,
                    ),
                ],
            }
        )

    return mutate(store, case_id, apply)


def assign(store: Store, case_id: str, *, responsible: str, user_id: str) -> InvoiceCase:
    name = (responsible or "").strip()

    def apply(case: InvoiceCase) -> InvoiceCase:
        if name == case.responsible:
            raise CaseError("Ansvarig är redan satt till det.")
        return case.model_copy(
            update={
                "responsible": name,
                "timeline": [
                    *case.timeline,
                    _human_event(
                        "assigned",
                        by=user_id,
                        summary=f"Ansvarig: {name or 'ej utsedd'}",
                        from_value=case.responsible,
                        to_value=name,
                    ),
                ],
            }
        )

    return mutate(store, case_id, apply)


def comment(store: Store, case_id: str, *, text: str, user_id: str) -> InvoiceCase:
    """Say something about the invoice without changing anything about it."""
    said = (text or "").strip()
    if not said:
        raise CaseError("Tom kommentar.")

    def apply(case: InvoiceCase) -> InvoiceCase:
        return case.model_copy(
            update={
                "timeline": [
                    *case.timeline,
                    _human_event("commented", by=user_id, summary=said[:160], note=said),
                ]
            }
        )

    return mutate(store, case_id, apply)


def note_task(store: Store, case_id: str, *, task, user_id: str) -> InvoiceCase:
    """Put the work somebody took on into the case's own history."""

    def apply(case: InvoiceCase) -> InvoiceCase:
        return case.model_copy(
            update={
                "timeline": [
                    *case.timeline,
                    _human_event(
                        "task_created",
                        by=user_id,
                        summary=f"Uppgift skapad: {task.title}",
                        ref_id=task.id,
                        note=f"Ansvarig: {task.responsible or 'ej utsedd'}",
                    ),
                ]
            }
        )

    return mutate(store, case_id, apply)


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
    cases = [c for c in project(store) if c.supplier_key == key and c.id != case.id]
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

    org_numbers = sorted({c.supplier_ref for c in [case, *cases] if c.supplier_ref})

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
        "amountOpen": str(sum((c.total_amount or Decimal(0) for c in openish), Decimal(0))),
    }


__all__ = [
    "CaseError",
    "analyse_case",
    "analysis_runs",
    "assign",
    "case_id_for",
    "comment",
    "documents_for",
    "findings_for_invoice",
    "mutate",
    "note_task",
    "project",
    "project_one",
    "set_review_status",
    "signals_for",
    "supplier_context",
    "totals",
]
