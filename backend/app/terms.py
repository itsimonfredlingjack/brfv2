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
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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

# Every inflection a Swedish agreement actually uses. The first version had
# "säga" but neither "sägas" nor "sägs", so "Avtalet får sägas upp skriftligen
# senast sex månader före avtalstidens utgång" — the commonest phrasing there
# is — read as no notice period at all.
NOTICE_WORDS = frozenset(
    {
        "uppsägning",
        "uppsagning",
        "uppsägningen",
        "uppsagningen",
        "uppsägningstid",
        "uppsagningstid",
        "uppsägningstiden",
        "uppsagningstiden",
        "uppsäga",
        "uppsaga",
        "uppsägas",
        "uppsagas",
        "säga",
        "saga",
        "sägas",
        "sagas",
        "sägs",
        "sags",
        "säges",
        "sages",
    }
)

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

    def merged_with(self, other: "Span") -> "Span":
        return Span(min(self.start, other.start), max(self.end, other.end))

    def distance_to(self, other: "Span") -> int:
        """Words between the two spans, 0 when they touch or overlap."""
        if self.end < other.start:
            return other.start - self.end - 1
        if other.end < self.start:
            return self.start - other.end - 1
        return 0


# ---------------------------------------------------------------------------
# Date arithmetic
# ---------------------------------------------------------------------------

# Deliberately here rather than in the watch engine. "tre månader före den 31
# december" is a *reading* of the contract, and the arithmetic that turns it
# into 30 september is part of that reading — including the clamping rule,
# which is the only place this could quietly be wrong.


