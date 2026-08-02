"""What a re-analysis replaced, and what the difference was.

The engine's open findings are replaced on every run. This module is what
keeps that from being a silent overwrite: it compares what the engine says now
against what it said last time, writes the difference in plain Swedish, and
carries the superseded findings along with the run that superseded them.

Everything here is **pure**. :func:`build_run` is handed the previous run, the
findings that were on the invoice before, and the ones the engine just
produced, and returns the record — or ``None`` when there is nothing to
record. The writing happens in one place, under one lock, in
:func:`app.invoices.cases.analyse_case`.

**When a run is a version.** A run is written down when any of three things
differs from the previous recorded run:

* the **reading** it was built on (the invoice's content hash changed in the
  source system),
* the **result** it produced (any finding added, removed or reworded),
* the **rules** that produced it (:data:`ANALYSIS_ENGINE_VERSION`).

A run that matches the previous one on all three is not a version of anything.
Recording it anyway would fill the audit trail with rows that say "somebody
pressed refresh", which is exactly the noise that hides the rows that say
"this conclusion changed" — and it would break the workspace's idempotency
promise, where pressing refresh twice leaves the records it left once.

**How two runs are compared.** Findings are matched by what they *say*
(:func:`app.integrations.models.finding_content_key`), not by id — an engine
mints fresh ids every run, so matching on those would make every re-run look
like a wholesale replacement. What is left over after the identical pairs are
struck out is then paired *within one finding type, and only when there is
exactly one on each side*: that is the case where "the comparison against the
previous invoice changed" is a fact rather than a guess. Anything else is
reported as one finding gone and another arrived, because deciding which of
three duplicates became which of two others would be this module inventing a
history nobody recorded.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from ..integrations.models import (
    ANCHOR_LABELS,
    FINDING_TYPE_LABELS,
    VERDICT_LABELS,
    ReviewFinding,
    finding_content_key,
)
from .models import (
    ANALYSIS_ENGINE_VERSION,
    ENGINE,
    AnalysisChange,
    AnalysisRun,
    AnalysisSource,
    FactChange,
    InvoiceCase,
)


def type_label(finding_type: str) -> str:
    return FINDING_TYPE_LABELS.get(finding_type, finding_type)


def source_of(snapshot) -> AnalysisSource:
    """The reading a run was built on, as a record that outlives the snapshot."""
    return AnalysisSource(
        invoice_id=snapshot.id,
        adapter=snapshot.adapter,
        external_ref=snapshot.external_ref,
        source_dataset=snapshot.source_dataset,
        content_sha256=snapshot.content_sha256,
        retrieved_at=snapshot.retrieved_at,
    )


def result_fingerprint(findings: list[ReviewFinding]) -> str:
    """What a run said, independent of when it said it or under which ids."""
    payload = "|".join(sorted(finding_content_key(f) for f in findings))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run_id_for(
    tenant_id: str,
    invoice_id: str,
    *,
    engine_version: str,
    source: str,
    result: str,
    supersedes: str,
) -> str:
    """A run's identity, derived from what it is rather than minted.

    ``supersedes`` is in the digest so a result that comes back — run 3 landing
    on exactly what run 1 said — is a third row rather than a silent overwrite
    of the first. Without it the two would share an id, and an append-only
    store would either refuse the write or lose run 2's place in the chain.
    """
    raw = "\x00".join(
        [tenant_id, invoice_id, engine_version, source, result, supersedes]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# The diff
# ---------------------------------------------------------------------------


def _unmatched(mine: list[ReviewFinding], theirs: list[ReviewFinding]) -> list[ReviewFinding]:
    """Everything in ``mine`` the other side does not also say, counting duplicates."""
    available = Counter(finding_content_key(f) for f in theirs)
    out: list[ReviewFinding] = []
    for finding in mine:
        key = finding_content_key(finding)
        if available[key]:
            available[key] -= 1
        else:
            out.append(finding)
    return out


def _fact_map(finding: ReviewFinding) -> dict[str, str]:
    """The finding's verified values, keyed so repeats stay separate.

    A finding may carry several facts under one label — ``new_line_finding``
    writes one "Ny rad" per line — so the second and later ones are numbered
    rather than collapsed into the first. Collapsing them would report two rows
    becoming three as no change at all.
    """
    seen: Counter[str] = Counter()
    out: dict[str, str] = {}
    for fact in finding.verified_facts:
        seen[fact.label] += 1
        key = fact.label if seen[fact.label] == 1 else f"{fact.label} ({seen[fact.label]})"
        out[key] = fact.value
    return out


def _anchor_words(strength: str | None) -> str:
    if not strength:
        return "ingen koppling"
    return ANCHOR_LABELS.get(strength, strength)


def _fact_changes(before: ReviewFinding, after: ReviewFinding) -> list[FactChange]:
    old, new = _fact_map(before), _fact_map(after)
    labels = list(old) + [label for label in new if label not in old]
    changes = [
        FactChange(label=label, from_value=old.get(label, ""), to_value=new.get(label, ""))
        for label in labels
        if old.get(label, "") != new.get(label, "")
    ]
    # Not a verified fact, but the same question: what is different now. How
    # firmly the document was tied to the supplier decides how much a finding
    # is worth, and somebody confirming a supplier name is the most common way
    # it changes — the reader should not have to infer that from a sentence
    # quietly losing its caveat.
    if before.anchor_strength != after.anchor_strength:
        changes.append(
            FactChange(
                label="Koppling till leverantören",
                from_value=_anchor_words(before.anchor_strength),
                to_value=_anchor_words(after.anchor_strength),
            )
        )
    return changes


def _changed(before: ReviewFinding, after: ReviewFinding) -> AnalysisChange:
    label = type_label(after.finding_type)
    facts = _fact_changes(before, after)
    if before.verdict != after.verdict:
        summary = (
            f"{label}: {VERDICT_LABELS[before.verdict]} → {VERDICT_LABELS[after.verdict]}."
        )
    elif facts:
        first = facts[0]
        summary = (
            f"{label}: {first.label} {first.from_value or '—'} → {first.to_value or '—'}."
            + (f" Och {len(facts) - 1} uppgift till." if len(facts) == 2 else "")
            + (f" Och {len(facts) - 1} uppgifter till." if len(facts) > 2 else "")
        )
    else:
        summary = (
            f"{label}: bedömningen står kvar ({VERDICT_LABELS[after.verdict]}), "
            "men formuleringen har ändrats."
        )
    return AnalysisChange(
        kind="changed",
        finding_type=after.finding_type,
        finding_type_label=label,
        summary=summary,
        from_verdict=before.verdict,
        to_verdict=after.verdict,
        from_text=before.suggestion,
        to_text=after.suggestion,
        fact_changes=facts,
        finding_id=after.id,
        replaced_finding_id=before.id,
    )


def _added(finding: ReviewFinding) -> AnalysisChange:
    """A finding this run says and the previous one did not.

    No fact list: every value in it is new, so listing them would be the
    finding itself repeated in a worse format — and the finding is on the
    screen. Facts are listed where they answer a question the reader cannot
    answer by looking, which is when one changed.
    """
    label = type_label(finding.finding_type)
    return AnalysisChange(
        kind="added",
        finding_type=finding.finding_type,
        finding_type_label=label,
        summary=f"Nytt fynd — {label}: {VERDICT_LABELS[finding.verdict]}.",
        to_verdict=finding.verdict,
        to_text=finding.suggestion,
        finding_id=finding.id,
    )


def _removed(finding: ReviewFinding) -> AnalysisChange:
    label = type_label(finding.finding_type)
    return AnalysisChange(
        kind="removed",
        finding_type=finding.finding_type,
        finding_type_label=label,
        summary=(
            f"{label} ({VERDICT_LABELS[finding.verdict]}) hittades inte den här gången. "
            "Det betyder att den här körningen inte kom fram till det — inte att det är avfärdat."
        ),
        from_verdict=finding.verdict,
        from_text=finding.suggestion,
        replaced_finding_id=finding.id,
    )


def diff_findings(
    before: list[ReviewFinding], after: list[ReviewFinding]
) -> list[AnalysisChange]:
    """What changed between two runs' findings. See the module docstring."""
    gone = _unmatched(before, after)
    fresh = _unmatched(after, before)

    by_type_gone: dict[str, list[ReviewFinding]] = defaultdict(list)
    by_type_fresh: dict[str, list[ReviewFinding]] = defaultdict(list)
    for finding in gone:
        by_type_gone[finding.finding_type].append(finding)
    for finding in fresh:
        by_type_fresh[finding.finding_type].append(finding)

    changes: list[AnalysisChange] = []
    for finding_type in sorted(set(by_type_gone) | set(by_type_fresh)):
        old = by_type_gone.get(finding_type, [])
        new = by_type_fresh.get(finding_type, [])
        if len(old) == 1 and len(new) == 1:
            changes.append(_changed(old[0], new[0]))
            continue
        changes.extend(_added(f) for f in new)
        changes.extend(_removed(f) for f in old)
    return changes


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _summarise(
    changes: list[AnalysisChange], *, source_changed: bool, first: bool, findings: int
) -> str:
    if first:
        return (
            f"Första inspelade granskningen: {findings} fynd."
            if findings
            else "Första inspelade granskningen: inga fynd."
        )
    counts = Counter(c.kind for c in changes)
    parts = [
        f"{counts[kind]} {word}"
        for kind, word in (
            ("added", "nytt fynd" if counts["added"] == 1 else "nya fynd"),
            ("changed", "ändrat fynd" if counts["changed"] == 1 else "ändrade fynd"),
            ("removed", "fynd borta"),
        )
        if counts[kind]
    ]
    if not parts:
        return (
            "Granskningen kördes mot en ny läsning av fakturan och kom fram till "
            "exakt samma sak som förra gången."
        )
    said = ", ".join(parts)
    return (
        f"Ersatte den föregående granskningen: {said}."
        + (" Fakturan hade lästs om ur källan sedan dess." if source_changed else "")
    )


