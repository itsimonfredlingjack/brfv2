"""Keeping the message itself — as an ordinary document, not a special case.

The attachment is not the point. A board's most expensive incoming mail often
carries no file at all:

    "Vi godkänner offerten på 148 000 kr, sätt igång vecka 12."
    "Uppsägning måste ske senast tre månader före avtalstidens utgång."
    "Ni har tio dagar på er att svara på föreläggandet."

A product that only preserves PDFs loses every one of those, and then cannot
answer "did anyone approve the quote" six months later. So a reviewed message
can be preserved — and the interesting decision is *how*.

**It becomes a PDF, and goes through the ordinary ingestion path.** Not a new
"email" record type with its own search, its own viewer and its own idea of a
citation. :meth:`app.store.Store.add_document` extracts it, chunks it, indexes
it; :mod:`app.citations` verifies quotes against its page words and paints
rects on them; :mod:`app.answer` retrieves it beside the association's
contracts and refuses when it is not relevant. The message opens at the page,
with the sentence highlighted, exactly like an annual report does.

That is worth the cost of rendering a PDF, and the cost is the honest part: a
second evidence path would have meant a second citation resolver, a second
verbatim rule and a second place a quote could be "verified" by machinery
nobody had adversarially tested. There is one, and this uses it.

**Preservation is a human act, and the record says so.** Nothing is preserved
at import. The header block rendered onto page one carries the provenance the
queue holds — sender, recipients, both timestamps, Message-ID, the content hash
of the original MIME — so the document is self-describing once it is in the
archive and somebody opens it two years later without the queue in front of
them.

**A preserved message is evidence.** Unlike an attachment, it does not need a
separate adoption step: a named administrator preserved it, with a stated
reason, which *is* the adoption bar
(:func:`app.integrations.intake.adopt_attachment`). What it must still not do is
corroborate an invoice that arrived in the same message — see
:func:`app.integrations.review.evidence_excluded_document_ids`.
"""

from __future__ import annotations

import logging

from ..schemas import CitationOut
from ..store import Store
from .models import SourceEvent, utc_now_iso
from .store import IntegrationStore

logger = logging.getLogger("brf.integrations.preserve")

# A4 at 72 dpi, the same page geometry the rest of the corpus uses.
PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0
MARGIN = 56.0
BODY_SIZE = 10.5
HEAD_SIZE = 9.5
TITLE_SIZE = 14.0
LEADING = 1.45

# Helvetica: a PyMuPDF built-in with no font file to ship, and Latin-1
# coverage — which is every character Swedish needs. A message carrying
# characters outside it (an emoji, Greek) renders those as a placeholder
# rather than failing the preservation; the text that matters is intact and
# the alternative is refusing to keep a decision over a smiley.
FONT = "helv"

MAX_PAGES = 40


class PreservationError(ValueError):
    """This message cannot be preserved as a document, and the message says why."""


