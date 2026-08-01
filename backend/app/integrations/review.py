"""Invoice ↔ contract review: exact citations, transparent comparison, honest doubt.

What this does is narrow on purpose. It takes one
:class:`~app.integrations.models.InvoiceSnapshot`, finds candidate passages in
the tenant's own documents, and — only where a passage verifies **verbatim** —
compares a value it read there against a value the invoice carries. The result
is one of three words, never four:

    överensstämmer      a verified passage carries a value equal to the invoice's
    möjlig avvikelse    a verified passage carries a comparable value that differs
    kan inte verifieras nothing comparable verified

There is deliberately no "avviker". Asserting a deviation as fact would claim
the contract *says* something, and what was actually established is that the
passage that was found says something else — which is not the same, because the
term may live on a page retrieval did not surface.

**Why this is deterministic and not a model call.** Every number in a finding is
read out of a span that passed :func:`app.citations.resolve_citation` — the same
verbatim check, the same wrong-occurrence guard and the same all-or-nothing rule
as an answer's citations. A generated comparison would put a number in front of
a board member that no verification stands behind, which is precisely the
failure this product exists to avoid. The ``suggestion`` field says what to look
at in plain Swedish and is labelled ``regelmotor``, because that is what wrote
it.

**Where it fails.** It reads amounts and ISO date ranges. A contract that
expresses its price as "index enligt SCB:s entreprenadindex" carries no
comparable value, and this returns *kan inte verifieras* rather than guessing —
which is the correct answer, and the one a reviewer can act on.
"""

from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal
from typing import Iterable

from ..citations import Rejected, Resolved, resolve_citation
from ..schemas import CitationOut, Chunk
from ..store import Store
from .models import (
    VERDICT_LABELS,
    InvoiceSnapshot,
    ReviewFinding,
    Verdict,
    VerifiedFact,
    utc_now_iso,
)

logger = logging.getLogger("brf.integrations.review")

# How many retrieval candidates are examined for a comparable value. Small on
# purpose: a reviewer reads citations, and twenty of them is not review.
MAX_CANDIDATE_CHUNKS = 8
# Words of context kept around a matched value. Enough to carry the term it
# belongs to ("ersättning ... 12 500 kr per månad"), short enough that a
# citation does not paint the page.
QUOTE_WINDOW_BEFORE = 12
QUOTE_WINDOW_AFTER = 8

# Amount equality tolerance. Öre, not "close enough".
AMOUNT_EPSILON = Decimal("0.01")

_CURRENCY_TOKENS = {"kr", "kr.", "sek", "kronor", "kronor.", ":-"}

# What kind of quantity an amount is. Comparing across these classes is how a
# review invents a deviation: a contract that says "1 250 kronor per timme" and
# an invoice totalling 6 250 kr are not in disagreement, and a rule that
# subtracts one from the other would say they are.
#
#   rate      a price per unit of something — per timme, per säck, per styck
#   periodic  an amount per period — per månad, per kvartal, per år
#   plain     an amount with no qualifier — treated as a total
AmountUnit = str

_RATE_UNITS = {"timme", "timma", "tim", "h", "säck", "sack", "styck", "st", "kvadratmeter", "kvm", "m2"}
_PERIODIC_UNITS = {"månad", "manad", "kvartal", "år", "ar", "vecka", "halvår"}
# How far after an amount a qualifier may sit: "1 250 kronor per timme" is
# three tokens, "450 kr/tim" is one.
_UNIT_LOOKAHEAD = 4
_THOUSANDS_GROUP = re.compile(r"^\d{3}$")
_NUMERIC_HEAD = re.compile(r"^\d{1,3}$")
_PLAIN_NUMBER = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_DECIMAL_TAIL = re.compile(r"^[.,]\d{1,2}$")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Terms that make a passage worth reading for a price. Used only to build the
# retrieval query — never to decide anything.
_CONTRACT_TERMS = (
    "avtal ersättning pris belopp månadsavgift arvode avtalsperiod "
    "giltighetstid uppsägning indexreglering"
)

