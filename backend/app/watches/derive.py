"""Turning what a contract says about time into dates a board can act on.

The engine reads the tenant's own documents and proposes watches. Every
proposal satisfies three conditions, and a candidate that fails any one of them
does not become a watch:

1. the passage verifies **verbatim** through :func:`app.citations.resolve_citation`;
2. the due date is *computed*, not guessed — from a date that is written in the
   document, with the arithmetic recorded in ``derivation``;
3. the obligation is one of the kinds a board has a routine for.

Condition 2 is the one that does the work. "Uppsägning ska ske senast tre
månader före avtalstidens utgång" is a perfectly clear sentence and an
impossible watch: there is no date in it. Guessing which date "avtalstidens
utgång" refers to would produce a calendar entry that looks exactly like a
correct one, which is the worst possible failure for a feature whose entire
value is that the board can trust it. That clause becomes an
:class:`~app.watches.models.UnresolvedObligation` instead — a real answer,
which the board can resolve by supplying the missing fact.

**What is scanned.** The association's own archive: uploaded documents, and
attachments a named administrator adopted (the same evidence rule the invoice
review uses — see :func:`app.integrations.review.unadopted_incoming_document_ids`).
Material still sitting in the queue is not the association's yet.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date

from .. import terms as terms_mod
from ..citations import Rejected, Resolved, resolve_citation
from ..schemas import Chunk, CitationOut
from ..store import Store
from .models import (
    Recurrence,
    UnresolvedObligation,
    Watch,
    WatchKind,
)

logger = logging.getLogger("brf.watches.derive")

# Words of context kept around a matched clause. A watch card shows this, so it
# has to carry the sentence — a bare "tre månader" proves nothing to a reader.
QUOTE_WINDOW_BEFORE = 16
QUOTE_WINDOW_AFTER = 14

# How far from an obligation word a date or duration may sit and still be about
# it. One sentence, give or take.
OBLIGATION_REACH = 25

# The vocabulary. Kept here rather than in `terms.py` because these are the
# things a *board* has routines for; reading a duration is general, knowing
# that "OVK" is an obligation is domain.
NOTICE_WORDS = frozenset(
    {"uppsägning", "uppsagning", "uppsägas", "sägas", "sagas", "uppsägningstid", "uppsagningstid"}
)
RENEWAL_WORDS = frozenset(
    {"förlängs", "forlangs", "förlängning", "forlangning", "förnyas", "fornyas", "prolongeras"}
)
WARRANTY_WORDS = frozenset({"garanti", "garantitid", "garantitiden", "garantiåtagande", "ansvarstid"})
INSPECTION_WORDS = frozenset(
    {
        "besiktning",
        "besiktigas",
        "slutbesiktning",
        "garantibesiktning",
        "ovk",
        "ventilationskontroll",
        "energideklaration",
        "brandskyddskontroll",
        "sotning",
        "radonmätning",
        "radonmatning",
        "hissbesiktning",
        "revisionsbesiktning",
    }
)
RECURRING_DUTY_WORDS = frozenset(
    {
        "service",
        "underhåll",
        "underhall",
        "avläsning",
        "avlasning",
        "rapport",
        "redovisning",
        "kontroll",
        "tillsyn",
        "provtryckning",
        "filterbyte",
    }
)

# A date that is the end of something, rather than a date in passing.
_END_CONTEXT = frozenset(
    {
        "utgång",
        "utgang",
        "utgången",
        "upphör",
        "upphor",
        "upphörande",
        "till",
        "t.o.m",
        "t.o.m.",
        "tom",
        "senast",
        "före",
        "fore",
        "slutar",
        "löper",
        "loper",
        "ut",
    }
)

_EDGE_PUNCT = " \t()[]{}.,;:!?\"'§•· "


def _clean(token: str) -> str:
    return token.strip().strip(_EDGE_PUNCT)


def _lower(token: str) -> str:
    return _clean(token).casefold()


@dataclass
class _Page:
    """One chunk with the page words it covers, ready to be read and cited."""

    chunk: Chunk
    words: list[str]
    start: int
    end: int

    @property
    def usable(self) -> bool:
        return self.end >= self.start

    def slice(self) -> list[str]:
        return self.words[self.start : self.end + 1]

    def quote_for(self, span: terms_mod.Span) -> str:
        a = max(self.start, self.start + span.start - QUOTE_WINDOW_BEFORE)
        b = min(self.end, self.start + span.end + QUOTE_WINDOW_AFTER)
        return " ".join(self.words[a : b + 1]).strip()


def _pages_of(store: Store, document_id: str) -> list[_Page]:
    out: list[_Page] = []
    pages = store.pages.get(document_id) or []
    for chunk in store.chunks.values():
        if chunk.document_id != document_id:
            continue
        page = pages[chunk.page - 1] if 1 <= chunk.page <= len(pages) else None
        if page is None:
            continue
        words = [w.text for w in page.words]
        candidate = _Page(
            chunk=chunk,
            words=words,
            start=max(0, chunk.word_start),
            end=min(len(words) - 1, chunk.word_end) if words else -1,
        )
        if candidate.usable:
            out.append(candidate)
    return sorted(out, key=lambda p: (p.chunk.page, p.start))


def _citation(store: Store, page: _Page, quote: str) -> CitationOut | None:
    result = resolve_citation(page.chunk, [quote], store.pages)
    if isinstance(result, Rejected):
        logger.debug("Citat avvisat (%s) för %s", result.reason, page.chunk.id)
        return None
    assert isinstance(result, Resolved)
    meta = store.documents.get(page.chunk.document_id)
    if meta is None:
        return None
    return CitationOut(
        document_id=page.chunk.document_id,
        document_name=meta.name,
        page=result.page,
        quote=quote,
        quotes=[quote],
        chunk_id=page.chunk.id,
        rects=result.rects,
        score=1.0,
        approximate=meta.source == "scanned",
        corpus_origin=meta.corpus_origin,
    )


def reviewable_document_ids(store: Store) -> list[str]:
    """The association's own archive: uploaded, or adopted out of the queue."""
    try:
        from ..integrations.review import unadopted_incoming_document_ids

        excluded = unadopted_incoming_document_ids(store)
    except Exception as exc:  # a broken queue must not silently widen the scan
        logger.error("Kunde inte läsa köns bilagor för uteslutning: %s", exc)
        raise
    return [doc_id for doc_id in store.documents if doc_id not in excluded]


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