def _wrap(text: str, font, size: float, width: float) -> list[str]:
    """Break one paragraph into lines that fit, measuring the real font.

    Measured rather than estimated at N characters per line: the extracted word
    boxes are what citation rects are built from, so a line that overflowed the
    text area would put a highlight off the page and fail
    ``bbox_out_of_bounds`` — a silent, confusing failure much later.
    """
    import fitz

    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if fitz.get_text_length(candidate, fontname=font, fontsize=size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        # A single word longer than the line (a URL, a long reference) is cut
        # rather than allowed to overflow.
        while fitz.get_text_length(word, fontname=font, fontsize=size) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and fitz.get_text_length(word[:cut], fontname=font, fontsize=size) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def render_pdf(event: SourceEvent) -> bytes:
    """The message as a PDF: a provenance header, then the text as it was stored.

    The body is rendered verbatim from ``SourceEvent.body_text`` — the same
    string the queue displayed and the triage read — so a quote shown on a card
    is findable in the document that preserves it.
    """
    import fitz

    document = fitz.open()
    text_width = PAGE_WIDTH - 2 * MARGIN

    header = [
        ("Från", event.origin_display and f"{event.origin_display} <{event.origin}>" or event.origin),
        ("Till", ", ".join(event.recipients) or "—"),
        ("Avsänt", event.occurred_at or "okänt"),
        ("Mottaget av föreningen", event.received_at),
        ("Meddelande-id", event.external_ref or "—"),
        ("Innehållshash (SHA-256)", event.content_sha256),
        ("Källa", f"{event.provenance.method} / {event.provenance.adapter}"),
        ("Importerat av", event.provenance.imported_by),
    ]

    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN

    def _new_page():
        nonlocal page, y
        if document.page_count >= MAX_PAGES:
            raise PreservationError(
                f"Meddelandet blir längre än {MAX_PAGES} sidor och bevaras inte som dokument. "
                "Korta ned det eller bevara bilagan i stället."
            )
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = MARGIN

    def _write(line: str, size: float, gap: float = 0.0) -> None:
        nonlocal y
        if y + size * LEADING > PAGE_HEIGHT - MARGIN:
            _new_page()
        page.insert_text((MARGIN, y + size), line, fontname=FONT, fontsize=size)
        y += size * LEADING + gap

    for line in _wrap(event.subject or "(utan ämne)", FONT, TITLE_SIZE, text_width):
        _write(line, TITLE_SIZE)
    _write("Bevarad e-post — inkommande post till föreningen", HEAD_SIZE, gap=6)

    for label, value in header:
        for i, line in enumerate(_wrap(f"{label}: {value}", FONT, HEAD_SIZE, text_width)):
            _write(line if i == 0 else f"    {line}", HEAD_SIZE)

    if event.attachments:
        _write("", HEAD_SIZE)
        _write("Bilagor som följde med meddelandet:", HEAD_SIZE)
        for attachment in event.attachments:
            for line in _wrap(
                f"– {attachment.filename} ({attachment.bytes} byte, sha256 {attachment.sha256[:16]}…)"
                + (" — i föreningens arkiv" if attachment.archived else " — material under granskning"),
                FONT,
                HEAD_SIZE,
                text_width,
            ):
                _write(line, HEAD_SIZE)

    _write("", BODY_SIZE)
    _write("Meddelandets text", HEAD_SIZE, gap=4)

    body = event.body_text or ""
    if not body.strip():
        _write("(meddelandet innehöll ingen läsbar text)", BODY_SIZE)
    for paragraph in body.split("\n"):
        for line in _wrap(paragraph, FONT, BODY_SIZE, text_width):
            _write(line, BODY_SIZE)

    data = document.tobytes()
    document.close()
    return data


def document_name(event: SourceEvent) -> str:
    """What the preserved message is called in the document list.

    Dated and prefixed so it sorts with its neighbours and is recognisable as
    correspondence rather than as one more contract.
    """
    when = (event.occurred_at or event.received_at or "")[:10]
    subject = (event.subject or "utan ämne").strip()
    for bad in '/\\:*?"<>|':
        subject = subject.replace(bad, "-")
    return f"E-post {when} — {subject[:80]}.pdf"


def preserve_message(
    *,
    store: Store,
    integrations: IntegrationStore,
    event_id: str,
    user_id: str,
    note: str,
) -> SourceEvent:
    """Keep this message's text as a document of the association's.

    Idempotent: a message already preserved returns unchanged rather than
    ingesting a second copy, because two copies of one email would compete in
    retrieval for the same citation — the same defect deduplication exists to
    prevent for attachments.

    That idempotency is only worth something if the check and the write cannot
    be separated, so the tenant's integration lock is held across all of it: the
    "have we already?" question, rendering the PDF, ingesting it, and recording
    which document it became. Outside a lock, two requests both answered "no" —
    and the association got the same email in its archive twice, competing for
    the citation the second one would win half the time.

    ``integrations.lock`` before ``Store.lock``, as everywhere: ``add_document``
    is called from inside it.
    """
    reason = (note or "").strip()
    if not reason:
        raise PreservationError(
            "Ange varför meddelandet ska bevaras. Ett dokument som blir en del av "
            "föreningens underlag utan att någon säger varför är inte ett arkiv."
        )
    with integrations.lock:
        event = integrations.get_source_event(event_id)
        if event is None:
            raise PreservationError("Okänd källhändelse.")
        if event.preserved_document_id and event.preserved_document_id in store.documents:
            return event
        if not (event.body_text or "").strip():
            raise PreservationError(
                "Meddelandet har ingen text att bevara. Lägg bilagan i arkivet i stället."
            )

        meta = store.add_document(document_name(event), render_pdf(event))
        try:
            return integrations.mutate_source_event(
                event_id,
                lambda current: current.model_copy(
                    update={
                        "preserved_document_id": meta.id,
                        "preserved_by": user_id,
                        "preserved_at": utc_now_iso(),
                        "preservation_note": reason,
                    }
                ),
            )
        except Exception:
            # Same discipline as the import path: the document is rolled back
            # through the product's own delete route, so a failed preservation
            # leaves no orphan in the archive.
            try:
                store.delete_document(meta.id)
            except Exception:  # pragma: no cover - best effort, already failing
                logger.error(
                    "Kunde inte rulla tillbaka dokument %s efter misslyckad bevaring", meta.id
                )
            raise


def citation_for(store: Store, document_id: str, quote: str) -> CitationOut | None:
    """A verified citation into a preserved message, or nothing.

    The point of preserving a message is that what was read out of it can be
    *opened*. A triage signal carries a quote; once the message is a document,
    that quote goes through :func:`app.citations.resolve_citation` — the same
    verbatim check, the same rects, the same all-or-nothing rule as an answer's
    citation — and becomes something a watch or a task can carry.

    Returns ``None`` when the quote does not verify. That is not an error and
    is not worked around: a citation that cannot be resolved is not shown,
    which is the rule everywhere else in this product.
    """
    from ..citations import Rejected, resolve_citation

    meta = store.documents.get(document_id)
    if meta is None:
        return None
    _, chunks, pages, _ = store.snapshot()
    candidates = [c for c in chunks.values() if c.document_id == document_id]
    candidates.sort(key=lambda c: (c.page, c.word_start))
    for chunk in candidates:
        resolved = resolve_citation(chunk, [quote], {document_id: pages.get(document_id, [])})
        if isinstance(resolved, Rejected):
            continue
        return CitationOut(
            document_id=document_id,
            document_name=meta.name,
            page=resolved.page,
            quote=quote,
            quotes=[quote],
            chunk_id=chunk.id,
            rects=resolved.rects,
            score=1.0,
            approximate=meta.source == "scanned",
            corpus_origin=meta.corpus_origin,
        )
    return None


__all__ = [
    "MAX_PAGES",
    "PreservationError",
    "citation_for",
    "document_name",
    "preserve_message",
    "render_pdf",
]