# A date range only counts as a *period* when one of these stands shortly
# before it. Without the requirement, an invoice header's issue and due dates
# read as an agreement period — which is what the first run of this engine did.
_PERIOD_KEYWORDS = {
    "period",
    "perioden",
    "avtalsperiod",
    "avtalsperioden",
    "avtalstid",
    "avtalstiden",
    "giltighetstid",
    "gäller",
    "löper",
    "från",
    "fr.o.m",
    "t.o.m",
    "avser",
    "mellan",
}
_PERIOD_CONTEXT = 4


# ---------------------------------------------------------------------------
# Reading values out of page words
# ---------------------------------------------------------------------------


_EDGE_PUNCT = " \t()[]{}.,;:!?\"'§•·\u00a0"

# A number preceded by one of these is a year, a clause number or a page
# reference, whatever happens to stand near it. "År 2030 utförs omputsning" sits
# two tokens after "850 000 kronor." in the seeded maintenance plan, and
# without this guard the review read 2030 as an amount and compared it to an
# invoice.
_NOT_AN_AMOUNT_BEFORE = {"år", "§", "paragraf", "punkt", "sida", "sid", "nr", "no"}


def _clean(token: str) -> str:
    """Strip the punctuation that sits on a word in extracted PDF text.

    Trailing punctuation matters more here than it does for prose matching:
    ``"1 250 kronor per timme,"`` ends with a comma, and a unit classifier that
    compares ``"timme,"`` against ``"timme"`` decides the amount has no unit —
    which then compares an hourly rate against an invoice total and reports a
    deviation that does not exist. That was a real defect, found by running the
    review against the seeded snow-clearing contract.
    """
    return token.strip().strip(_EDGE_PUNCT)


def scan_amounts(words: list[str]) -> list[tuple[int, int, Decimal]]:
    """Every currency amount in ``words``, as ``(start, end_inclusive, value)``.

    PDF extraction splits "12 500,00 kr" into separate words, so a Swedish
    thousands-grouped amount is reassembled here rather than matched with one
    regular expression over joined text — joined text would lose the word
    indices that a citation span needs.

    A number counts as money only when a currency marker *follows* it within
    two tokens ("1 250 kronor"), or sits immediately before it ("SEK 1 250").
    An earlier version accepted a marker anywhere in a ±2 window, which made the
    year in "…850 000 kronor. År 2030 utförs…" an amount, because the previous
    sentence's "kronor." was still in range.
    """
    found: list[tuple[int, int, Decimal]] = []
    i = 0
    n = len(words)
    while i < n:
        head = _clean(words[i])
        if not (_NUMERIC_HEAD.fullmatch(head) or _PLAIN_NUMBER.fullmatch(head)):
            i += 1
            continue
        if i > 0 and _clean(words[i - 1]).lower() in _NOT_AN_AMOUNT_BEFORE:
            i += 1
            continue

        digits = head.replace(",", ".")
        end = i
        # Thousands groups: "12" "500" "000"
        j = i + 1
        while j < n and _THOUSANDS_GROUP.fullmatch(_clean(words[j])) and "." not in digits:
            digits += _clean(words[j])
            end = j
            j += 1
        # A decimal tail may arrive as its own token: "12 500" ",00"
        if j < n and "." not in digits and _DECIMAL_TAIL.fullmatch(_clean(words[j])):
            digits += _clean(words[j]).replace(",", ".")
            end = j
            j += 1

        after = {_clean(w).lower() for w in words[end + 1 : min(n, end + 3)]}
        before = {_clean(words[i - 1]).lower()} if i > 0 else set()
        if (after | before) & _CURRENCY_TOKENS:
            try:
                found.append((i, end, Decimal(digits)))
            except Exception:  # a token that looked numeric but is not
                pass
        i = end + 1
    return found


def amount_unit(words: list[str], end_index: int) -> AmountUnit:
    """Classify the amount ending at ``end_index`` by the qualifier after it."""
    tail = [
        _clean(w).lower().strip("/")
        for w in words[end_index + 1 : end_index + 1 + _UNIT_LOOKAHEAD]
    ]
    # "kr/tim" arrives as one token; split it so the unit is visible.
    expanded: list[str] = []
    for token in tail:
        expanded.extend(part for part in token.split("/") if part)
    for token in expanded:
        if token in _RATE_UNITS:
            return "rate"
        if token in _PERIODIC_UNITS:
            return "periodic"
    return "plain"