def shift_months(day: date, months: int) -> date:
    """Move a date by whole months, clamping the day to the target month.

    31 december minus three months is 30 september, not "31 september" and not
    1 oktober. Clamping down is what a Swedish contract means by "tre månader
    före": the deadline falls inside the month, and a deadline that silently
    moved to the 1st of the next month would be a day late in the only
    direction that matters.
    """
    total = (day.year * 12 + (day.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    if month == 12:
        last = 31
    else:
        last = (date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def shift(day: date, count: int, unit: str) -> date:
    """Move a date by ``count`` of ``unit`` ("month" | "year" | "week" | "day")."""
    if unit == "month":
        return shift_months(day, count)
    if unit == "year":
        return shift_months(day, count * 12)
    if unit == "week":
        return day + timedelta(weeks=count)
    if unit == "day":
        return day + timedelta(days=count)
    raise ValueError(f"okänd tidsenhet: {unit!r}")


# IANA name, never CET/CEST/+02:00 — those flip twice a year and a stored
# offset is a lie the other half of the year.
STOCKHOLM_TZ = "Europe/Stockholm"


def calendar_date_in(value: str, *, zone: str = STOCKHOLM_TZ) -> date | None:
    """UTC instant → calendar date in ``zone``. ``date()`` is taken after conversion.

    ``2026-08-14T22:30:00Z`` is already 15 August in Europe/Stockholm. Taking
    the UTC date first starts a ten-day count on the wrong morning.
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        instant = datetime.fromisoformat(text)
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ZoneInfo(zone)).date()


def parse_iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# Month names as a Swedish sentence abbreviates them — the same forms the UI's
# own date formatting produces, so backend prose and frontend chrome cannot
# read as two dialects.
MANADER = ("jan.", "feb.", "mars", "apr.", "maj", "juni",
           "juli", "aug.", "sep.", "okt.", "nov.", "dec.")


def svenskt_datum(day: date | str | None, *, idag: date | None = None) -> str:
    """A date as a person says it: "31 maj 2029", never "2029-05-31".

    ISO stays in the machine fields; this is for prose — titles, derivations,
    signal sentences. Pass *idag* to drop the year when it is the current one
    (what a register column wants); leave it out where the year always
    matters, as in a deadline years ahead.
    """
    if isinstance(day, str):
        parsed = parse_iso(day)
        if parsed is None:
            return day
        day = parsed
    if day is None:
        return "—"
    ar = "" if idag is not None and day.year == idag.year else f" {day.year}"
    return f"{day.day} {MANADER[day.month - 1]}{ar}"


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


# Verbs that mean the duration next to them is how long the agreement *renews*
# for, not how much notice is required. "Om avtalet inte sägs upp förlängs det
# med tolv månader i taget. Avtalet får sägas upp senast sex månader före
# avtalstidens utgång" states both, and an earlier version of this scanner read
# the first number — reporting a twelve-month notice period on a contract whose
# notice period is six.
_RENEWAL_VERBS = frozenset(
    {"förlängs", "forlangs", "förlängas", "forlangas", "förlängning", "forlangning", "förnyas", "fornyas", "löper", "loper"}
)


def scan_notice_periods(words: list[str]) -> list[NoticeTerm]:
    """How much notice the agreement requires, when it says so.

    The duration has to belong to the notice, which means two things beyond
    standing near it: no sentence may end in between, and no renewal verb may
    stand in between. Both guards exist because a contract that states its
    renewal length and its notice period in adjacent clauses is the normal
    case, not the awkward one.
    """
    out: list[NoticeTerm] = []
    n = len(words)
    for i, word in enumerate(words):
        if _lower(word) not in NOTICE_WORDS:
            continue
        for j in sorted(range(max(0, i - 6), min(n, i + 7)), key=lambda k: abs(k - i)):
            count = _count_at(words, j)
            if count is None:
                continue
            lo, hi = (i, j) if i < j else (j, i)
            between = words[lo + 1 : hi]
            if any(_lower(w) in _RENEWAL_VERBS for w in between):
                continue
            if any(
                _clean(w).endswith((".", "!", "?")) and _clean(w).casefold() not in _ABBREVIATIONS
                for w in between
            ):
                continue
            unit = None
            for k in range(j + 1, min(n, j + 4)):
                unit = DURATION_UNITS.get(_lower(words[k]))
                if unit is not None:
                    out.append(NoticeTerm(span=Span(min(i, j), max(i, k)), count=count, unit=unit))
                    break
            if unit is not None:
                break
    return out


@dataclass(frozen=True)
class RelativeDeadline:
    """"senast tre månader före den 31 december 2026" — a date you can compute.

    This is the shape that actually makes a deadline actionable: a duration, a
    direction and an anchor date that is *in the text*. Without the anchor
    there is nothing to compute from, and this scanner returns nothing rather
    than something plausible — see :mod:`app.watches.derive` for what happens
    to the clause then.
    """

    span: Span
    count: int
    unit: str
    before: bool  # "före" vs "efter"
    anchor_iso: str

    def resolve(self) -> str:
        anchor = parse_iso(self.anchor_iso)
        assert anchor is not None  # only built from a parsed date
        return shift(anchor, -self.count if self.before else self.count, self.unit).isoformat()

    def human(self) -> str:
        unit = {"month": "månader", "year": "år", "week": "veckor", "day": "dagar"}[self.unit]
        direction = "före" if self.before else "efter"
        return f"{self.count} {unit} {direction} {self.anchor_iso}"


@dataclass(frozen=True)
class RelativeHit:
    """A day-count in the text, with an in-text anchor date when one is there.

    "inom tio dagar" has no date of its own — ``anchor_iso`` is empty, and
    :func:`anchor_relative` fills it from an external receipt date. "15 dagar
    från fakturadatum 2026-09-01" already names its start, and that date wins.
    """

    span: Span
    count: int
    unit: str  # "day"
    before: bool
    anchor_iso: str  # "" when the text does not name a date


# One place for how an interval is said in Swedish — derive.py writes these
# into proposal prose, so an inline dict here would be a second dialect
# ("triennial") leaking into a board's reading the day someone forgets one.
RECURRENCE_HUMAN = {
    "monthly": "varje månad",
    "quarterly": "varje kvartal",
    "yearly": "varje år",
    "biennial": "vartannat år",
    "triennial": "vart tredje år",
}


@dataclass(frozen=True)
class RecurrenceTerm:
    span: Span
    every: str  # "monthly" | "quarterly" | "yearly" | "biennial" | "triennial"

    def human(self) -> str:
        return RECURRENCE_HUMAN[self.every]


# Words that say a date is the far end of a countdown rather than the deadline
# itself. Both directions, because "sex månader efter slutbesiktning" is as
# common as "tre månader före avtalstidens utgång".
_BEFORE_WORDS = frozenset({"före", "fore", "innan", "senast"})
_AFTER_WORDS = frozenset({"efter", "från", "fran", "räknat", "raknat"})

RECURRENCE_PHRASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("varje", "månad"), "monthly"),
    (("varje", "manad"), "monthly"),
    (("månadsvis",), "monthly"),
    (("manadsvis",), "monthly"),
    (("varje", "kvartal"), "quarterly"),
    (("kvartalsvis",), "quarterly"),
    (("varje", "år"), "yearly"),
    (("varje", "ar"), "yearly"),
    (("årligen",), "yearly"),
    (("arligen",), "yearly"),
    (("årlig",), "yearly"),
    (("arlig",), "yearly"),
    (("vartannat", "år"), "biennial"),
    (("vartannat", "ar"), "biennial"),
    (("vart", "tredje", "år"), "triennial"),
    (("vart", "tredje", "ar"), "triennial"),
)


def scan_relative_deadlines(words: list[str], *, reach: int = 12) -> list[RelativeDeadline]:
    """Deadlines expressed as a distance from a date the text actually points at.

    Three conditions, and the first version of this function had only a weak
    form of the third — which produced a confidently wrong deadline out of the
    seeded snow-clearing contract:

        "Avtalet gäller från den 1 november 2026 och tills vidare.
         Uppsägning skall ske skriftligen senast tre månader före
         avtalstidens utgång."

    Taking the *nearest* date made "tre månader före" count from the contract's
    **start**, and reported that notice had to be given by 2026-08-01. Every
    part of that was verifiable and all of it was nonsense: the clause counts
    from a date the document never states.

    So the anchor must satisfy all three:

    1. **A direction word follows the duration** — "tre månader *före* …",
       "fem år *från* …". A "senast" standing in front of the duration is a
       qualifier on the obligation, not the operator on the date.
    2. **The date comes after that direction word**, within ``reach``. A date
       earlier in the text is something else being talked about.
    3. **No sentence ends in between.** A deadline does not count from a date
       in the previous sentence, which is exactly what went wrong.

    A duration with no anchor stays a :class:`NoticeTerm` and nothing more,
    because the only way to turn it into a date would be to assume which date
    it counts from.
    """
    out: list[RelativeDeadline] = []
    dates = scan_dates(words)
    n = len(words)
    for duration in scan_durations(words):
        direction: bool | None = None
        operator_at = -1
        for i in range(duration.span.end + 1, min(n, duration.span.end + 4)):
            token = _lower(words[i])
            if token in _BEFORE_WORDS:
                direction, operator_at = True, i
                break
            if token in _AFTER_WORDS:
                direction, operator_at = False, i
                break
        if direction is None:
            continue
        anchor: DateHit | None = None
        for hit in dates:
            if hit.span.start <= operator_at:
                continue
            if hit.span.start - operator_at > reach:
                continue
            # A sentence boundary between the operator and the date means the
            # date belongs to a different statement.
            if any(
                _clean(words[j]).endswith((".", "!", "?")) and not _is_abbreviation(words[j])
                for j in range(operator_at, hit.span.start)
            ):
                continue
            anchor = hit
            break
        if anchor is None:
            continue
        out.append(
            RelativeDeadline(
                span=duration.span.merged_with(anchor.span),
                count=duration.count,
                unit=duration.unit,
                before=direction,
                anchor_iso=anchor.iso,
            )
        )
    return out


# Tokens that end in a full stop without ending a sentence. Short list on
# purpose: a false positive here re-opens the bug this guard exists to close,
# so anything not listed is treated as a sentence end.
_ABBREVIATIONS = frozenset({"t.o.m.", "fr.o.m.", "bl.a.", "dvs.", "resp.", "nr.", "ca.", "s.k."})


def _is_abbreviation(token: str) -> bool:
    return token.strip().casefold() in _ABBREVIATIONS


# Day-counts that an email uses as a deadline. Kept off DURATION_UNITS on
# purpose: putting "dagar" there would make the contract scan start proposing
# watches from "tio dagar" in a PDF, counted from nothing.
_DAY_UNITS = frozenset({"dag", "dagar", "dags"})
_WORKDAY_UNITS = frozenset({"arbetsdag", "arbetsdagar", "vardag", "vardagar"})
_PA_ER = frozenset({"på", "pa"})


def _day_unit_at(words: list[str], index: int) -> tuple[int, bool] | None:
    """Index of a day-unit after ``index``, and whether it is a working-day word.

    Returns ``None`` when the next tokens are not a duration in days at all.
    """
    n = len(words)
    count = _count_at(words, index)
    if count is None:
        return None
    for j in range(index + 1, min(n, index + 4)):
        token = _lower(words[j])
        if token in _WORKDAY_UNITS:
            return j, True
        if token in _DAY_UNITS:
            return j, False
        if _count_at(words, j) == count:
            continue
        break
    return None


def scan_day_deadlines(words: list[str], *, reach: int = 12) -> list[RelativeHit]:
    """Swedish day-deadlines: "inom tio dagar", "senast om fem dagar", "på er".

    Working days are not calendar days. A hit whose unit is ``arbetsdagar``
    (or that names them next to the count) is dropped rather than converted
    with a guess about whose calendar applies.
    """
    out: list[RelativeHit] = []
    n = len(words)
    dates = scan_dates(words)
    for i in range(n):
        count = _count_at(words, i)
        if count is None:
            continue
        if i > 0 and _count_at(words, i - 1) == count:
            continue
        located = _day_unit_at(words, i)
        if located is None:
            continue
        unit_at, is_workday = located
        neighbourhood = {_lower(w) for w in words[max(0, i - 1) : min(n, unit_at + 3)]}
        if is_workday or neighbourhood & _WORKDAY_UNITS:
            continue

        particle_start: int | None = None
        for k in range(max(0, i - 3), i):
            if _lower(words[k]) == "inom":
                particle_start = k
                break
        if particle_start is None:
            for k in range(max(0, i - 4), i - 1 if i else 0):
                if _lower(words[k]) == "senast" and _lower(words[k + 1]) == "om":
                    particle_start = k
                    break
        particle_end: int | None = None
        for k in range(unit_at + 1, min(n, unit_at + 3)):
            if _lower(words[k]) in _PA_ER and k + 1 < n and _lower(words[k + 1]) == "er":
                particle_end = k + 1
                break

        direction: bool | None = None
        operator_at = -1
        for k in range(unit_at + 1, min(n, unit_at + 4)):
            token = _lower(words[k])
            if token in _BEFORE_WORDS:
                direction, operator_at = True, k
                break
            if token in _AFTER_WORDS:
                direction, operator_at = False, k
                break

        anchor: DateHit | None = None
        if operator_at >= 0:
            for hit in dates:
                if hit.span.start <= operator_at:
                    continue
                if hit.span.start - operator_at > reach:
                    continue
                if any(
                    _clean(words[j]).endswith((".", "!", "?")) and not _is_abbreviation(words[j])
                    for j in range(operator_at, hit.span.start)
                ):
                    continue
                anchor = hit
                break

        if particle_start is None and particle_end is None and anchor is None:
            continue

        start = i if particle_start is None else particle_start
        end = unit_at
        if particle_end is not None:
            end = max(end, particle_end)
        if anchor is not None:
            end = max(end, anchor.span.end)
        out.append(
            RelativeHit(
                span=Span(start, end),
                count=count,
                unit="day",
                before=bool(direction),
                anchor_iso=anchor.iso if anchor is not None else "",
            )
        )
    return out


def anchor_relative(hits: list[RelativeHit], *, reference_date: date) -> list[RelativeDeadline]:
    """Resolve day-counts against ``reference_date`` when the text named none.

    Two-step, the way SUTime/HeidelTime split extraction from normalisation:
    :func:`scan_day_deadlines` finds the duration; this function is the only
    place an external date is applied. An in-text date on the hit wins.
    Arithmetic is calendar days on a :class:`~datetime.date`, never a
    timezone-aware timedelta — ten days across the October shift is ten dates,
    not 240 hours.
    """
    out: list[RelativeDeadline] = []
    for hit in hits:
        anchor_iso = hit.anchor_iso or reference_date.isoformat()
        out.append(
            RelativeDeadline(
                span=hit.span,
                count=hit.count,
                unit=hit.unit,
                before=hit.before,
                anchor_iso=anchor_iso,
            )
        )
    return out


def scan_recurrence(words: list[str]) -> list[RecurrenceTerm]:
    """How often something repeats, when the text says so in as many words."""
    out: list[RecurrenceTerm] = []
    last_end = -1
    for i in range(len(words)):
        if i <= last_end:
            continue
        for phrase, every in RECURRENCE_PHRASES:
            if _phrase_at(words, i, phrase):
                span = Span(i, i + len(phrase) - 1)
                out.append(RecurrenceTerm(span=span, every=every))
                last_end = span.end
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
    "RECURRENCE_PHRASES",
    "PeriodTerm",
    "RecurrenceTerm",
    "RelativeDeadline",
    "RelativeHit",
    "STOCKHOLM_TZ",
    "SWEDISH_MONTHS",
    "SWEDISH_NUMBERS",
    "Span",
    "anchor_relative",
    "calendar_date_in",
    "parse_iso",
    "scan_dates",
    "scan_day_deadlines",
    "scan_durations",
    "scan_index_clauses",
    "scan_notice_periods",
    "scan_periods",
    "scan_recurrence",
    "scan_relative_deadlines",
    "shift",
    "shift_months",
]