@dataclass
class _Proposal:
    kind: WatchKind
    title: str
    due: str
    derivation: str
    span: terms_mod.Span
    recurrence: Recurrence = "none"


def _near(span: terms_mod.Span, words: list[str], vocabulary: frozenset[str]) -> bool:
    lo = max(0, span.start - OBLIGATION_REACH)
    hi = min(len(words), span.end + OBLIGATION_REACH + 1)
    return any(_lower(w) in vocabulary for w in words[lo:hi])


def _end_flavoured(span: terms_mod.Span, words: list[str]) -> bool:
    lo = max(0, span.start - 5)
    return any(_lower(w) in _END_CONTEXT for w in words[lo : span.start + 1])


def _propose_notice(words: list[str]) -> list[_Proposal]:
    """"senast tre månader före den 31 december 2026" → a date to act by."""
    out: list[_Proposal] = []
    for deadline in terms_mod.scan_relative_deadlines(words):
        if not (
            _near(deadline.span, words, NOTICE_WORDS)
            or _near(deadline.span, words, RENEWAL_WORDS)
        ):
            continue
        due = deadline.resolve()
        renews = _near(deadline.span, words, RENEWAL_WORDS)
        title = (
            f"Säg upp eller ompröva avtalet senast {terms_mod.svenskt_datum(due)}"
            if renews
            else f"Uppsägning måste ske senast {terms_mod.svenskt_datum(due)}"
        )
        out.append(
            _Proposal(
                kind="notice_deadline",
                title=title,
                due=due,
                derivation=f"{terms_mod.svenskt_datum(deadline.anchor_iso)} minus {deadline.human().split(' före ')[0]}",
                span=deadline.span,
            )
        )
    return out


