"""Deciding whether a document is about the supplier on an invoice.

The review hangs on one question: does some document in the association's own
archive *name* this supplier? Get it wrong in one direction and an elevator
company's call-out fee is compared against a snow-clearing contract's hourly
rate. Get it wrong in the other and a contract that says "Snösvängen AB" is
invisible to an invoice from "Snösvängen Entreprenad AB", which is the same
company and was the first thing a real reviewer noticed.

So the answer is not a boolean. It is an :class:`Anchor` with a *strength*, and
the strength changes what the finding is allowed to say:

``org_number``   the invoice's organisation number appears verbatim in the
                 document. Two companies can share a trading name; none share
                 an organisation number.
``exact``        the full name appears verbatim.
``legal_form``   the name appears without its legal form, or with a different
                 one — "Snösvängen Entreprenad AB" against "Snösvängen
                 Entreprenad". Same company, differently written.
``alias``        a human at this association has confirmed that these two names
                 are the same supplier. A person's decision, recorded with
                 their id.
``partial``      the distinctive part of the name matches and the rest does
                 not. **Weak**: it produces an anchor so the review can
                 proceed, and it obliges the finding to say the names differ
                 and to offer the alias for confirmation. A weak anchor that
                 stayed silent would be the old bug wearing better clothes.

Everything here is about *which strings to look for*. Whether a string is
actually in a document is still decided by
:func:`app.citations.resolve_citation` against the extracted page words — no
amount of clever name matching relaxes the verbatim requirement.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Literal

# Swedish and Nordic legal forms, plus the noise that clings to them. Removed
# from the end of a name to find its core, never from the middle: "AB Svenska
# Bostäder" is a company whose name starts with AB.
LEGAL_FORM_TOKENS = frozenset(
    {
        "ab",
        "aktiebolag",
        "publ",
        "hb",
        "kb",
        "handelsbolag",
        "kommanditbolag",
        "ekonomisk",
        "förening",
        "forening",
        "ek",
        "ekf",
        "af",
        "as",
        "asa",
        "oy",
        "aps",
        "gmbh",
        "ltd",
        "plc",
        "inc",
        "corp",
        "sa",
        "bv",
        "nv",
    }
)

# Words too common to identify a company on their own. A first token from this
# set is not distinctive enough to carry a partial anchor by itself.
GENERIC_TOKENS = frozenset(
    {
        "service",
        "tjänster",
        "tjanster",
        "entreprenad",
        "entreprenader",
        "bygg",
        "byggnads",
        "fastighet",
        "fastigheter",
        "fastighetsservice",
        "förvaltning",
        "forvaltning",
        "städ",
        "stad",
        "städservice",
        "el",
        "eltjänst",
        "vvs",
        "rör",
        "ror",
        "hiss",
        "hissar",
        "svenska",
        "sverige",
        "nordic",
        "nordisk",
        "group",
        "gruppen",
        "city",
        "syd",
        "nord",
        "väst",
        "vast",
        "öst",
        "ost",
        "teknik",
        "drift",
        "energi",
        "trädgård",
        "tradgard",
        "mark",
        "anläggning",
        "anlaggning",
    }
)

AnchorStrength = Literal["org_number", "exact", "legal_form", "alias", "partial"]

# Ordered strongest first. Used to pick between competing matches and to decide
# whether a finding must carry a name-difference caveat.
STRENGTH_ORDER: tuple[AnchorStrength, ...] = (
    "org_number",
    "exact",
    "alias",
    "legal_form",
    "partial",
)
WEAK_STRENGTHS: frozenset[str] = frozenset({"partial"})

_PUNCT = re.compile(r"[^\w\s&-]", re.UNICODE)
_ORG_NUMBER = re.compile(r"\b(\d{6})[-\s]?(\d{4})\b")
_SWEDISH_ORG_PREFIX = re.compile(r"^(?:16|18|19|20)")


def strip_accents_preserving_swedish(text: str) -> str:
    """Fold accents but keep å, ä and ö, which are letters and not decoration."""
    keep = {"å", "ä", "ö", "Å", "Ä", "Ö"}
    out = []
    for char in text:
        if char in keep:
            out.append(char)
            continue
        decomposed = unicodedata.normalize("NFD", char)
        out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
    return "".join(out)


def tokens_of(name: str) -> list[str]:
    """Comparable tokens: casefolded, punctuation removed, whitespace collapsed."""
    cleaned = _PUNCT.sub(" ", strip_accents_preserving_swedish(name))
    return [t for t in cleaned.casefold().split() if t]


def core_tokens(name: str) -> list[str]:
    """The name with its trailing legal form removed.

    Trailing only. "Ekonomisk förening" is two tokens and both go; "AB" at the
    front stays, because a name that begins with it is using it as a name.
    """
    parts = tokens_of(name)
    while parts and parts[-1] in LEGAL_FORM_TOKENS:
        parts.pop()
    return parts


def normalize(name: str) -> str:
    """A canonical key for "is this the same supplier" comparisons."""
    return " ".join(core_tokens(name))


def is_distinctive(token: str) -> bool:
    return len(token) >= 4 and token not in GENERIC_TOKENS


def normalize_org_number(value: str) -> str:
    """``556677-8899`` and ``5566778899`` are the same number. Personal and
    coordination numbers with a century prefix reduce to their ten digits."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and _SWEDISH_ORG_PREFIX.match(digits):
        digits = digits[2:]
    return digits if len(digits) == 10 else ""


