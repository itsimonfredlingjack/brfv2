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

**What it reads.** Amounts, and periods written as ISO dates or in Swedish
("från den 1 november 2026 och tills vidare"). Terms it can read but cannot
compare — an index-regulated price, "tolv (12) månader från undertecknande", a
notice period — are cited as facts and answered *kan inte verifieras* with the
clause quoted, which is different information from having found nothing. See
:mod:`app.integrations.terms`.

**What anchors it.** The supplier's name or organisation number, verified
verbatim in a document, with a recorded strength
(:mod:`app.integrations.supplier`). A weak anchor still produces a finding, and
that finding says the names differ and offers the alias for a human to confirm.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from ..citations import Rejected, Resolved, resolve_citation
from ..schemas import CitationOut, Chunk
from ..store import Store
from . import supplier as supplier_mod
from . import terms as terms_mod
from .models import (
    VERDICT_LABELS,
    AliasProposal,
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

# Terms that make a passage worth reading for a price. Used only to build the
# retrieval query — never to decide anything.
_CONTRACT_TERMS = (
    "avtal ersättning pris belopp månadsavgift arvode avtalsperiod "
    "giltighetstid uppsägning indexreglering"
)


# ---------------------------------------------------------------------------
# Reading values out of page words
# ---------------------------------------------------------------------------


_EDGE_PUNCT = " \t()[]{}.,;:!?\"'§•· "

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
    """Closed date ranges, kept for callers that only want the old shape.

    :func:`app.integrations.terms.scan_periods` is what the review uses now: it
    reads Swedish month names and open-ended agreements as well, and returns
    them as :class:`~app.integrations.terms.PeriodTerm`.
    """
    return [
        (p.span.start, p.span.end, p.start_iso, p.end_iso)
        for p in terms_mod.scan_periods(words)
        if p.end_iso is not None
    ]


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
    """Every document that arrived as an attachment in the integration queue."""
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


def unadopted_incoming_document_ids(store: Store) -> set[str]:
    """Queue attachments **nobody has put in the archive**, which are not evidence.

    This is the most important rule in this module, and the adoption step is
    what makes it liveable.

    An invoice PDF imported from a `.eml` becomes an ordinary document:
    indexed, retrievable, citable. Left in the candidate pool, the review then
    found "5 000 kronor" *in the invoice itself* and reported that the invoice
    agrees with the invoice — a verified citation, a confident verdict, and no
    information whatsoever. The first end-to-end run of this engine did exactly
    that.

    The rule that fixes it is not a filename check. It is that an incoming
    attachment is the material *being reviewed*, and the association's own
    archive is what carries authority to review it against. Until this block
    shipped adoption, that meant a contract received by mail could never become
    evidence at all — conservative, and a real gap: the board had the contract,
    the product could see it, and it refused to use it.

    Now a named administrator can adopt one — an explicit act, recorded with
    who and when and why (``Attachment.archived*``). An adopted attachment is a
    document of the association's, and behaves like any other. An unadopted one
    is still only material, and is excluded here.
    """
    excluded: set[str] = set()
    try:
        events = store.integrations.list_source_events()
    except Exception as exc:
        logger.error("Kunde inte läsa källhändelser för uteslutning: %s", exc)
        raise
    for event in events:
        for attachment in event.attachments:
            if attachment.document_id and not attachment.archived:
                excluded.add(attachment.document_id)
    return excluded


def evidence_excluded_document_ids(store: Store, invoice: InvoiceSnapshot) -> set[str]:
    """What may not be cited as evidence about *this* invoice.

    Two rules, and the second is not implied by the first: every unadopted
    queue attachment, **plus** every attachment of the source event this
    invoice came in on — adopted or not. Adopting the PDF of an invoice is a
    perfectly reasonable thing for a board to do; letting that invoice then
    corroborate itself is not.
    """
    excluded = unadopted_incoming_document_ids(store)
    if invoice.source_event_id:
        event = store.integrations.get_source_event(invoice.source_event_id)
        if event is not None:
            excluded |= {a.document_id for a in event.attachments if a.document_id}
    return excluded


def _candidates(store: Store, invoice: InvoiceSnapshot) -> list[tuple[_Candidate, float]]:
    """Chunks worth reading for this invoice, best first."""
    query = f"{invoice.supplier_name} {_CONTRACT_TERMS}".strip()
    settings = store.settings
    excluded = evidence_excluded_document_ids(store, invoice)
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
# The anchor
# ---------------------------------------------------------------------------


@dataclass
class Anchor:
    """The verified fact that a document is about this invoice's supplier."""

    citation: CitationOut
    document_id: str
    document_name: str
    strength: str
    matched_text: str
    confirmed_by: str = ""

    @property
    def weak(self) -> bool:
        return self.strength in supplier_mod.WEAK_STRENGTHS

    def note(self, invoice: InvoiceSnapshot) -> str:
        if self.strength == "org_number":
            return (
                f"Kopplingen är gjord på organisationsnummer ({self.matched_text}), "
                "som är entydigt."
            )
        if self.strength == "exact":
            return f"{self.document_name} namnger {invoice.supplier_name} ordagrant."
        if self.strength == "alias":
            who = f" ({self.confirmed_by})" if self.confirmed_by else ""
            return (
                f"{self.document_name} skriver \"{self.matched_text}\". En person här har "
                f"bekräftat att det är samma leverantör som {invoice.supplier_name}{who}."
            )
        if self.strength == "legal_form":
            return (
                f"{self.document_name} skriver \"{self.matched_text}\" — samma namn som på "
                "fakturan, med annan bolagsform."
            )
        return (
            f"{self.document_name} skriver \"{self.matched_text}\", fakturan säger "
            f"\"{invoice.supplier_name}\". Namnen är inte identiska; kopplingen bygger på "
            "att den särskiljande delen är densamma."
        )

    def proposal(self, invoice: InvoiceSnapshot) -> AliasProposal | None:
        if not self.weak:
            return None
        return AliasProposal(
            invoice_name=invoice.supplier_name,
            document_name=self.matched_text,
            document_id=self.document_id,
            basis=(
                f"Den särskiljande delen \"{self.matched_text}\" står ordagrant i "
                f"{self.document_name}."
            ),
        )


def _full_name_at(words: list[str], start: int, size: int) -> tuple[str, bool]:
    """The company name the document actually writes, and whether we matched all of it.

    A needle can match a *prefix* of a longer name: the invoice says
    "Snösvängen AB", its core is the single token "snösvängen", and that token
    appears inside "Snösvängen Entreprenad AB". Treating that as "same name,
    different legal form" would overstate it — the document names something
    longer, and only a person can say the two are one company.

    So the match is extended rightwards across further capitalised tokens and a
    trailing legal form, and the caller is told whether anything was added. The
    extended text is also what an alias proposal should carry: a human asked to
    confirm "Snösvängen AB = Snösvängen Entreprenad AB" is being asked the real
    question, where "Snösvängen AB = Snösvängen" is asking about a fragment.
    """
    end = start + size - 1
    extended = end
    while extended + 1 < len(words):
        # A name cannot continue past the end of its own sentence or clause.
        # "…Snösvängen Entreprenad AB. Entreprenören ska…" would otherwise
        # swallow the next sentence's first word, and a match that reached that
        # far would be judged a prefix of a longer name that does not exist.
        if words[extended].rstrip().endswith((".", ",", ";", ":", ")", "!", "?")):
            break
        nxt = _clean(words[extended + 1])
        if not nxt:
            break
        lowered = supplier_mod.tokens_of(nxt)
        if not lowered:
            break
        if lowered[0] in supplier_mod.LEGAL_FORM_TOKENS:
            extended += 1
            continue
        # A capitalised word directly after a company name is part of it.
        # Anything else — a verb, a comma, "org.nr" — ends the name.
        if nxt[:1].isupper() and nxt.isalpha():
            extended += 1
            continue
        break
    # Trailing legal-form tokens are part of the name but do not make the match
    # a prefix: "Snösvängen Entreprenad" against "Snösvängen Entreprenad AB" is
    # the same name.
    real_end = extended
    while real_end > end and supplier_mod.tokens_of(_clean(words[real_end]))[:1] and supplier_mod.tokens_of(
        _clean(words[real_end])
    )[0] in supplier_mod.LEGAL_FORM_TOKENS:
        real_end -= 1
    return " ".join(_clean(w) for w in words[start : extended + 1]).strip(), real_end > end


def _find_anchor(
    store: Store, invoice: InvoiceSnapshot, candidates: list[tuple[_Candidate, float]]
) -> Anchor | None:
    """The strongest verified mention of this supplier, or None.

    Strongest, not first: a document that carries the organisation number
    outranks one that carries a partially matching name, however the retrieval
    happened to order them. Ranking is not evidence — see
    :func:`review_invoice`.
    """
    aliases = [
        (a.document_name, a.created_by) for a in store.integrations.aliases_for(invoice.supplier_name)
    ]
    needles = supplier_mod.needles_for(
        invoice.supplier_name,
        org_number=invoice.supplier_ref or "",
        aliases=aliases,
    )
    if not needles:
        return None

    best: Anchor | None = None
    for candidate, score in candidates:
        words = candidate.slice()
        lowered = [supplier_mod.tokens_of(_clean(w)) for w in words]
        # One token per word after normalisation; a word that normalises to
        # nothing (a bullet, a rule) can never start a match.
        flat = [parts[0] if parts else "" for parts in lowered]
        for needle in needles:
            if best is not None and supplier_mod.strength_rank(
                needle.strength
            ) >= supplier_mod.strength_rank(best.strength):
                continue
            size = len(needle.tokens)
            for i in range(len(flat) - size + 1):
                if tuple(flat[i : i + size]) != needle.tokens:
                    continue
                written, is_prefix = _full_name_at(words, i, size)
                strength = needle.strength
                if is_prefix and strength in ("exact", "legal_form"):
                    # We matched part of a longer name. That is a candidate, not
                    # an identity — a person has to say so, which is what the
                    # weak strength and its alias proposal ask for.
                    strength = "partial"
                if best is not None and supplier_mod.strength_rank(
                    strength
                ) >= supplier_mod.strength_rank(best.strength):
                    continue
                quote = candidate.quote_for(i, i + size - 1)
                citation = _citation(store, candidate.chunk, quote, score)
                if citation is None:
                    continue
                best = Anchor(
                    citation=citation,
                    document_id=candidate.chunk.document_id,
                    document_name=citation.document_name,
                    strength=strength,
                    matched_text=written or " ".join(_clean(w) for w in words[i : i + size]),
                    confirmed_by=needle.confirmed_by,
                )
                break
            if best is not None and best.strength == supplier_mod.STRENGTH_ORDER[0]:
                return best
    return best


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
    anchor: Anchor | None = None,
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
        anchor_strength=anchor.strength if anchor else None,
        anchor_note=anchor.note(invoice) if anchor else None,
        alias_proposal=anchor.proposal(invoice) if anchor else None,
    ).with_label()


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} {currency}".replace(",", " ").replace(".", ",", 1)