def _propose_notice_from_period(words: list[str]) -> list[_Proposal]:
    """"…till och med den 31 januari 2028. … senast sex månader före avtalstidens utgång."

    The commonest shape in a Swedish agreement, and the one that costs a board
    the most when it is missed: the end date is stated, the notice period is
    stated, and they are in different sentences with "avtalstidens utgång"
    standing between them instead of a date.

    :func:`app.terms.scan_relative_deadlines` will not touch this, and it is
    right not to — its anchor must be a date the clause points at directly.
    This rule resolves the phrase instead, under conditions narrow enough that
    the resolution is a reading rather than a guess:

    * a **closed** agreement period verified in the same passage;
    * a notice period stated **after** it;
    * the notice clause explicitly pointing at the end of a term — "utgång",
      "upphörande", "avtalstidens slut" — rather than at nothing in particular.

    What it assumed is written into ``derivation``, in full, so the one
    inference here is the one thing a reader is told first.
    """
    out: list[_Proposal] = []
    periods = [p for p in terms_mod.scan_periods(words) if p.end_iso and not p.open_ended]
    if not periods:
        return out
    for notice in terms_mod.scan_notice_periods(words):
        end_word_at = None
        for j in range(notice.span.end, min(len(words), notice.span.end + 6)):
            if _lower(words[j]) in {"utgång", "utgang", "utgången", "utgangen", "upphörande", "upphorande", "slut", "slutet"}:
                end_word_at = j
                break
        if end_word_at is None:
            continue
        period = next((p for p in periods if p.span.end < notice.span.start), None)
        if period is None:
            continue
        anchor = terms_mod.parse_iso(period.end_iso)
        if anchor is None:  # pragma: no cover - end_iso is always parseable
            continue
        due = terms_mod.shift(anchor, -notice.count, notice.unit).isoformat()
        unit = {"month": "månader", "year": "år", "week": "veckor"}[notice.unit]
        out.append(
            _Proposal(
                kind="notice_deadline",
                title=f"Säg upp eller ompröva avtalet senast {terms_mod.svenskt_datum(due)}",
                due=due,
                derivation=(
                    f"avtalstidens utgång {terms_mod.svenskt_datum(period.end_iso)} enligt citerad avtalstid "
                    f"{period.human()}, minus {notice.count} {unit}"
                ),
                span=period.span.merged_with(terms_mod.Span(notice.span.start, end_word_at)),
            )
        )
    return out


def _propose_expiry(words: list[str], already: set[str]) -> list[_Proposal]:
    """A closed agreement period's end date, when no notice deadline covers it.

    Deliberately second in line: when a contract states both, the notice
    deadline is the date somebody has to do something by, and putting the
    expiry beside it would give a board two entries for one obligation.
    """
    if already:
        return []
    out: list[_Proposal] = []
    for period in terms_mod.scan_periods(words):
        if period.end_iso is None or period.open_ended:
            continue
        out.append(
            _Proposal(
                kind="expiry",
                title=f"Avtalet upphör {terms_mod.svenskt_datum(period.end_iso)}",
                due=period.end_iso,
                derivation=f"citerad avtalstid {period.human()}",
                span=period.span,
            )
        )
    return out


def _propose_warranty(words: list[str]) -> list[_Proposal]:
    """"garantitid fem år från slutbesiktningen 2024-05-12"."""
    out: list[_Proposal] = []
    for deadline in terms_mod.scan_relative_deadlines(words):
        if deadline.before or not _near(deadline.span, words, WARRANTY_WORDS):
            continue
        due = deadline.resolve()
        out.append(
            _Proposal(
                kind="warranty",
                title=f"Garantitiden går ut {terms_mod.svenskt_datum(due)}",
                due=due,
                derivation=f"{terms_mod.svenskt_datum(deadline.anchor_iso)} plus {deadline.human().split(' efter ')[0]}",
                span=deadline.span,
            )
        )
    return out