def scan_iso_periods(words: list[str]) -> list[tuple[int, int, str, str]]:
    """Date ranges as ``(start, end_inclusive, from_iso, to_iso)``.

    Two dates near each other are not automatically a period. An invoice header
    reading "Fakturadatum: 2026-02-03  Förfallodatum: 2026-03-05" produced a
    confident "citerad period 2026-02-03 – 2026-03-05" in the first run of this
    engine, which was simply false. So a period keyword has to stand within a
    few tokens before the first date, and the two dates must be adjacent or
    separated by one dash-like token.

    Handles both shapes extraction produces: two separate date tokens, and one
    token carrying both because the PDF had no space around the dash.
    """
    found: list[tuple[int, int, str, str]] = []
    for i, word in enumerate(words):
        dates = _ISO_DATE.findall(_clean(word))
        if not dates:
            continue
        context = {_clean(w).lower() for w in words[max(0, i - _PERIOD_CONTEXT) : i]}
        if not (context & _PERIOD_KEYWORDS):
            continue
        if len(dates) >= 2:
            found.append((i, i, dates[0], dates[1]))
            continue
        for j in range(i + 1, min(len(words), i + 3)):
            ahead = _ISO_DATE.findall(_clean(words[j]))
            if ahead:
                found.append((i, j, dates[0], ahead[0]))
                break
    return found


# ---------------------------------------------------------------------------
# Turning a word span into a verified citation
# ---------------------------------------------------------------------------


class _Candidate:
    """One chunk, with the page words it covers, ready to be read and cited."""

    def __init__(self, store: Store, chunk: Chunk) -> None:
        self.chunk = chunk
        pages = store.pages.get(chunk.document_id) or []
        self.page = pages[chunk.page - 1] if 1 <= chunk.page <= len(pages) else None
        self.words = [w.text for w in self.page.words] if self.page else []
        self.start = max(0, chunk.word_start)
        self.end = min(len(self.words) - 1, chunk.word_end) if self.words else -1

    @property
    def usable(self) -> bool:
        return self.page is not None and self.end >= self.start

    def slice(self) -> list[str]:
        return self.words[self.start : self.end + 1]

    def quote_for(self, local_start: int, local_end: int) -> str:
        """A contiguous run of the page's own words around a match.

        Built from the extracted words rather than from ``chunk.text`` so the
        quote is, by construction, findable at the cited location — the
        verifier is then a real check on the *span choice*, not a formality
        that a string built from the same string will always pass.
        """
        a = max(self.start, self.start + local_start - QUOTE_WINDOW_BEFORE)
        b = min(self.end, self.start + local_end + QUOTE_WINDOW_AFTER)
        return " ".join(self.words[a : b + 1]).strip()


def _citation(
    store: Store, chunk: Chunk, quote: str, score: float
) -> CitationOut | None:
    """Verify ``quote`` at ``chunk`` and build a citation, or return None."""
    result = resolve_citation(chunk, [quote], store.pages)
    if isinstance(result, Rejected):
        logger.debug("Citat avvisat (%s) för %s", result.reason, chunk.id)
        return None
    assert isinstance(result, Resolved)
    meta = store.documents.get(chunk.document_id)
    if meta is None:
        return None
    return CitationOut(
        document_id=chunk.document_id,
        document_name=meta.name,
        page=result.page,
        quote=quote,
        quotes=[quote],
        chunk_id=chunk.id,
        rects=result.rects,
        score=round(score, 4),
        approximate=meta.source == "scanned",
        corpus_origin=meta.corpus_origin,
    )


def incoming_document_ids(store: Store) -> set[str]:
    """Documents that arrived as attachments in the integration queue.

    These are excluded from being cited as evidence, and the reason is the most
    important rule in this module.

    An invoice PDF that was imported from a `.eml` becomes an ordinary document:
    indexed, retrievable, citable. Left in the candidate pool, the review then
    found "5 000 kronor" *in the invoice itself* and reported that the invoice
    agrees with the invoice — a verified citation, a confident verdict, and no
    information whatsoever. The first end-to-end run of this engine did exactly
    that.

    The rule that fixes it is not a filename check. It is that an incoming
    attachment is the material *being reviewed*, and the association's own
    archive is what carries authority to review it against. A contract that
    arrived by mail therefore does not count as evidence until someone uploads
    it to the archive deliberately — a real limitation, and the conservative
    direction to be wrong in.
    """
    incoming: set[str] = set()
    try:
        events = store.integrations.list_source_events()
    except Exception as exc:  # a broken queue must not silently widen evidence
        logger.error("Kunde inte läsa källhändelser för uteslutning: %s", exc)
        raise
    for event in events:
        for attachment in event.attachments:
            if attachment.document_id:
                incoming.add(attachment.document_id)
    return incoming


