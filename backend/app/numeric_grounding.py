"""Numeric grounding gate (SPEC §2.10 — see docs/evidence/numeric-grounding.md).

Citation verification (app/citations.py) proves a QUOTE is verbatim-real at
its claimed location. It says nothing about whether the model's own prose
ANSWER — composed freely alongside that quote — asserts the same numbers the
quote does. A real production incident showed the gap: a verified citation
quote read "Total utgift 15 659 566 kr", and Gemma 4 12B's answer text
nevertheless said "1 565 956 kr" — a transposed-digit fabrication the
existing pipeline had no mechanism to catch, because the citation itself
passed every check.

This gate closes that specific hole: every material number in the final
answer text must reappear, after normalization, among the numbers found in
the ACCEPTED citations' verified quote spans. Support never comes from
anything else — not a rejected citation, not a document filename, not a
page number, not a chunk id, not the user's question.

Deterministic and offline: pure text/value comparison, no model call, no
arithmetic engine. A derived/calculated value (e.g. a sum the model computed
itself) is never "supported" by this gate — only a number that appears
verbatim in a verified quote is, matching the product's conservative MVP
policy of copy-exact over calculate-and-round.

Follow-up fix (identifier false positives): a digit that is part of a
verified ENTITY NAME — the tenant's own registered name, e.g. "Brf
Gjutformen 12" — is not a factual claim, and treating it as one produced a
real false refusal in pilot testing (see docs/evidence/numeric-grounding.md).
`check_numeric_grounding` accepts an optional `trusted_names` set for this:
only a COMPLETE, exact (normalized) span is ever excluded from the answer
before numbers are extracted — never a bare digit, never a partial match,
never anything from the user's question. Trusted names are supplied by the
caller (app/answer.py, sourced from auth.get_tenant() and from THIS
response's own accepted citations' document names) — this module never
decides what counts as trusted, only how to mask an exact span once told.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from .normalize import normalize_text

# A number token, scanned AFTER normalize_text has folded every NBSP / thin
# space / narrow-no-break-space variant to a plain ASCII space (see
# app/normalize.py's _CHAR_MAP) — Swedish financial PDF exports routinely use
# a non-breaking space *inside* a grouped number so it never wraps across a
# line, so both "15 659 566" (typed with regular spaces) and a source token
# that embeds NBSP between digit groups normalize identically before this
# regex ever runs.
#
# Matches, left to right, non-overlapping:
#   - space-grouped thousands: "15 659 566"
#   - an ungrouped digit run:  "56", "2032"
#   - an optional decimal part, comma OR point: "151,5" / "151.5"
#   - an optional trailing percent sign (with or without a space before it)
#
# A hyphen between two numbers ("2024-2053", an org-nr "769621-4455") is
# deliberately NOT captured as a sign — the hyphen simply isn't part of the
# match, so both endpoints are extracted as independent positive numbers.
# That gives range support "where practical" for free, without a dedicated
# range grammar, and lets a hyphenated id decompose symmetrically on both
# the answer and quote side.
#
# Period-grouped thousands ("15.659.566") requires AT LEAST TWO ".DDD"
# groups to be unambiguous. A single ".DDD" group ("15.659") is inherently
# ambiguous between thousands-grouping and a decimal — deliberately left as
# a decimal (falls through to the bare-digit-run + frac alternative below)
# rather than guessing, matching the task's "no ambiguous decimal/grouping
# assumptions" requirement. This alternative must come first: alternation
# tries left to right, and it must get first refusal at "15.659.566" before
# the bare `\d+` alternative would otherwise claim just "15".
_NUMBER_RE = re.compile(
    r"""
    (?<![\w,.])                          # not glued to a preceding digit/word/decimal separator
    (?P<int>
        \d{1,3}(?:\.\d{3}){2,}           # period-grouped thousands: "15.659.566" (>=2 groups)
        |\d{1,3}(?:\ \d{3})+             # space-grouped thousands: "15 659 566"
        |\d+                             # ungrouped digit run, e.g. "566"
    )
    (?P<frac>[.,]\d+)?                   # decimal part, comma or point
    (?P<pct>\ ?(?:%|procent))?           # percent sign OR the Swedish word, optionally space-separated
    (?!\w)                               # not glued to a following word char (unit, id suffix)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class NumberClaim:
    raw: str        # the exact matched substring, for human-readable mismatch messages
    value: Decimal  # canonical numeric value (thousands separators stripped, decimal normalized)
    is_percent: bool  # "%" is a distinct claim from the bare digits — 8 and 8% never cross-match


