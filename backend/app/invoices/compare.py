"""What changed, what repeats, and what has never been seen before.

The contract review (:mod:`app.integrations.review`) answers one question: does
this invoice agree with a passage in the association's own documents. This
module answers the three questions a board asks *before* that one, and it
answers them out of the association's own invoice history rather than out of a
model:

* **Has this changed?** Against the previous invoice from the same supplier,
  with the difference decomposed into the part the invoice explains itself
  (a quantity that went up) and the part it does not (a unit price that went
  up). Those are different sentences to a reviewer and the second is the only
  one worth chasing.
* **Have we seen this already?** Exact and near duplicates across every source
  the association has read from, plus the credit invoice that would explain a
  matching amount with the opposite sign.
* **Is any of this new?** A line description that has never appeared from this
  supplier is not a deviation and is not nothing; it is a question.

Every finding produced here is a :class:`~app.integrations.models.ReviewFinding`
with the same three verdicts as everything else in this domain, and every
number in one is read out of a stored invoice record — not inferred, not
generated. There are no citations on these findings, because there is no
document behind them; what stands behind them is the association's own earlier
invoice, named by number and date so it can be opened.

**Why there is no fourth verdict.** "Verified", "likely deviation", "needs
documentation" and "no deviation found" map onto the three words this product
already uses — *överensstämmer* covers both "verified" and "no deviation found",
because in this domain they are the same statement. Adding a fourth would mean
asserting a deviation as fact, which is exactly what
``docs/INTEGRATIONSDOMAN.md`` §5 refuses.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Iterable

from ..integrations.models import (
    VERDICT_LABELS,
    InvoiceSnapshot,
    ReviewFinding,
    Verdict,
    VerifiedFact,
    utc_now_iso,
)
from ..integrations.supplier import core_tokens, is_distinctive
from ..integrations.supplier import normalize as normalize_supplier
from .identity import number_key
from .models import InvoiceCase

# Öre, not "close enough" — same tolerance the contract review compares with.
AMOUNT_EPSILON = Decimal("0.01")

# How far apart two invoices for the same amount may sit and still be worth
# raising as a possible duplicate. A month: a supplier that bills monthly for
# the same amount is normal and must not light up every month, but two copies
# of one invoice a fortnight apart is exactly the thing that gets paid twice.
NEAR_DUPLICATE_DAYS = 21

_WS = re.compile(r"\s+")


def money(value: Decimal | None, currency: str = "SEK") -> str:
    """A Swedish amount. Local to this package so no private import is needed."""
    if value is None:
        return "—"
    return f"{value:,.2f} {currency}".replace(",", " ").replace(".", ",", 1)


def percent(old: Decimal, new: Decimal) -> str | None:
    """The change as a percentage, or ``None`` when there is nothing to divide by."""
    if old == 0:
        return None
    try:
        share = (new - old) / old * Decimal(100)
    except (InvalidOperation, ZeroDivisionError):  # pragma: no cover - defensive
        return None
    rounded = share.quantize(Decimal("0.1"))
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded}".replace(".", ",") + " %"


def _description_key(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip().lower()


def _days_between(a: str | None, b: str | None) -> int | None:
    from ..terms import parse_iso

    first, second = parse_iso(a or ""), parse_iso(b or "")
    if first is None or second is None:
        return None
    return abs((first - second).days)


def finding(
    snapshot: InvoiceSnapshot,
    finding_type: str,
    verdict: Verdict,
    *,
    facts: Iterable[VerifiedFact] = (),
    suggestion: str,
    uncertainty: str | None,
) -> ReviewFinding:
    """One finding about this invoice's own history. No citations by design.

    A citation in this product means a verbatim-verified passage in a document.
    A comparison against last month's invoice has no such passage — what stands
    behind it is a stored record, named in the facts by number and date. Making
    up a citation shape for it would be the first place the word stopped
    meaning what it means everywhere else.
    """
    return ReviewFinding(
        id=uuid.uuid4().hex[:12],
        tenant_id=snapshot.tenant_id,
        finding_type=finding_type,  # type: ignore[arg-type]
        created_at=utc_now_iso(),
        invoice_id=snapshot.id,
        source_event_id=snapshot.source_event_id,
        verdict=verdict,
        verdict_label=VERDICT_LABELS[verdict],
        verified_facts=list(facts),
        suggestion=suggestion,
        uncertainty=uncertainty,
    )


# ---------------------------------------------------------------------------
# Against the previous invoice
# ---------------------------------------------------------------------------


def previous_snapshot(
    snapshot: InvoiceSnapshot, history: list[InvoiceSnapshot]
) -> InvoiceSnapshot | None:
    """The same supplier's most recent earlier invoice, or ``None``.

    "Earlier" is by invoice date, falling back on the retrieval time when a
    source carries no date. Ties are broken by external reference so the answer
    is stable — a comparison that picked a different baseline on every run
    would make the change history unreadable.
    """
    key = normalize_supplier(snapshot.supplier_name)
    if not key:
        return None
    mine = (snapshot.invoice_date or "", snapshot.external_ref)
    candidates = [
        row
        for row in history
        if row.id != snapshot.id
        and normalize_supplier(row.supplier_name) == key
        and row.total_amount is not None
        and (row.invoice_date or "", row.external_ref) < mine
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r.invoice_date or "", r.external_ref))


def _line_changes(
    current: InvoiceSnapshot, previous: InvoiceSnapshot
) -> tuple[list[VerifiedFact], list[str], list[str]]:
    """Per-line decomposition into what the invoice explains and what it does not.

    ``Δbelopp = p₀·(q₁−q₀) + q₁·(p₁−p₀)``: the first term is the quantity
    effect and the second is the price effect. That split is the whole point.
    A snow-clearing invoice that doubled because it snowed twice as much is not
    the same event as one that doubled because the hourly rate went up, and a
    review that reports "+4 625 kr" without saying which is not review.
    """
    before = {_description_key(line.description): line for line in previous.lines}
    facts: list[VerifiedFact] = []
    explained: list[str] = []
    unexplained: list[str] = []
    currency = current.currency or "SEK"

    for line in current.lines:
        earlier = before.get(_description_key(line.description))
        if earlier is None:
            continue
        label = line.description or "fakturarad"
        if (
            line.unit_price is not None
            and earlier.unit_price is not None
            and line.unit_price != earlier.unit_price
        ):
            share = percent(earlier.unit_price, line.unit_price)
            facts.append(
                VerifiedFact(
                    label=f"À-pris {label}",
                    value=(
                        f"{money(earlier.unit_price, currency)} → "
                        f"{money(line.unit_price, currency)}"
                        + (f" ({share})" if share else "")
                    ),
                    source="invoice",
                )
            )
            effect = (line.quantity or Decimal(1)) * (line.unit_price - earlier.unit_price)
            unexplained.append(
                f"à-priset för {label} har gått från {money(earlier.unit_price, currency)} "
                f"till {money(line.unit_price, currency)}"
                + (f" ({share})" if share else "")
                + f", vilket är {money(effect, currency)} av skillnaden"
            )
        if (
            line.quantity is not None
            and earlier.quantity is not None
            and line.quantity != earlier.quantity
        ):
            facts.append(
                VerifiedFact(
                    label=f"Antal {label}",
                    value=f"{earlier.quantity} → {line.quantity}",
                    source="invoice",
                )
            )
            effect = (earlier.unit_price or Decimal(0)) * (line.quantity - earlier.quantity)
            explained.append(
                f"antalet för {label} har gått från {earlier.quantity} till {line.quantity}"
                + (
                    f", vilket förklarar {money(effect, currency)} av skillnaden"
                    if earlier.unit_price is not None
                    else ""
                )
            )
    return facts, explained, unexplained


def previous_comparison(
    snapshot: InvoiceSnapshot, history: list[InvoiceSnapshot]
) -> ReviewFinding:
    """How this invoice differs from the last one from the same supplier."""
    currency = snapshot.currency or "SEK"
    previous = previous_snapshot(snapshot, history)

    if previous is None:
        return finding(
            snapshot,
            "invoice_previous_comparison",
            "cannot_be_verified",
            facts=[
                VerifiedFact(
                    label="Leverantör enligt fakturan",
                    value=snapshot.supplier_name,
                    source="invoice",
                ),
                VerifiedFact(
                    label="Fakturabelopp",
                    value=money(snapshot.total_amount, currency),
                    source="invoice",
                ),
            ],
            suggestion=(
                f"Det finns ingen tidigare inläst faktura från {snapshot.supplier_name} att "
                "jämföra med. Läs in en äldre faktura från samma leverantör om ni vill se "
                "förändringen över tid."
            ),
            uncertainty=(
                "Utan en tidigare faktura går det inte att säga om något har ändrats. "
                "Att ingen finns här betyder inte att ingen finns — bara att den inte är inläst."
            ),
        )

    label_previous = (
        f"Faktura {previous.invoice_number or previous.external_ref}"
        f" ({previous.invoice_date or 'utan datum'})"
    )
    facts = [
        VerifiedFact(label="Föregående faktura", value=label_previous, source="invoice"),
        VerifiedFact(
            label="Belopp föregående",
            value=money(previous.total_amount, previous.currency or currency),
            source="invoice",
        ),
        VerifiedFact(
            label="Belopp den här fakturan",
            value=money(snapshot.total_amount, currency),
            source="invoice",
        ),
    ]

    if snapshot.total_amount is None:
        return finding(
            snapshot,
            "invoice_previous_comparison",
            "cannot_be_verified",
            facts=facts,
            suggestion=(
                f"Den här fakturan bär inget totalbelopp, så den går inte att jämföra med "
                f"{label_previous}."
            ),
            uncertainty="Ett belopp som inte finns i källan kan inte jämföras med något.",
        )

    delta = snapshot.total_amount - previous.total_amount
    line_facts, explained, unexplained = _line_changes(snapshot, previous)
    facts.extend(line_facts)

    if abs(delta) <= AMOUNT_EPSILON:
        return finding(
            snapshot,
            "invoice_previous_comparison",
            "matches",
            facts=[
                *facts,
                VerifiedFact(label="Förändring", value="oförändrat belopp", source="invoice"),
            ],
            suggestion=(
                f"Beloppet är oförändrat mot {label_previous} "
                f"({money(previous.total_amount, currency)})."
            ),
            uncertainty=(
                "Att totalbeloppet är oförändrat säger ingenting om vad raderna innehåller, "
                "om tjänsten är utförd, eller om beloppet var rätt från början."
            ),
        )

    share = percent(previous.total_amount, snapshot.total_amount)
    direction = "högre" if delta > 0 else "lägre"
    facts.append(
        VerifiedFact(
            label="Förändring",
            value=f"{money(delta, currency)}" + (f" ({share})" if share else ""),
            source="invoice",
        )
    )

    parts = [
        f"Fakturan är {money(abs(delta), currency)} {direction} än {label_previous} "
        f"({money(previous.total_amount, currency)} → {money(snapshot.total_amount, currency)}"
        + (f", {share}" if share else "")
        + ")."
    ]
    if explained:
        parts.append("Fakturan förklarar själv en del av det: " + "; ".join(explained) + ".")
    if unexplained:
        parts.append(
            "Det här förklarar den inte: "
            + "; ".join(unexplained)
            + ". Stäm av mot avtalet eller be leverantören om grunden för höjningen."
        )
    elif not explained:
        parts.append(
            "Fakturaraderna säger inte vad skillnaden består i — raderna heter inte "
            "samma sak som förra gången, eller saknar antal och à-pris."
        )

    return finding(
        snapshot,
        "invoice_previous_comparison",
        "possible_deviation" if unexplained or not explained else "matches",
        facts=facts,
        suggestion=" ".join(parts),
        uncertainty=(
            "Det här är en jämförelse mellan två fakturor, inte mot ett avtal. En höjning "
            "kan vara helt avtalsenlig — indexreglerad, säsongsberoende eller beställd — "
            "och den här jämförelsen kan inte se någon av de sakerna."
        ),
    )


# ---------------------------------------------------------------------------
# Duplicates and credits
# ---------------------------------------------------------------------------


def supplier_relation(mine: str, theirs: str) -> str | None:
    """How two supplier names are related, or ``None`` if not at all.

    Deliberately looser than the contract review's anchor, and for the opposite
    reason. The anchor decides whether a document may be used as *evidence*
    about an invoice, so it has to be strict. This decides whether two invoices
    are worth putting in front of a person as possibly-the-same, and the
    dangerous error there is silence: "Snösvängen AB" and "Snösvängen
    Entreprenad AB" sending the same invoice number is exactly the pair a
    duplicate check exists for, and a check that only matched identical strings
    would miss it.

    The looseness is safe because nothing here is asserted as fact — the
    returned sentence is put in the finding so the reader can see the
    comparison was made on a partial name match and weigh it themselves.
    """
    if not mine or not theirs:
        return None
    if normalize_supplier(mine) == normalize_supplier(theirs):
        return "samma leverantörsnamn"
    shared = {t for t in core_tokens(mine) if is_distinctive(t)} & {
        t for t in core_tokens(theirs) if is_distinctive(t)
    }
    if not shared:
        return None
    return f"leverantörsnamnen delar det särskiljande ordet \"{sorted(shared)[0]}\""


def duplicate_findings(
    snapshot: InvoiceSnapshot,
    history: list[InvoiceSnapshot],
    *,
    case_key: str,
    key_of,
) -> list[ReviewFinding]:
    """Exact and near duplicates, plus a matching credit, across every source.

    ``key_of`` maps a snapshot to its case key, so two readings that already
    converged on one case are never reported as duplicates of each other — that
    is convergence working, not a finding.
    """
    currency = snapshot.currency or "SEK"
    mine = number_key(snapshot.invoice_number)
    out: list[ReviewFinding] = []

    for other in history:
        if other.id == snapshot.id or key_of(other) == case_key:
            continue
        relation = supplier_relation(snapshot.supplier_name, other.supplier_name)
        if relation is None:
            continue
        if snapshot.total_amount is None or other.total_amount is None:
            continue

        theirs = number_key(other.invoice_number)
        label = (
            f"Faktura {other.invoice_number or other.external_ref}"
            f" ({other.invoice_date or 'utan datum'}, {other.adapter})"
        )
        same_amount = abs(snapshot.total_amount - other.total_amount) <= AMOUNT_EPSILON
        gap = _days_between(snapshot.invoice_date, other.invoice_date)

        if mine and theirs and mine == theirs:
            out.append(
                finding(
                    snapshot,
                    "invoice_possible_duplicate",
                    "possible_deviation",
                    facts=[
                        VerifiedFact(label="Den här fakturan", value=f"{snapshot.invoice_number or snapshot.external_ref} — {money(snapshot.total_amount, currency)}", source="invoice"),
                        VerifiedFact(label="Redan inläst", value=f"{label} — {money(other.total_amount, currency)}", source="invoice"),
                        VerifiedFact(
                            label="Belopp",
                            value="samma belopp" if same_amount else "olika belopp",
                            source="invoice",
                        ),
                        VerifiedFact(label="Kopplingen bygger på", value=relation, source="invoice"),
                    ],
                    suggestion=(
                        f"Samma fakturanummer finns redan inläst som {label} ({relation}). "
                        + (
                            "Beloppen är identiska — kontrollera att fakturan inte är på väg att "
                            "betalas två gånger."
                            if same_amount
                            else "Beloppen skiljer sig, vilket kan betyda en rättad eller "
                            "omskriven faktura."
                        )
                    ),
                    uncertainty=(
                        "Två poster med samma nummer behöver inte vara samma faktura — en "
                        "leverantör kan återanvända nummerserier mellan år, och en läsning ur "
                        "två system kan ha delat upp samma faktura på två referenser. "
                        "Ingenting här kan avgöra vilket det är."
                    ),
                )
            )
            continue

        if same_amount and gap is not None and gap <= NEAR_DUPLICATE_DAYS:
            out.append(
                finding(
                    snapshot,
                    "invoice_possible_duplicate",
                    "possible_deviation",
                    facts=[
                        VerifiedFact(label="Den här fakturan", value=f"{money(snapshot.total_amount, currency)} den {snapshot.invoice_date or '—'}", source="invoice"),
                        VerifiedFact(label="Liknande post", value=f"{label} — {money(other.total_amount, currency)}", source="invoice"),
                        VerifiedFact(label="Dagar emellan", value=str(gap), source="invoice"),
                        VerifiedFact(label="Kopplingen bygger på", value=relation, source="invoice"),
                    ],
                    suggestion=(
                        f"Samma belopp som {label} ({relation}), {gap} dagar isär, men "
                        "med olika fakturanummer. Kontrollera om det är två fakturor eller en "
                        "faktura som kommit in två vägar."
                    ),
                    uncertainty=(
                        "Ett återkommande abonnemang ser precis så här ut och är då helt "
                        "korrekt. Det här är en flagga, inte ett fel."
                    ),
                )
            )

        if (
            snapshot.total_amount != 0
            and abs(snapshot.total_amount + other.total_amount) <= AMOUNT_EPSILON
        ):
            # Which of the two is the credit note is not a detail. A negative
            # amount credits a positive one and never the other way round, so a
            # single sentence for both directions is wrong in one of them — and
            # it is wrong exactly when the invoice on the screen is the credit
            # note, which is the case a reviewer opens a credit note to read.
            crediting = snapshot.total_amount < 0
            out.append(
                finding(
                    snapshot,
                    "invoice_credit_relation",
                    "matches",
                    facts=[
                        VerifiedFact(label="Den här fakturan", value=money(snapshot.total_amount, currency), source="invoice"),
                        VerifiedFact(label="Motsvarande post", value=f"{label} — {money(other.total_amount, currency)}", source="invoice"),
                    ],
                    suggestion=(
                        f"Den här posten är negativ och tar exakt ut {label}. Den kan vara "
                        "krediteringen av den fakturan."
                        if crediting
                        else f"{label} har exakt motsatt belopp och kan vara krediteringen av den "
                        "här fakturan."
                    ),
                    uncertainty=(
                        "Att två belopp tar ut varandra betyder inte att krediteringen avser "
                        "just den här fakturan. Ingenting i underlaget säger vilken faktura en "
                        "kreditnota hör till."
                    ),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Lines nobody has seen before
# ---------------------------------------------------------------------------


def new_line_finding(
    snapshot: InvoiceSnapshot, history: list[InvoiceSnapshot]
) -> ReviewFinding | None:
    """Lines from this supplier that have never appeared before.

    Not a deviation — a question. A new fee may be perfectly agreed; what is
    established is only that the association's own invoice history has never
    carried it, and that is exactly the kind of thing a board wants to be told
    once rather than discover in a year.
    """
    supplier = normalize_supplier(snapshot.supplier_name)
    if not supplier or not snapshot.lines:
        return None
    seen: set[str] = set()
    earlier = 0
    for row in history:
        if row.id == snapshot.id or normalize_supplier(row.supplier_name) != supplier:
            continue
        earlier += 1
        seen.update(_description_key(line.description) for line in row.lines)
    if earlier == 0:
        # With no history, everything is new and saying so is noise.
        return None
    fresh = [
        line
        for line in snapshot.lines
        if line.description and _description_key(line.description) not in seen
    ]
    if not fresh:
        return None
    currency = snapshot.currency or "SEK"
    return finding(
        snapshot,
        "invoice_new_line",
        "cannot_be_verified",
        facts=[
            VerifiedFact(
                label="Ny rad",
                value=f"{line.description} — {money(line.amount, currency)}",
                source="invoice",
            )
            for line in fresh
        ],
        suggestion=(
            ("Den här raden har" if len(fresh) == 1 else "De här raderna har")
            + f" inte förekommit på någon tidigare inläst faktura från {snapshot.supplier_name}: "
            + "; ".join(line.description for line in fresh)
            + ". Kontrollera att den ingår i avtalet eller är beställd."
        ),
        uncertainty=(
            f"Jämförelsen gäller {earlier} tidigare inläst"
            + ("a fakturor" if earlier != 1 else " faktura")
            + " från den här leverantören och ingenting annat. En rad kan vara ny för oss och "
            "gammal i avtalet, och en rad som bara stavats om räknas som ny här."
        ),
    )


def analyse_history(
    snapshot: InvoiceSnapshot,
    history: list[InvoiceSnapshot],
    *,
    case: InvoiceCase,
    key_of,
) -> list[ReviewFinding]:
    """Every history-based finding for one invoice, in reading order."""
    findings = [previous_comparison(snapshot, history)]
    findings.extend(
        duplicate_findings(snapshot, history, case_key=case.case_key, key_of=key_of)
    )
    fresh = new_line_finding(snapshot, history)
    if fresh is not None:
        findings.append(fresh)
    return findings


__all__ = [
    "AMOUNT_EPSILON",
    "NEAR_DUPLICATE_DAYS",
    "analyse_history",
    "duplicate_findings",
    "finding",
    "money",
    "new_line_finding",
    "percent",
    "previous_comparison",
    "previous_snapshot",
]