def _candidates(store: Store, invoice: InvoiceSnapshot) -> list[tuple[_Candidate, float]]:
    """Chunks worth reading for this invoice, best first."""
    query = f"{invoice.supplier_name} {_CONTRACT_TERMS}".strip()
    settings = store.settings
    excluded = incoming_document_ids(store)
    try:
        hits = store.index.search(
            query,
            weight=settings.searchWeighting / 100.0,
            candidates=settings.candidateCount,
            # Ask for more than MAX_CANDIDATE_CHUNKS: excluded incoming
            # attachments are filtered after ranking, and a pool that was
            # already trimmed to the limit would come back short.
            top_k=MAX_CANDIDATE_CHUNKS * 3,
            min_confidence=0.0,  # the verbatim check is the gate, not confidence
        )
    except Exception as exc:
        logger.warning("Retrieval misslyckades för fakturagranskning: %s", exc)
        return []
    out: list[tuple[_Candidate, float]] = []
    for hit in hits:
        if hit.document_id in excluded:
            continue
        chunk = store.chunks.get(hit.chunk_id)
        if chunk is None:
            continue
        candidate = _Candidate(store, chunk)
        if candidate.usable:
            out.append((candidate, hit.score))
        if len(out) >= MAX_CANDIDATE_CHUNKS:
            break
    return out


# ---------------------------------------------------------------------------
# The review
# ---------------------------------------------------------------------------


def _finding(
    invoice: InvoiceSnapshot,
    finding_type: str,
    verdict: Verdict,
    *,
    facts: Iterable[VerifiedFact] = (),
    citations: Iterable[CitationOut] = (),
    suggestion: str,
    uncertainty: str | None,
) -> ReviewFinding:
    return ReviewFinding(
        id=uuid.uuid4().hex[:12],
        tenant_id=invoice.tenant_id,
        finding_type=finding_type,  # type: ignore[arg-type]
        created_at=utc_now_iso(),
        invoice_id=invoice.id,
        source_event_id=invoice.source_event_id,
        verdict=verdict,
        verdict_label=VERDICT_LABELS[verdict],
        verified_facts=list(facts),
        citations=list(citations),
        suggestion=suggestion,
        uncertainty=uncertainty,
    ).with_label()


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} {currency}".replace(",", " ").replace(".", ",", 1)


def _supplier_mention(
    store: Store, invoice: InvoiceSnapshot, candidates: list[tuple[_Candidate, float]]
) -> tuple[CitationOut, str] | None:
    """A verified citation of the supplier's name, when a document carries it.

    This is what turns "retrieval ranked this document first" into "this
    document names the supplier on this page" — a fact rather than a ranking,
    and the anchor the whole review hangs on (see :func:`review_invoice`).
    """
    name_words = [w for w in invoice.supplier_name.split() if len(w) > 2]
    if not name_words:
        return None
    needle = [w.casefold() for w in name_words]
    for candidate, score in candidates:
        words = candidate.slice()
        lowered = [_clean(w).casefold() for w in words]
        for i in range(len(lowered) - len(needle) + 1):
            if lowered[i : i + len(needle)] == needle:
                quote = candidate.quote_for(i, i + len(needle) - 1)
                citation = _citation(store, candidate.chunk, quote, score)
                if citation is not None:
                    return citation, candidate.chunk.document_id
    return None