def build_run(
    *,
    case: InvoiceCase,
    snapshot,
    previous: AnalysisRun | None,
    open_before: list[ReviewFinding],
    kept: list[ReviewFinding],
    written: list[ReviewFinding],
    already_decided: list[ReviewFinding],
    at: str,
) -> AnalysisRun | None:
    """The record of one analysis, or ``None`` when nothing changed.

    ``open_before`` is what this run replaces — the engine's own previous
    output, nobody's decision. ``written`` is what it left in its place.
    ``kept`` is what it was not allowed to touch: findings a person has
    approved, dismissed or corrected. ``already_decided`` is the part of the
    engine's output that repeats, word for word, something in ``kept``; those
    are not written a second time, because a decision covers the statement it
    was made about — and counting them here is what keeps that suppression
    visible instead of looking like the engine stopped saying it.

    The no-op test compares ``written`` against ``open_before``: the previous
    run's *output* is the invoice's live open set, not the ``replaced`` list on
    its own record. That is also why a human decision taken since the last run
    counts as a change — it removed something from the set the engine is now
    being compared against, and pretending otherwise would make the next run's
    diff describe a state nobody was ever looking at.
    """
    source = source_of(snapshot)
    result = result_fingerprint(written)
    source_changed = previous is not None and previous.source.fingerprint() != source.fingerprint()

    if (
        previous is not None
        and previous.engine_version == ANALYSIS_ENGINE_VERSION
        and not source_changed
        and result_fingerprint(open_before) == result
    ):
        return None

    first = previous is None
    # A first run against nothing changed nothing: every finding in it would be
    # listed as "new", which is the findings on the screen repeated in a worse
    # format. A first run that *did* replace something — findings written
    # before this trail existed — keeps its diff, because that is a
    # replacement and the whole point is that one is never silent.
    changes = [] if first and not open_before else diff_findings(open_before, written)
    return AnalysisRun(
        id=run_id_for(
            case.tenant_id,
            snapshot.id,
            engine_version=ANALYSIS_ENGINE_VERSION,
            source=source.fingerprint(),
            result=result,
            supersedes=previous.id if previous else "",
        ),
        tenant_id=case.tenant_id,
        case_id=case.id,
        invoice_id=snapshot.id,
        sequence=(previous.sequence + 1) if previous else 1,
        ran_at=at,
        engine=ENGINE,
        engine_version=ANALYSIS_ENGINE_VERSION,
        source=source,
        supersedes=previous.id if previous else "",
        supersedes_sequence=previous.sequence if previous else 0,
        source_changed=source_changed,
        finding_count=len(written),
        kept_count=len(kept),
        already_decided_count=len(already_decided),
        changes=changes,
        replaced=list(open_before),
        summary=_summarise(
            changes, source_changed=source_changed, first=first, findings=len(written)
        ),
        note=_note(first=first, replaced=open_before),
    )


def _note(*, first: bool, replaced: list[ReviewFinding]) -> str:
    """What the reader must not conclude from the run. Only what is true of it.

    A first run that replaced nothing must not carry a sentence about what it
    replaced — a note that describes something that did not happen is the
    quickest way to make a reader stop reading the notes.
    """
    parts = ["Fynden är förslag från en regelmotor, inte beslut."]
    if replaced:
        parts.append(
            "Det som ersatts ligger kvar här och går att läsa, men gäller inte längre "
            "som aktuell granskning."
        )
    if not first:
        parts.append("Ingenting en människa beslutat om har rörts av den här körningen.")
    elif replaced:
        parts.append(
            "Fynden som ersattes fanns redan när revisionshistoriken började föras — "
            "vilken körning som skrev dem är inte inspelat."
        )
    return " ".join(parts)


__all__ = [
    "build_run",
    "diff_findings",
    "result_fingerprint",
    "run_id_for",
    "source_of",
    "type_label",
]