def org_numbers_in(text: str) -> set[str]:
    return {
        normalize_org_number(f"{a}{b}")
        for a, b in _ORG_NUMBER.findall(text or "")
        if normalize_org_number(f"{a}{b}")
    }


@dataclass(frozen=True)
class NeedleSpec:
    """One string to look for, and what finding it would mean.

    ``tokens`` is what is compared against the page's own words, because that
    is the unit extraction produces and the unit a citation span is measured
    in. ``display`` is what a person is shown.
    """

    tokens: tuple[str, ...]
    display: str
    strength: AnchorStrength
    # For an alias match: who confirmed it, so a finding can say so.
    confirmed_by: str = ""


def needles_for(
    supplier_name: str,
    *,
    org_number: str = "",
    aliases: Iterable[tuple[str, str]] = (),
) -> list[NeedleSpec]:
    """Every string worth looking for, strongest first, without duplicates.

    ``aliases`` is ``(alias name, confirmed by)`` for aliases a human at this
    association has recorded against this supplier.
    """
    out: list[NeedleSpec] = []
    seen: set[tuple[str, ...]] = set()

    def add(tokens: list[str], display: str, strength: AnchorStrength, by: str = "") -> None:
        key = tuple(tokens)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(NeedleSpec(tokens=key, display=display, strength=strength, confirmed_by=by))

    normalized_org = normalize_org_number(org_number)
    if normalized_org:
        # Both written forms, because a contract writes one and an invoice the
        # other, and neither is more correct.
        add([f"{normalized_org[:6]}-{normalized_org[6:]}"], org_number, "org_number")
        add([normalized_org], org_number, "org_number")

    full = tokens_of(supplier_name)
    add(full, supplier_name, "exact")

    for alias, by in aliases:
        add(tokens_of(alias), alias, "alias", by)
        add(core_tokens(alias), alias, "alias", by)

    core = core_tokens(supplier_name)
    if core != full:
        add(core, supplier_name, "legal_form")

    # The distinctive head: the longest leading run that is worth matching on
    # its own. Two tokens always, or one when that one token is distinctive.
    if len(core) >= 2:
        add(core[:2], " ".join(core[:2]), "partial")
    if core and is_distinctive(core[0]):
        add(core[:1], core[0], "partial")
    return out


def strength_rank(strength: str) -> int:
    try:
        return STRENGTH_ORDER.index(strength)  # type: ignore[arg-type]
    except ValueError:  # pragma: no cover - a strength not in the table
        return len(STRENGTH_ORDER)


def names_differ(invoice_name: str, document_name: str) -> bool:
    """True when the two names are not the same supplier written the same way."""
    return normalize(invoice_name) != normalize(document_name)


__all__ = [
    "AnchorStrength",
    "GENERIC_TOKENS",
    "LEGAL_FORM_TOKENS",
    "NeedleSpec",
    "STRENGTH_ORDER",
    "WEAK_STRENGTHS",
    "core_tokens",
    "is_distinctive",
    "names_differ",
    "needles_for",
    "normalize",
    "normalize_org_number",
    "org_numbers_in",
    "strength_rank",
    "strip_accents_preserving_swedish",
    "tokens_of",
]