def review_invoice(store: Store, invoice: InvoiceSnapshot) -> list[ReviewFinding]:
    """Compare one invoice against the tenant's own documents.

    The review is anchored on the supplier's name. Unless some document names
    the supplier — verified verbatim, not merely ranked highly by retrieval —
    nothing in the archive is evidence about this invoice, and the only honest
    answer is *kan inte verifieras*.

    Without that anchor the engine compared an elevator company's call-out fee
    against the snow-clearing contract's hourly rate and reported a "möjlig
    avvikelse" of 13 750 kronor. Every part of that was verified: the amount
    was really in the document, the citation really resolved. It was still
    nonsense, because the two numbers were never about the same agreement.

    Never returns an empty list: "we looked and found nothing" is itself
    something a reviewer needs to see.
    """

    currency = invoice.currency or "SEK"
    candidates = _candidates(store, invoice)
    supplier = _supplier_mention(store, invoice, candidates)

    if supplier is None:
        return [
            _finding(
                invoice,
                "invoice_without_contract",
                "cannot_be_verified",
                facts=[
                    VerifiedFact(
                        label="Leverantör enligt fakturan",
                        value=invoice.supplier_name,
                        source="invoice",
                    ),
                    VerifiedFact(
                        label="Belopp enligt fakturan",
                        value=_money(invoice.total_amount, currency),
                        source="invoice",
                    ),
                ],
                suggestion=(
                    f"Inget dokument i föreningens arkiv namnger {invoice.supplier_name}. "
                    "Ladda upp avtalet, eller granska fakturan mot underlag utanför appen."
                ),
                uncertainty=(
                    "Utan ett dokument som namnger leverantören finns ingenting att "
                    "jämföra mot. Belopp i andra avtal är inte jämförbara med den här "
                    "fakturan, hur nära de än ligger i siffror. Observera att en bilaga "
                    "som kommit in i granskningskön inte räknas som underlag — den är "
                    "det som granskas, inte det som granskas mot."
                ),
            )
        ]

    # Only documents that name the supplier may carry evidence about this
    # invoice. Everything else in the archive is about something else.
    anchor_documents = {supplier[1]}
    anchored = [c for c in candidates if c[0].chunk.document_id in anchor_documents]

    findings: list[ReviewFinding] = []

    amount_finding = _review_amount(store, invoice, anchored, supplier, currency)
    if amount_finding is not None:
        findings.append(amount_finding)

    if invoice.period_start and invoice.period_end:
        period_finding = _review_period(store, invoice, anchored, supplier)
        if period_finding is not None:
            findings.append(period_finding)

    if not findings:
        findings.append(
            _finding(
                invoice,
                "invoice_without_contract",
                "cannot_be_verified",
                facts=[
                    VerifiedFact(
                        label="Leverantör enligt fakturan",
                        value=invoice.supplier_name,
                        source="invoice",
                    ),
                    VerifiedFact(
                        label="Leverantören namnges i dokumentet",
                        value=invoice.supplier_name,
                        source="document",
                        citation_index=0,
                    ),
                ],
                citations=[supplier[0]],
                suggestion=(
                    f"{supplier[0].document_name} namnger {invoice.supplier_name}, men "
                    "fakturan bär inget belopp och ingen period att jämföra."
                ),
                uncertainty=(
                    "Fakturan saknar de fält som den här granskningen kan jämföra."
                ),
            )
        )
    return findings


def _comparison_targets(invoice: InvoiceSnapshot) -> list[tuple[str, str, Decimal]]:
    """What an amount in a contract could legitimately be compared against.

    Each entry is ``(unit class, human label, value)``. The unit class is what
    keeps the comparison like-for-like: a contract's per-hour rate is only ever
    matched against an invoice line's unit price, never against the invoice
    total, because those two numbers are not claims about the same thing.
    """
    targets: list[tuple[str, str, Decimal]] = []
    if invoice.total_amount is not None:
        targets.append(("plain", "fakturans totalbelopp inklusive moms", invoice.total_amount))
        if invoice.vat_amount is not None:
            targets.append(
                (
                    "plain",
                    "fakturans totalbelopp exklusive moms",
                    invoice.total_amount - invoice.vat_amount,
                )
            )
        # An invoice that declares a period is itself a periodic amount.
        if invoice.period_start and invoice.period_end:
            targets.append(("periodic", "fakturans belopp för perioden", invoice.total_amount))
            if invoice.vat_amount is not None:
                targets.append(
                    (
                        "periodic",
                        "fakturans belopp för perioden exklusive moms",
                        invoice.total_amount - invoice.vat_amount,
                    )
                )
    for line in invoice.lines:
        if line.unit_price is not None:
            label = f"à-pris för {line.description}" if line.description else "à-pris på fakturaraden"
            targets.append(("rate", label, line.unit_price))
    return targets


