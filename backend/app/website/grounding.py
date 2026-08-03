"""The grounding gate, applied to what a model writes on the public website.

This product's whole claim is that it will refuse rather than invent. A website
builder is where that claim is easiest to lose: nobody asked the AI a question,
so there is no answer to verify — it was asked to *write something*, and prose
composed to fill a page is exactly the prose that invents an amount, a date or a
deadline nobody can point to.

So the same gate that protects an answer protects a published page, reusing
:func:`app.numeric_grounding.check_numeric_grounding` rather than growing a
second, weaker rule beside it. Every material number in text a model wrote must
appear in something that actually supports it, or the command is refused and
nothing is written.

**What counts as support, and the one honest difference from the answer path.**
:mod:`app.numeric_grounding` warns that the user's own question must never
support an answer, and that is right there: a person asking "stämmer det att
avgiften höjs 4%?" has not established anything, and letting the question
support the answer would let the model agree with whatever it was handed.

Authoring is a different act. When a board member types *"skriv att vattnet
stängs av 12 mars 08–15"*, the date is not a claim the model produced — it is
the association telling its own website what to say, and it is the association's
to say. Refusing it would not protect anyone; it would only mean the board
cannot use the feature for the announcements it exists to write. So the
operator's own instruction is support **here and nowhere else**, and that
narrowing is the reason this lives in its own module instead of as a flag on the
shared one.

Everything else the model asserts must come from the association's documents,
through the ordinary retrieval-and-verification path, arriving as accepted
:class:`~app.schemas.CitationOut` spans attached to the block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..numeric_grounding import check_numeric_grounding, describe_mismatch
from ..schemas import CitationOut
from .components import CLAIM_BEARING, spec_for
from .sanitize import plain_text


@dataclass(frozen=True)
class GroundingVerdict:
    ok: bool
    reason: str = ""          # Swedish, shown to the operator when refused
    unsupported: tuple[str, ...] = ()


def claim_text(component_type: str, props: dict) -> str:
    """Every piece of a block a reader would take as a statement of fact.

    Walks only the fields whose kind is claim-bearing (see
    :data:`app.website.components.CLAIM_BEARING`), including the subfields of
    list items — a date inside a calendar row is as much a claim as one in a
    paragraph, and skipping it would leave the most fact-dense block in the
    vocabulary ungated.
    """
    spec = spec_for(component_type)
    parts: list[str] = []

    def take(kind: str, value) -> None:
        if kind == "richtext":
            parts.append(plain_text(str(value or "")))
        elif isinstance(value, str):
            parts.append(value)

    for name, field in spec.fields.items():
        value = props.get(name)
        if field.kind == "list":
            for row in value or []:
                if not isinstance(row, dict):
                    continue
                for sub_name, sub in field.fields.items():
                    # Dates inside list rows are claims too — and they are
                    # stored as ÅÅÅÅ-MM-DD, whose digits the numeric gate reads.
                    if sub.kind in CLAIM_BEARING or sub.kind == "date":
                        take(sub.kind, row.get(sub_name))
        elif field.kind in CLAIM_BEARING or field.kind == "date":
            take(field.kind, value)

    return " ".join(p for p in parts if p)


def support_quotes(sources: Iterable[CitationOut]) -> list[str]:
    """The verified spans behind a block — and only those.

    Mirrors the answer pipeline's contract exactly: a citation's *verified*
    quote spans are support, its document name and page number are not.
    """
    quotes: list[str] = []
    for citation in sources:
        quotes.extend(citation.quotes or ([citation.quote] if citation.quote else []))
    return quotes


def check_written_content(
    component_type: str,
    props: dict,
    *,
    sources: Iterable[CitationOut] = (),
    instruction: str = "",
    trusted_names: Iterable[str] = (),
) -> GroundingVerdict:
    """Gate one block's model-written content. Callers pass human writes straight through.

    ``instruction`` is the operator's own words for this change — support, for
    the reason argued in this module's docstring. ``trusted_names`` is the
    association's own name, handed through to the shared gate so that
    "Brf Gjutformen 12" is not read as a claim about the number twelve.
    """
    text = claim_text(component_type, props)
    if not text.strip():
        return GroundingVerdict(ok=True)

    support = support_quotes(sources)
    if instruction.strip():
        support.append(instruction)

    result = check_numeric_grounding(text, support, trusted_names=trusted_names)
    if result.ok:
        return GroundingVerdict(ok=True)

    missing = describe_mismatch(result)
    return GroundingVerdict(
        ok=False,
        unsupported=tuple(claim.raw for claim in result.unsupported),
        reason=(
            f"AI:n ville skriva {missing} på sidan, men det finns inte i föreningens "
            "dokument och stod inte i din instruktion. Ändringen skrevs inte. "
            "Be om texten igen med uppgiften i frågan, eller lägg in dokumentet den "
            "ska hämtas ur."
        ),
    )


def prose_text(component_type: str, props: dict) -> str:
    """The parts of a block a reader takes as *statements*, not as labels.

    Deliberately narrower than :func:`claim_text`: a heading, a button word or a
    menu label cannot really assert anything on its own, while a paragraph can
    assert almost anything. The distinction is what makes the review state below
    proportionate instead of a nag on every generated heading.
    """
    spec = spec_for(component_type)
    parts: list[str] = []
    for name, field in spec.fields.items():
        value = props.get(name)
        if field.kind in ("richtext", "textarea") and isinstance(value, str):
            parts.append(plain_text(value) if field.kind == "richtext" else value)
        elif field.kind == "list":
            for row in value or []:
                if not isinstance(row, dict):
                    continue
                for sub_name, sub in field.fields.items():
                    sub_value = row.get(sub_name)
                    if sub.kind in ("richtext", "textarea") and isinstance(sub_value, str):
                        parts.append(plain_text(sub_value) if sub.kind == "richtext" else sub_value)
    return " ".join(p for p in parts if p.strip())


def grounding_label(component_type: str, props: dict, sources: Iterable[CitationOut]) -> str:
    """What a model-written block may call itself.

    - ``grounded`` — citations came back from the association's own documents.
    - ``unverified`` — the model wrote **prose** with nothing behind it.
    - ``editorial`` — the model wrote only labels, which cannot carry a claim.

    The middle case is the one this function exists for. The numeric gate above
    catches an invented amount or date; it cannot catch *"Grillning är förbjuden
    i föreningen"*, which contains no digit, is entirely fabricated, and used to
    be labelled ``editorial`` and published like anything else.

    Detecting that semantically is not something this product can honestly claim
    to do, so it does not try. It marks the text, shows it in the draft, and
    **refuses to publish the page** until a person adopts it — by editing it, or
    by saying so. That is the same asymmetry the rest of the product runs on: a
    machine may read and propose, but nobody's words become the association's
    until a person makes them so.
    """
    if list(sources):
        return "grounded"
    return "unverified" if prose_text(component_type, props).strip() else "editorial"


__all__ = [
    "GroundingVerdict",
    "check_written_content",
    "claim_text",
    "grounding_label",
    "prose_text",
    "support_quotes",
]