def review_invoice(store: Store, invoice: InvoiceSnapshot) -> list[ReviewFinding]:
    """Compare one invoice against the tenant's own documents.

    The review is anchored on the supplier's identity. Unless some document
    names the supplier — verified verbatim, not merely ranked highly by
    retrieval — nothing in the archive is evidence about this invoice, and the
    only honest answer is *kan inte verifieras*.

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
    anchor = _find_anchor(store, invoice, candidates)

    if anchor is None:
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
                    "Ladda upp avtalet, arkivera det om det kommit per mejl, eller granska "
                    "fakturan mot underlag utanför appen."
                ),
                uncertainty=(
                    "Utan ett dokument som namnger leverantören finns ingenting att "
                    "jämföra mot. Belopp i andra avtal är inte jämförbara med den här "
                    "fakturan, hur nära de än ligger i siffror. Observera att en bilaga "
                    "som ligger kvar i granskningskön inte räknas som underlag — den är "
                    "det som granskas, inte det som granskas mot, förrän någon "
                    "uttryckligen arkiverar den."
                ),
            )
        ]

    # Only documents that identify the supplier may carry evidence about this
    # invoice. Everything else in the archive is about something else.
    anchored = [c for c in candidates if c[0].chunk.document_id == anchor.document_id]

    findings: list[ReviewFinding] = []

    amount_finding = _review_amount(store, invoice, anchored, anchor, currency)
    if amount_finding is not None:
        findings.append(amount_finding)

    if invoice.period_start and invoice.period_end:
        period_finding = _review_period(store, invoice, anchored, anchor)
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
                        value=anchor.matched_text,
                        source="document",
                        citation_index=0,
                    ),
                ],
                citations=[anchor.citation],
                suggestion=(
                    f"{anchor.document_name} namnger {invoice.supplier_name}, men "
                    "fakturan bär inget belopp och ingen period att jämföra."
                ),
                uncertainty=(
                    "Fakturan saknar de fält som den här granskningen kan jämföra."
                ),
                anchor=anchor,
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


def _index_clause(
    store: Store, candidates: list[tuple[_Candidate, float]]
) -> tuple[CitationOut, terms_mod.IndexTerm] | None:
    """A verified clause saying the price follows an index, if the contract has one."""
    for candidate, score in candidates:
        words = candidate.slice()
        for clause in terms_mod.scan_index_clauses(words):
            quote = candidate.quote_for(clause.span.start, clause.span.end)
            citation = _citation(store, candidate.chunk, quote, score)
            if citation is not None:
                return citation, clause
    return None


def _weak_anchor_caveat(anchor: Anchor, invoice: InvoiceSnapshot) -> str:
    if not anchor.weak:
        return ""
    return (
        f" Kopplingen mellan fakturans \"{invoice.supplier_name}\" och dokumentets "
        f"\"{anchor.matched_text}\" är inte bekräftad av någon här — bekräfta att det är "
        "samma leverantör innan fyndet används."
    )


def _review_amount(
    store: Store,
    invoice: InvoiceSnapshot,
    candidates: list[tuple[_Candidate, float]],
    anchor: Anchor,
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

    citations: list[CitationOut] = [anchor.citation]
    invoice_facts.append(
        VerifiedFact(
            label="Leverantören namnges i dokumentet",
            value=anchor.matched_text,
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
        index = _index_clause(store, candidates)
        index_note = ""
        if index is not None:
            # Equal amounts and an index clause is still a match — the printed
            # price and the invoice agree, which is exactly what an index that
            # has not yet been applied looks like. Worth saying, not worth
            # downgrading.
            citations.append(index[0])
            index_note = (
                f" Avtalet har ett {index[1].human()}; att beloppen är lika betyder att "
                "ingen uppräkning slagit igenom på den här fakturan."
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
                + index_note
            ),
            uncertainty=(
                "Jämförelsen gäller det citerade villkoret och ingenting annat. "
                "Antal timmar, mängder, indexuppräkning, tillägg och senare ändringar "
                "är inte kontrollerade." + _weak_anchor_caveat(anchor, invoice)
            ),
            anchor=anchor,
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
        index = _index_clause(store, candidates)
        if index is not None:
            # An index-regulated price makes a difference between the printed
            # amount and the invoice uninformative: the printed amount is a
            # base, not the current price. Reporting "möjlig avvikelse" here
            # would hand a reviewer a number to disprove rather than a fact to
            # act on. The honest verdict is that this cannot be verified, and
            # the useful part is *why*, with both clauses cited.
            citations.append(index[0])
            invoice_facts.append(
                VerifiedFact(
                    label="Prisvillkoret är indexreglerat",
                    value=index[1].human(),
                    source="document",
                    citation_index=len(citations) - 1,
                )
            )
            return _finding(
                invoice,
                "contract_term_not_comparable",
                "cannot_be_verified",
                facts=invoice_facts,
                citations=citations,
                suggestion=(
                    f"{label.capitalize()} är {_money(target_value, currency)} och det citerade "
                    f"villkoret i {citation.document_name} s. {citation.page} anger "
                    f"{_money(value, currency)}. Skillnaden går inte att tolka som en avvikelse: "
                    f"priset är {index[1].human()}. Räkna upp grundbeloppet enligt indexvillkoret "
                    "innan fakturan bedöms."
                ),
                uncertainty=(
                    "Det citerade beloppet är en grundnivå, inte det pris som gäller idag. "
                    "Vilket indextal som ska tillämpas, från vilken basmånad och för vilken "
                    "period framgår inte av den här jämförelsen."
                    + _weak_anchor_caveat(anchor, invoice)
                ),
                anchor=anchor,
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
                + _weak_anchor_caveat(anchor, invoice)
            ),
            anchor=anchor,
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
            (
                "Inga belopp kunde citeras ordagrant som jämförbara med fakturan."
                if not verified_any_amount
                else "Belopp gick att verifiera i dokumenten, men inget av dem avser samma "
                "sorts kvantitet som fakturan — ett à-pris kan inte jämföras med ett "
                "totalbelopp utan att antal och mängder är kända."
            )
            + _weak_anchor_caveat(anchor, invoice)
        ),
        anchor=anchor,
    )


def _uncomparable_period_terms(
    store: Store, candidates: list[tuple[_Candidate, float]]
) -> tuple[list[CitationOut], list[VerifiedFact], list[str]]:
    """Terms about time that were read and cited but cannot be compared.

    A duration counted from a signing date the product does not have, and a
    notice period. Both are real answers to "what does the agreement say about
    time", and both are invisible to a date comparison.
    """
    citations: list[CitationOut] = []
    facts: list[VerifiedFact] = []
    descriptions: list[str] = []
    for candidate, score in candidates:
        words = candidate.slice()
        found: list[tuple[terms_mod.Span, str, str]] = []
        for duration in terms_mod.scan_durations(words):
            found.append((duration.span, "Avtalstid i citerat villkor", duration.human()))
        for notice in terms_mod.scan_notice_periods(words):
            found.append((notice.span, "Uppsägningstid i citerat villkor", notice.human()))
        for span, label, human in found:
            quote = candidate.quote_for(span.start, span.end)
            citation = _citation(store, candidate.chunk, quote, score)
            if citation is None:
                continue
            citations.append(citation)
            facts.append(
                VerifiedFact(
                    label=label,
                    value=human,
                    source="document",
                    citation_index=len(citations) - 1,
                )
            )
            descriptions.append(f"{human} ({citation.document_name} s. {citation.page})")
            if len(citations) >= 2:
                return citations, facts, descriptions
    return citations, facts, descriptions


def _review_period(
    store: Store,
    invoice: InvoiceSnapshot,
    candidates: list[tuple[_Candidate, float]],
    anchor: Anchor,
) -> ReviewFinding | None:
    assert invoice.period_start and invoice.period_end

    facts = [
        VerifiedFact(
            label="Fakturaperiod",
            value=f"{invoice.period_start} – {invoice.period_end}",
            source="invoice",
        )
    ]
    citations: list[CitationOut] = [anchor.citation]

    for candidate, score in candidates:
        words = candidate.slice()
        for period in terms_mod.scan_periods(words):
            quote = candidate.quote_for(period.span.start, period.span.end)
            citation = _citation(store, candidate.chunk, quote, score)
            if citation is None:
                continue
            citations.append(citation)
            facts.append(
                VerifiedFact(
                    label="Avtalstid i citerat villkor",
                    value=period.human(),
                    source="document",
                    citation_index=len(citations) - 1,
                )
            )
            if period.covers(invoice.period_start, invoice.period_end):
                open_note = (
                    " Avtalet löper tills vidare, så slutdatum finns inte att jämföra mot — "
                    "kontrollera att det inte är uppsagt."
                    if period.open_ended
                    else ""
                )
                return _finding(
                    invoice,
                    "invoice_contract_period",
                    "matches",
                    facts=facts,
                    citations=citations,
                    suggestion=(
                        f"Fakturaperioden ligger inom den citerade avtalstiden "
                        f"{period.human()} i {citation.document_name} s. {citation.page}."
                        + open_note
                    ),
                    uncertainty=(
                        "Att perioden ryms i avtalstiden säger ingenting om att just "
                        "den här tjänsten är beställd för perioden."
                        + _weak_anchor_caveat(anchor, invoice)
                    ),
                    anchor=anchor,
                )
            return _finding(
                invoice,
                "invoice_contract_period",
                "possible_deviation",
                facts=facts,
                citations=citations,
                suggestion=(
                    f"Fakturaperioden {invoice.period_start} – {invoice.period_end} ligger "
                    f"helt eller delvis utanför den citerade avtalstiden {period.human()} "
                    f"i {citation.document_name} s. {citation.page}. Kontrollera om avtalet "
                    "är förlängt eller om fakturan avser något annat."
                ),
                uncertainty=(
                    "Perioden kan vara förlängd genom ett tillägg eller en automatisk "
                    "förlängningsklausul som inte finns i den citerade passagen."
                    + _weak_anchor_caveat(anchor, invoice)
                ),
                anchor=anchor,
            )

    # No dated period. Before answering "nothing found", look for the terms
    # that describe time without dates — they are usually the reason.
    term_citations, term_facts, descriptions = _uncomparable_period_terms(store, candidates)
    if term_citations:
        base = len(citations)
        citations.extend(term_citations)
        facts.extend(
            fact.model_copy(
                update={
                    "citation_index": base + (fact.citation_index or 0),
                }
            )
            for fact in term_facts
        )
        return _finding(
            invoice,
            "contract_term_not_comparable",
            "cannot_be_verified",
            facts=facts,
            citations=citations,
            suggestion=(
                "Avtalet anger sin tid utan datum: "
                + "; ".join(descriptions)
                + ". Fakturaperioden "
                f"{invoice.period_start} – {invoice.period_end} går därför inte att jämföra "
                "maskinellt. Stäm av mot undertecknandedatum eller senaste förlängning."
            ),
            uncertainty=(
                "En löptid räknad från undertecknande kräver undertecknandedatumet, och det "
                "finns inte i den citerade passagen. Villkoret är läst och citerat, men det "
                "besvarar inte om just den här perioden är avtalad."
                + _weak_anchor_caveat(anchor, invoice)
            ),
            anchor=anchor,
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
            "Ingen daterad period och inget läsbart tidsvillkor kunde citeras ordagrant."
            + _weak_anchor_caveat(anchor, invoice)
        ),
        anchor=anchor,
    )