def _review_amount(
    store: Store,
    invoice: InvoiceSnapshot,
    candidates: list[tuple[_Candidate, float]],
    supplier: tuple[CitationOut, str] | None,
    currency: str,
) -> ReviewFinding | None:
    targets = _comparison_targets(invoice)
    if not targets:
        return None

    invoice_facts = [
        VerifiedFact(
            label="Leverantör enligt fakturan", value=invoice.supplier_name, source="invoice"
        )
    ]
    if invoice.total_amount is not None:
        invoice_facts.append(
            VerifiedFact(
                label="Fakturabelopp", value=_money(invoice.total_amount, currency), source="invoice"
            )
        )
    if invoice.vat_amount is not None:
        invoice_facts.append(
            VerifiedFact(
                label="Varav moms", value=_money(invoice.vat_amount, currency), source="invoice"
            )
        )
    for line in invoice.lines:
        if line.unit_price is not None:
            invoice_facts.append(
                VerifiedFact(
                    label=f"À-pris enligt fakturan — {line.description or 'rad'}",
                    value=_money(line.unit_price, currency),
                    source="invoice",
                )
            )

    citations: list[CitationOut] = []
    if supplier is not None:
        citations.append(supplier[0])
        invoice_facts.append(
            VerifiedFact(
                label="Leverantören namnges i dokumentet",
                value=invoice.supplier_name,
                source="document",
                citation_index=0,
            )
        )

    # value, unit, citation, target label, target value
    match: tuple[Decimal, str, CitationOut, str, Decimal] | None = None
    nearest: tuple[Decimal, str, CitationOut, str, Decimal] | None = None
    verified_any_amount = False

    for candidate, score in candidates:
        words = candidate.slice()
        for local_start, local_end, value in scan_amounts(words):
            unit = amount_unit(words, local_end)
            comparable = [t for t in targets if t[0] == unit]
            if not comparable:
                # A per-säck price on an invoice with no per-säck line is not a
                # deviation and not evidence. It is simply not comparable, and
                # saying nothing about it is the honest handling.
                continue
            quote = candidate.quote_for(local_start, local_end)
            citation = _citation(store, candidate.chunk, quote, score)
            if citation is None:
                continue
            verified_any_amount = True
            for _, label, target_value in comparable:
                delta = abs(value - target_value)
                if delta <= AMOUNT_EPSILON:
                    match = (value, unit, citation, label, target_value)
                    break
                if nearest is None or delta < abs(nearest[0] - nearest[4]):
                    nearest = (value, unit, citation, label, target_value)
            if match is not None:
                break
        if match is not None:
            break

    if match is not None:
        value, unit, citation, label, target_value = match
        citations.append(citation)
        invoice_facts.append(
            VerifiedFact(
                label="Belopp i citerat villkor",
                value=_money(value, currency),
                source="document",
                citation_index=len(citations) - 1,
            )
        )
        return _finding(
            invoice,
            "invoice_contract_amount",
            "matches",
            facts=invoice_facts,
            citations=citations,
            suggestion=(
                f"{label.capitalize()} ({_money(target_value, currency)}) motsvarar det "
                f"citerade villkoret i {citation.document_name} s. {citation.page}."
            ),
            uncertainty=(
                "Jämförelsen gäller det citerade villkoret och ingenting annat. "
                "Antal timmar, mängder, indexuppräkning, tillägg och senare ändringar "
                "är inte kontrollerade."
            ),
        )

    if nearest is not None:
        value, unit, citation, label, target_value = nearest
        citations.append(citation)
        invoice_facts.append(
            VerifiedFact(
                label="Närmast jämförbara belopp i citerat villkor",
                value=_money(value, currency),
                source="document",
                citation_index=len(citations) - 1,
            )
        )
        return _finding(
            invoice,
            "invoice_contract_amount",
            "possible_deviation",
            facts=invoice_facts,
            citations=citations,
            suggestion=(
                f"{label.capitalize()} är {_money(target_value, currency)}. Det jämförbara "
                f"beloppet i {citation.document_name} s. {citation.page} är "
                f"{_money(value, currency)} — en skillnad på "
                f"{_money(abs(target_value - value), currency)}. Kontrollera villkoret "
                "innan fakturan hanteras."
            ),
            uncertainty=(
                "Det här är inte ett konstaterat avtalsbrott. Det citerade beloppet är "
                "det enda jämförbara som gick att verifiera; villkoret kan avse en annan "
                "period eller tjänst, ett belopp före indexuppräkning, eller ha ändrats "
                "genom ett tillägg som inte finns i den citerade passagen."
            ),
        )

    return _finding(
        invoice,
        "invoice_contract_amount",
        "cannot_be_verified",
        facts=invoice_facts,
        citations=citations,
        suggestion=(
            "Inget jämförbart belopp i föreningens dokument gick att verifiera mot "
            "fakturan. Granska manuellt."
        ),
        uncertainty=(
            "Inga belopp kunde citeras ordagrant som jämförbara med fakturan."
            if not verified_any_amount
            else "Belopp gick att verifiera i dokumenten, men inget av dem avser samma "
            "sorts kvantitet som fakturan — ett à-pris kan inte jämföras med ett "
            "totalbelopp utan att antal och mängder är kända."
        ),
    )