def _propose_inspection(words: list[str]) -> list[_Proposal]:
    """An inspection with a date of its own, and one that recurs from a date."""
    out: list[_Proposal] = []
    recurrences = terms_mod.scan_recurrence(words)
    for hit in terms_mod.scan_dates(words):
        if not _near(hit.span, words, INSPECTION_WORDS):
            continue
        cycle: Recurrence = "none"
        for recurrence in recurrences:
            if hit.span.distance_to(recurrence.span) <= OBLIGATION_REACH:
                cycle = recurrence.every  # type: ignore[assignment]
                break
        # A date that is plainly the *last* one done is still the anchor a
        # recurring obligation counts from; a one-off keeps its own date.
        due = hit.iso
        if cycle != "none":
            from .models import RECURRENCE_STEPS

            count, unit = RECURRENCE_STEPS[cycle]
            due = terms_mod.shift(terms_mod.parse_iso(hit.iso), count, unit).isoformat()
        out.append(
            _Proposal(
                kind="inspection",
                title=(
                    f"Besiktning eller kontroll senast {terms_mod.svenskt_datum(due)}"
                    if cycle == "none"
                    else f"Återkommande kontroll, nästa gång {terms_mod.svenskt_datum(due)}"
                ),
                due=due,
                derivation=(
                    f"citerat datum {terms_mod.svenskt_datum(hit.iso)}"
                    if cycle == "none"
                    else f"{terms_mod.svenskt_datum(hit.iso)} plus ett intervall "
                    f"({terms_mod.RECURRENCE_HUMAN[cycle]})"
                ),
                span=hit.span,
                recurrence=cycle,
            )
        )
    return out


def _propose_recurring_duty(words: list[str]) -> list[_Proposal]:
    """"Avläsning sker kvartalsvis med start 2026-01-31"."""
    out: list[_Proposal] = []
    dates = terms_mod.scan_dates(words)
    for recurrence in terms_mod.scan_recurrence(words):
        if not _near(recurrence.span, words, RECURRING_DUTY_WORDS):
            continue
        anchor = next(
            (h for h in dates if recurrence.span.distance_to(h.span) <= OBLIGATION_REACH), None
        )
        if anchor is None:
            continue
        from .models import RECURRENCE_STEPS

        count, unit = RECURRENCE_STEPS[recurrence.every]
        due = terms_mod.shift(terms_mod.parse_iso(anchor.iso), count, unit).isoformat()
        out.append(
            _Proposal(
                kind="recurring_obligation",
                title=f"Återkommande skyldighet, nästa gång {terms_mod.svenskt_datum(due)}",
                due=due,
                derivation=f"{terms_mod.svenskt_datum(anchor.iso)} plus ett intervall ({recurrence.human()})",
                span=recurrence.span.merged_with(anchor.span),
                recurrence=recurrence.every,  # type: ignore[arg-type]
            )
        )
    return out