def _parse_match(m: re.Match) -> NumberClaim | None:
    # ".replace(".", "")" is safe unconditionally: the only alternative that
    # can ever contain a literal "." is the period-thousands grouping one —
    # the space-grouped and bare-digit-run alternatives never match a ".".
    int_part = m.group("int").replace(" ", "").replace(".", "")
    frac_part = m.group("frac")
    text = int_part if not frac_part else f"{int_part}.{frac_part[1:]}"
    try:
        value = Decimal(text)
    except InvalidOperation:  # pragma: no cover — regex only emits digit runs
        return None
    return NumberClaim(raw=m.group(0).strip(), value=value, is_percent=bool(m.group("pct")))


def extract_numbers(text: str) -> list[NumberClaim]:
    """Every number-shaped token in `text`, left to right. Pure syntax — this
    function has no notion of which numbers are "material"; callers decide
    what set of numbers to check and what set counts as support."""
    if not text:
        return []
    normalized = normalize_text(text)
    claims = []
    for m in _NUMBER_RE.finditer(normalized):
        claim = _parse_match(m)
        if claim is not None:
            claims.append(claim)
    return claims


def mask_trusted_spans(text: str, trusted_names: Iterable[str]) -> str:
    """Blank out exact, normalized trusted-entity spans before number
    extraction, so a digit that is part of a verified entity name (a tenant's
    registered name, an accepted citation's document title) is never treated
    as a numeric CLAIM requiring citation support.

    Only a COMPLETE normalized span is ever excluded — matching is anchored
    on both ends with word boundaries, so "Brf Gjutformen 12" never matches
    inside "Brf Gjutformen 123" (wrong identifier) or a name that merely
    shares a prefix/suffix. Names are tried longest-first so one trusted name
    that is a substring of another can't shadow the longer, more specific
    match. Each match is replaced with spaces of equal length (never
    deleted) so numbers on either side of a masked span never become
    accidentally adjacent.

    `text` must already be normalized (normalize_text) — trusted names are
    normalized here to the same form before comparison.
    """
    names = sorted(
        {normalize_text(n).strip() for n in trusted_names if n and n.strip()},
        key=len,
        reverse=True,
    )
    if not names:
        return text
    pattern = re.compile("|".join(rf"(?<!\w){re.escape(n)}(?!\w)" for n in names))
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


@dataclass(frozen=True)
class NumericGroundingResult:
    ok: bool
    unsupported: list[NumberClaim]  # empty iff ok


def check_numeric_grounding(
    answer_text: str,
    support_quotes: list[str],
    *,
    trusted_names: Iterable[str] = (),
) -> NumericGroundingResult:
    """Verify every number claimed in `answer_text` equals (value AND
    percent-ness) a number found in `support_quotes` — the verbatim,
    already-verified spans of the citations about to be shown to the user.

    Callers MUST pass only ACCEPTED citations' quote spans as
    `support_quotes` — never a rejected citation's quote, a document name, a
    page number, a chunk id, or the question text. Passing anything else as
    "support" defeats the guarantee this gate exists to provide.

    `trusted_names` (optional): exact entity-name spans (see
    mask_trusted_spans) to exclude from `answer_text` BEFORE number
    extraction — never added to the support set. A digit inside a trusted
    span is never a claim at all, so it neither needs support nor can it
    manufacture false support for some unrelated number elsewhere in the
    answer that happens to share the same value.
    """
    support: set[tuple[Decimal, bool]] = set()
    for quote in support_quotes:
        for claim in extract_numbers(quote):
            support.add((claim.value, claim.is_percent))

    masked_answer = mask_trusted_spans(normalize_text(answer_text), trusted_names)
    unsupported = [
        claim for claim in extract_numbers(masked_answer) if (claim.value, claim.is_percent) not in support
    ]
    return NumericGroundingResult(ok=not unsupported, unsupported=unsupported)


def describe_mismatch(result: NumericGroundingResult) -> str:
    """A precise, human/model-readable description of exactly which numbers
    failed — fed back to the LLM as the repair prompt's mismatch report."""
    # Order-preserving de-dup: same number stated twice should list once.
    seen: list[str] = []
    for claim in result.unsupported:
        if claim.raw not in seen:
            seen.append(claim.raw)
    return ", ".join(seen)