def _review_period(
    store: Store,
    invoice: InvoiceSnapshot,
    candidates: list[tuple[_Candidate, float]],
    supplier: tuple[CitationOut, str] | None,
) -> ReviewFinding | None:
    assert invoice.period_start and invoice.period_end

    facts = [
        VerifiedFact(
            label="Fakturaperiod",
            value=f"{invoice.period_start} – {invoice.period_end}",
            source="invoice",
        )
    ]
    citations: list[CitationOut] = []
    if supplier is not None:
        citations.append(supplier[0])

    for candidate, score in candidates:
        words = candidate.slice()
        for local_start, local_end, start_iso, end_iso in scan_iso_periods(words):
            quote = candidate.quote_for(local_start, local_end)
            citation = _citation(store, candidate.chunk, quote, score)
            if citation is None:
                continue
            citations.append(citation)
            facts.append(
                VerifiedFact(
                    label="Period i citerat villkor",
                    value=f"{start_iso} – {end_iso}",
                    source="document",
                    citation_index=len(citations) - 1,
                )
            )
            inside = start_iso <= invoice.period_start and invoice.period_end <= end_iso
            if inside:
                return _finding(
                    invoice,
                    "invoice_contract_period",
                    "matches",
                    facts=facts,
                    citations=citations,
                    suggestion=(
                        f"Fakturaperioden ligger inom den citerade avtalsperioden "
                        f"{start_iso} – {end_iso} i {citation.document_name} s. {citation.page}."
                    ),
                    uncertainty=(
                        "Att perioden ryms i avtalstiden säger ingenting om att just "
                        "den här tjänsten är beställd för perioden."
                    ),
                )
            return _finding(
                invoice,
                "invoice_contract_period",
                "possible_deviation",
                facts=facts,
                citations=citations,
                suggestion=(
                    f"Fakturaperioden {invoice.period_start} – {invoice.period_end} ligger "
                    f"helt eller delvis utanför den citerade perioden {start_iso} – {end_iso} "
                    f"i {citation.document_name} s. {citation.page}. Kontrollera om avtalet "
                    "är förlängt eller om fakturan avser något annat."
                ),
                uncertainty=(
                    "Perioden kan vara förlängd genom ett tillägg eller en automatisk "
                    "förlängningsklausul som inte finns i den citerade passagen."
                ),
            )

    return _finding(
        invoice,
        "invoice_contract_period",
        "cannot_be_verified",
        facts=facts,
        citations=citations,
        suggestion=(
            "Ingen avtalsperiod gick att verifiera i föreningens dokument. "
            "Granska fakturaperioden manuellt."
        ),
        uncertainty=(
            "Ingen daterad period kunde citeras ordagrant. Avtalstiden kan vara "
            "uttryckt i löptid ('tolv månader från undertecknande') i stället för "
            "med datum."
        ),
    )