def _unresolved(words: list[str], dated_spans: list[terms_mod.Span]) -> list[tuple[terms_mod.Span, str, str]]:
    """Time limits that were read and could not be dated.

    Only reported when the clause is not already covered by a proposal on the
    same passage — otherwise every successful derivation would also produce a
    complaint about itself.
    """
    out: list[tuple[terms_mod.Span, str, str]] = []

    def covered(span: terms_mod.Span) -> bool:
        return any(span.distance_to(other) <= 3 for other in dated_spans)

    for notice in terms_mod.scan_notice_periods(words):
        if covered(notice.span):
            continue
        # notice.human() ends in the word "uppsägningstid" itself, so using it
        # after the label said the same word twice in a row.
        enhet = {"month": "månader", "year": "år", "week": "veckor"}[notice.unit]
        out.append(
            (
                notice.span,
                f"Uppsägningstid: {notice.count} {enhet}",
                "Klausulen anger hur lång uppsägningstiden är, men inte vilket datum den "
                "räknas från. Fyll i avtalets slutdatum för att få en bevakning.",
            )
        )
    for duration in terms_mod.scan_durations(words):
        if covered(duration.span) or not duration.anchor:
            continue
        out.append(
            (
                duration.span,
                f"Avtalstid: {duration.human()}",
                f"Löptiden räknas från {duration.anchor}, och det datumet står inte i den "
                "citerade passagen. Fyll i det för att få en bevakning.",
            )
        )
    return out


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    watches: list[Watch]
    unresolved: list[UnresolvedObligation]
    documents_read: int


def scan_documents(store: Store, *, now_iso: str) -> ScanResult:
    """Read every document in the archive and propose what can be dated."""
    watches: list[Watch] = []
    unresolved: list[UnresolvedObligation] = []
    documents = reviewable_document_ids(store)

    for document_id in documents:
        meta = store.documents.get(document_id)
        for page in _pages_of(store, document_id):
            words = page.slice()
            notice = _propose_notice(words) + _propose_notice_from_period(words)
            proposals = (
                notice
                + _propose_expiry(words, {p.title for p in notice})
                + _propose_warranty(words)
                + _propose_inspection(words)
                + _propose_recurring_duty(words)
            )
            dated_spans = [p.span for p in proposals]

            for proposal in proposals:
                quote = page.quote_for(proposal.span)
                citation = _citation(store, page, quote)
                if citation is None:
                    # The span did not verify verbatim. A watch whose evidence
                    # cannot be opened is a claim, so it is dropped rather than
                    # shown without its source.
                    continue
                watches.append(
                    Watch(
                        id=uuid.uuid4().hex[:12],
                        tenant_id=store.tenant_id,
                        kind=proposal.kind,
                        status="proposed",
                        title=proposal.title,
                        due_date=proposal.due,
                        derived_due_date=proposal.due,
                        derivation=proposal.derivation,
                        recurrence=proposal.recurrence,
                        citations=[citation],
                        source_document_id=document_id,
                        source_document_name=meta.name if meta else "",
                        created_at=now_iso,
                    )
                )

            for span, what, why in _unresolved(words, dated_spans):
                quote = page.quote_for(span)
                citation = _citation(store, page, quote)
                if citation is None:
                    continue
                unresolved.append(
                    UnresolvedObligation(
                        id=uuid.uuid4().hex[:12],
                        tenant_id=store.tenant_id,
                        what=what,
                        why=why,
                        citations=[citation],
                        source_document_id=document_id,
                        source_document_name=meta.name if meta else "",
                        created_at=now_iso,
                    )
                )

    return ScanResult(
        watches=_deduplicate(watches),
        unresolved=_deduplicate_unresolved(unresolved),
        documents_read=len(documents),
    )


def _deduplicate(watches: list[Watch]) -> list[Watch]:
    """One obligation per (document, kind, date).

    A clause that spans two chunks is read twice, and a contract that repeats
    its own notice period in a summary paragraph states it twice. Neither is
    two obligations, and a board that is shown the same deadline three times
    learns to skim the list.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[Watch] = []
    for watch in watches:
        key = (watch.source_document_id, watch.kind, watch.due_date)
        if key in seen:
            continue
        seen.add(key)
        out.append(watch)
    return out


def _deduplicate_unresolved(rows: list[UnresolvedObligation]) -> list[UnresolvedObligation]:
    seen: set[tuple[str, str]] = set()
    out: list[UnresolvedObligation] = []
    for row in rows:
        key = (row.source_document_id, row.what)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


__all__ = ["ScanResult", "reviewable_document_ids", "scan_documents"]
