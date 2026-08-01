"""Reading the parts of a contract that are not numbers.

The first version of the review engine understood amounts and ISO dates, and
answered *kan inte verifieras* to everything else. That is the correct answer
to give when nothing comparable was found, but it was being given to clauses
that a reader can read perfectly well:

    "Avtalet gäller från den 1 november 2026 och tills vidare."
    "Avtalstiden är tolv (12) månader från undertecknande."
    "Priserna indexregleras årligen enligt SCB:s entreprenadindex E84."
    "Uppsägningstiden är tre månader."

Each of these carries information, and losing it costs a reviewer more than a
wrong guess would — because *kan inte verifieras* looks the same whether the
contract is silent or whether it said something this code could not read, and
those are very different situations for the person who has to act.

So this module reads them, and the review uses what it reads in three ways:

1. **An open-ended period is a period.** "från den 1 november 2026 och tills
   vidare" bounds an invoice period from below, and that is enough to say the
   invoice falls inside the agreement — with the termination caveat stated,
   because an open-ended agreement is exactly one that may have ended.

2. **An index clause forbids a confident deviation.** If the contract says the
   price is index-adjusted, then a cited base amount that differs from the
   invoice is not evidence of a deviation; it is evidence that the base amount
   is not the current amount. The verdict drops to *kan inte verifieras* and
   cites both the amount and the index clause, which is more useful than a
   "möjlig avvikelse" a reviewer has to disprove.

3. **A term that cannot be compared is still worth citing.** A relative
   duration with no known signing date, or a notice period, is reported as a
   verified fact with its citation. The answer stays *kan inte verifieras* and
   now says which clause it read and why it could not compare it.

Nothing here relaxes the verbatim rule. Every span this module finds is turned
into a citation through :func:`app.citations.resolve_citation` by the caller,
and a span that will not verify is dropped like any other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------------------
# Swedish dates
# ---------------------------------------------------------------------------

SWEDISH_MONTHS: dict[str, int] = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "mars": 3, "mar": 3,
    "april": 4, "apr": 4,
    "maj": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "augusti": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

SWEDISH_NUMBERS: dict[str, int] = {
    "en": 1, "ett": 1, "två": 2, "tva": 2, "tre": 3, "fyra": 4, "fem": 5,
    "sex": 6, "sju": 7, "åtta": 8, "atta": 8, "nio": 9, "tio": 10,
    "elva": 11, "tolv": 12, "arton": 18, "tjugofyra": 24, "trettiosex": 36,
}

# Words that mean "and then it keeps going". Two tokens in the corpus
# ("tills vidare"), so both spellings are matched as a phrase.
OPEN_ENDED_PHRASES: tuple[tuple[str, ...], ...] = (
    ("tills", "vidare"),
    ("tillsvidare",),
    ("löpande",),
    ("lopande",),
)

DURATION_UNITS: dict[str, str] = {
    "månad": "month", "månader": "month", "manad": "month", "manader": "month",
    "månaders": "month", "manaders": "month",
    "år": "year", "ar": "year", "års": "year", "ars": "year",
    "vecka": "week", "veckor": "week", "veckors": "week",
}

# What a relative duration is counted from, when the contract says.
DURATION_ANCHORS: dict[str, str] = {
    "undertecknande": "undertecknande",
    "undertecknandet": "undertecknande",
    "avtalets": "avtalsstart",
    "avtalsstart": "avtalsstart",
    "tillträde": "tillträde",
    "tilltrade": "tillträde",
    "leverans": "leverans",
    "start": "avtalsstart",
    "ikraftträdande": "ikraftträdande",
    "ikrafttradande": "ikraftträdande",
}

NOTICE_WORDS = frozenset({"uppsägningstid", "uppsagningstid", "uppsägningstiden", "uppsagningstiden", "uppsägning", "uppsagning", "säga", "saga"})

# An index clause is a claim that the printed price is not the current price.
INDEX_WORDS = frozenset(
    {
        "index",
        "indexreglering",
        "indexregleras",
        "indexreglerat",
        "indexreglerad",
        "indexuppräkning",
        "indexupprakning",
        "indexuppräknas",
        "kpi",
        "konsumentprisindex",
        "entreprenadindex",
        "faktorprisindex",
        "prisindex",
        "basmånad",
        "basmanad",
        "basindex",
        "omräkningsfaktor",
        "omrakningsfaktor",
    }
)
# "SCB" alone is an institution; it counts only next to an index word.
INDEX_SUPPORT_WORDS = frozenset({"scb", "statistiska", "centralbyrån", "centralbyran"})

PERIOD_START_WORDS = frozenset(
    {"från", "fran", "fr.o.m", "fr.o.m.", "fom", "gäller", "galler", "löper", "loper", "avser", "startar", "börjar", "borjar"}
)
PERIOD_END_WORDS = frozenset({"till", "t.o.m", "t.o.m.", "tom", "–", "-", "—", "och"})

_EDGE_PUNCT = " \t()[]{}.,;:!?\"'§•· "
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DIGITS = re.compile(r"^\d{1,4}$")
_PAREN_DIGITS = re.compile(r"^\(?(\d{1,3})\)?$")


def _clean(token: str) -> str:
    return token.strip().strip(_EDGE_PUNCT)


def _lower(token: str) -> str:
    return _clean(token).casefold()


@dataclass(frozen=True)
class Span:
    """A run of page words, inclusive of both ends."""

    start: int
    end: int


@dataclass(frozen=True)
class DateHit:
    span: Span
    iso: str


@dataclass(frozen=True)
class PeriodTerm:
    """A contract period as the document expresses it."""

    span: Span
    start_iso: str
    end_iso: str | None
    open_ended: bool

    def covers(self, from_iso: str, to_iso: str) -> bool:
        if from_iso < self.start_iso:
            return False
        if self.open_ended or self.end_iso is None:
            return True
        return to_iso <= self.end_iso

    def human(self) -> str:
        if self.open_ended or self.end_iso is None:
            return f"{self.start_iso} och tills vidare"
        return f"{self.start_iso} – {self.end_iso}"


@dataclass(frozen=True)
class DurationTerm:
    """A term expressed as a length of time rather than as dates."""

    span: Span
    count: int
    unit: str  # "month" | "year" | "week"
    anchor: str  # "undertecknande", "avtalsstart", … or "" when unstated

    def human(self) -> str:
        unit = {"month": "månader", "year": "år", "week": "veckor"}[self.unit]
        anchored = f" från {self.anchor}" if self.anchor else ""
        return f"{self.count} {unit}{anchored}"


@dataclass(frozen=True)
class IndexTerm:
    """A clause saying the price moves with an index."""

    span: Span
    basis: str  # the index named, when one is: "entreprenadindex", "kpi", …

    def human(self) -> str:
        return f"indexreglerat pris ({self.basis})" if self.basis else "indexreglerat pris"


@dataclass(frozen=True)
class NoticeTerm:
    span: Span
    count: int
    unit: str

    def human(self) -> str:
        unit = {"month": "månader", "year": "år", "week": "veckor"}[self.unit]
        return f"{self.count} {unit}s uppsägningstid"


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------


def scan_dates(words: list[str]) -> list[DateHit]:
    """Every date in ``words``, ISO or Swedish long form.

    "den 1 november 2026" arrives from extraction as three or four separate
    words, so it is reassembled by position rather than matched with one
    expression over joined text — joined text would lose the word indices a
    citation span is built from.
    """
    hits: list[DateHit] = []
    n = len(words)
    for i, word in enumerate(words):
        iso = _ISO_DATE.findall(_clean(word))
        if iso:
            hits.append(DateHit(Span(i, i), iso[0]))
            continue
        day = _clean(word)
        if not _DIGITS.fullmatch(day) or not 1 <= int(day) <= 31:
            continue
        if i + 1 >= n:
            continue
        month = SWEDISH_MONTHS.get(_lower(words[i + 1]))
        if month is None:
            continue
        end = i + 1
        year = None
        if i + 2 < n and _DIGITS.fullmatch(_clean(words[i + 2])):
            candidate = int(_clean(words[i + 2]))
            if 1900 <= candidate <= 2200:
                year = candidate
                end = i + 2
        if year is None:
            # A day and a month with no year is a date the document expects
            # its reader to place from context. This code does not have that
            # context and does not invent it.
            continue
        try:
            resolved = date(year, month, int(day))
        except ValueError:
            continue
        start = i - 1 if i > 0 and _lower(words[i - 1]) == "den" else i
        hits.append(DateHit(Span(start, end), resolved.isoformat()))
    return hits


def _phrase_at(words: list[str], index: int, phrase: tuple[str, ...]) -> bool:
    if index + len(phrase) > len(words):
        return False
    return all(_lower(words[index + k]) == phrase[k] for k in range(len(phrase)))


def scan_periods(words: list[str], *, context: int = 4) -> list[PeriodTerm]:
    """Contract periods, closed and open-ended.

    A pair of dates is only a period when a period word stands shortly before
    the first one. Without that rule an invoice header's "Fakturadatum …
    Förfallodatum …" reads as an agreement period, which is what the first
    version of the review engine confidently reported.
    """
    out: list[PeriodTerm] = []
    dates = scan_dates(words)
    by_start = {hit.span.start: hit for hit in dates}
    for hit in dates:
        window = {_lower(w) for w in words[max(0, hit.span.start - context) : hit.span.start]}
        if not (window & PERIOD_START_WORDS):
            continue
        # Closed: another date within a few tokens after this one.
        closed: DateHit | None = None
        for j in range(hit.span.end + 1, min(len(words), hit.span.end + 5)):
            candidate = by_start.get(j)
            if candidate is not None:
                closed = candidate
                break
        if closed is not None:
            out.append(
                PeriodTerm(
                    span=Span(hit.span.start, closed.span.end),
                    start_iso=hit.iso,
                    end_iso=closed.iso,
                    open_ended=False,
                )
            )
            continue
        # Open-ended: "och tills vidare" shortly after.
        for j in range(hit.span.end + 1, min(len(words), hit.span.end + 6)):
            for phrase in OPEN_ENDED_PHRASES:
                if _phrase_at(words, j, phrase):
                    out.append(
                        PeriodTerm(
                            span=Span(hit.span.start, j + len(phrase) - 1),
                            start_iso=hit.iso,
                            end_iso=None,
                            open_ended=True,
                        )
                    )
                    break
            else:
                continue
            break
    return out


def _count_at(words: list[str], index: int) -> int | None:
    """A number written as digits or as a Swedish word, at ``index``.

    Contracts write "tolv (12) månader" as often as either alone, so a word
    followed by its own digits is one number and not two.
    """
    token = _lower(words[index])
    if token in SWEDISH_NUMBERS:
        return SWEDISH_NUMBERS[token]
    match = _PAREN_DIGITS.fullmatch(_clean(words[index]))
    if match:
        value = int(match.group(1))
        return value if 1 <= value <= 120 else None
    return None


def scan_durations(words: list[str]) -> list[DurationTerm]:
    """Terms like "tolv (12) månader från undertecknande"."""
    out: list[DurationTerm] = []
    n = len(words)
    for i in range(n):
        count = _count_at(words, i)
        if count is None:
            continue
        # "tolv (12) månader" is one duration written twice. Starting again at
        # the parenthesised repeat would report it as two.
        if i > 0 and _count_at(words, i - 1) == count:
            continue
        unit = None
        unit_at = i
        for j in range(i + 1, min(n, i + 4)):
            candidate = DURATION_UNITS.get(_lower(words[j]))
            if candidate is not None:
                unit, unit_at = candidate, j
                break
            # Skip a parenthesised repeat of the same number: "tolv (12) månader".
            if _count_at(words, j) == count:
                continue
            break
        if unit is None:
            continue
        anchor = ""
        end = unit_at
        for j in range(unit_at + 1, min(n, unit_at + 5)):
            found = DURATION_ANCHORS.get(_lower(words[j]))
            if found:
                anchor, end = found, j
                break
        out.append(DurationTerm(span=Span(i, end), count=count, unit=unit, anchor=anchor))
    return out


def scan_notice_periods(words: list[str]) -> list[NoticeTerm]:
    """A notice period, when one is stated near a duration."""
    out: list[NoticeTerm] = []
    n = len(words)
    for i, word in enumerate(words):
        if _lower(word) not in NOTICE_WORDS:
            continue
        window = range(max(0, i - 6), min(n, i + 7))
        for j in window:
            count = _count_at(words, j)
            if count is None:
                continue
            for k in range(j + 1, min(n, j + 4)):
                unit = DURATION_UNITS.get(_lower(words[k]))
                if unit is not None:
                    out.append(
                        NoticeTerm(span=Span(min(i, j), max(i, k)), count=count, unit=unit)
                    )
                    break
            else:
                continue
            break
    return out


def scan_index_clauses(words: list[str]) -> list[IndexTerm]:
    """Clauses saying the price follows an index.

    The basis is recorded when the clause names one, because "indexreglerat
    enligt KPI" and "enligt SCB:s entreprenadindex E84" send a reviewer to
    different places.
    """
    out: list[IndexTerm] = []
    n = len(words)
    last_end = -1
    for i, word in enumerate(words):
        token = _lower(word)
        if token not in INDEX_WORDS:
            continue
        # "indexregleras … enligt SCB:s entreprenadindex" is one clause with two
        # index words in it. Reporting it twice would double every citation a
        # reviewer is asked to read.
        if i <= last_end:
            continue
        basis = ""
        for candidate in (token, *[_lower(w) for w in words[max(0, i - 3) : min(n, i + 6)]]):
            if candidate in ("kpi", "konsumentprisindex"):
                basis = "KPI"
                break
            if candidate in ("entreprenadindex", "faktorprisindex"):
                basis = candidate
                break
        if not basis:
            support = {_lower(w) for w in words[max(0, i - 4) : min(n, i + 6)]}
            if support & INDEX_SUPPORT_WORDS:
                basis = "SCB"
        span = Span(max(0, i - 2), min(n - 1, i + 4))
        last_end = span.end
        out.append(IndexTerm(span=span, basis=basis))
    return out


__all__ = [
    "DURATION_ANCHORS",
    "DURATION_UNITS",
    "DateHit",
    "DurationTerm",
    "INDEX_WORDS",
    "IndexTerm",
    "NoticeTerm",
    "OPEN_ENDED_PHRASES",
    "PERIOD_START_WORDS",
    "PeriodTerm",
    "SWEDISH_MONTHS",
    "SWEDISH_NUMBERS",
    "Span",
    "scan_dates",
    "scan_durations",
    "scan_index_clauses",
    "scan_notice_periods",
    "scan_periods",
]
