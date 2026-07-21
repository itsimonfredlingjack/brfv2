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
"""

from __future__ import annotations

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
_NUMBER_RE = re.compile(
    r"""
    (?<![\w,.])                        # not glued to a preceding digit/word/decimal separator
    (?P<int>\d{1,3}(?:\ \d{3})+|\d+)   # "15 659 566"  or a bare run "566"
    (?P<frac>[.,]\d+)?                  # decimal part, comma or point
    (?P<pct>\ ?%)?                      # percent sign, optionally space-separated
    (?!\w)                              # not glued to a following word char (unit, id suffix)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class NumberClaim:
    raw: str        # the exact matched substring, for human-readable mismatch messages
    value: Decimal  # canonical numeric value (thousands separators stripped, decimal normalized)
    is_percent: bool  # "%" is a distinct claim from the bare digits — 8 and 8% never cross-match


def _parse_match(m: re.Match) -> NumberClaim | None:
    int_part = m.group("int").replace(" ", "")
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


@dataclass(frozen=True)
class NumericGroundingResult:
    ok: bool
    unsupported: list[NumberClaim]  # empty iff ok


def check_numeric_grounding(answer_text: str, support_quotes: list[str]) -> NumericGroundingResult:
    """Verify every number claimed in `answer_text` equals (value AND
    percent-ness) a number found in `support_quotes` — the verbatim,
    already-verified spans of the citations about to be shown to the user.

    Callers MUST pass only ACCEPTED citations' quote spans as
    `support_quotes` — never a rejected citation's quote, a document name, a
    page number, a chunk id, or the question text. Passing anything else as
    "support" defeats the guarantee this gate exists to provide.
    """
    support: set[tuple[Decimal, bool]] = set()
    for quote in support_quotes:
        for claim in extract_numbers(quote):
            support.add((claim.value, claim.is_percent))

    unsupported = [
        claim for claim in extract_numbers(answer_text) if (claim.value, claim.is_percent) not in support
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
