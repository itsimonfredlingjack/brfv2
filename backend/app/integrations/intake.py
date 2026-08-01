"""Import one `.eml` into a tenant's review queue — all of it, or none of it.

The failure this module exists to prevent is the half-import: a source event
that exists while one of its attachments does not, or two documents ingested
before the third was refused. Either leaves a queue entry that lies about what
arrived.

So the order is fixed, and it is the only interesting thing here:

1. **Validate everything first.** :func:`app.integrations.eml.parse_eml` reads
   the whole message and refuses on the first violation, before any store is
   touched. Nothing has been written when it raises.
2. **Check for a duplicate** by content hash, and stop if there is one. The
   caller is told which event it already is.
3. **Ingest the attachments**, keeping every ``doc_id`` that lands.
4. **On any failure in step 3, delete every document already added** and raise.
   ``Store.delete_document`` is the same call the product's own delete route
   uses, so the rollback leaves the tenant exactly as ingestion found it.
5. Only then write the ``SourceEvent``.

The event is the last thing written, deliberately: if the process dies at any
point before that, the tenant has at worst some orphaned documents it can see
and delete, never a queue entry pointing at documents that are not there.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from ..store import Store
from .eml import EmlFileAdapter, EmlRejected, NormalizedMessage, parse_eml
from .models import Attachment, Provenance, SourceEvent, utc_now_iso
from .store import IntegrationStore

logger = logging.getLogger("brf.integrations.intake")

# Relevance floor for a *suggestion*, deliberately below Settings.minRelevance.
#
# That setting is the refusal gate for generated answers: below it the product
# says it does not know, because an ungrounded answer is worse than none. A
# queue suggestion is a different act — it is a proposal a human confirms or
# rejects before it becomes a link, and the answer gate is simply the wrong
# threshold for it. Set too high, an operator is shown nothing and has to search
# the archive by hand; the correct failure mode here is an occasional
# unhelpful proposal, not silence.
SUGGESTION_MIN_CONFIDENCE = 0.08
SUGGESTION_LIMIT = 3


class DuplicateSourceEvent(ValueError):
    """These exact bytes are already in this tenant's queue."""

    def __init__(self, existing: SourceEvent) -> None:
        super().__init__(
            f"Meddelandet är redan importerat ({existing.received_at}) som {existing.id}."
        )
        self.existing = existing


def suggest_documents(
    store: Store,
    message: NormalizedMessage,
    *,
    exclude: set[str] | None = None,
    limit: int = SUGGESTION_LIMIT,
) -> list[str]:
    """Documents in the association's archive that this message may be about.

    A *suggestion*, and stored in a field named as one. The query is the
    subject plus the sender's domain — an invoice mail from
    ``faktura@snosvangen.example`` about "Snöröjning januari" should surface the
    snow-clearing contract, and the retrieval stack the product already has is
    better at that than any keyword rule written here would be.

    Attachments that arrived through this queue are excluded, including the
    message's own. Offering an operator "this invoice may be related to: this
    invoice" is not a suggestion, and it was the first thing the retrieval
    returned when the exclusion was missing — the freshly ingested attachment
    is by far the best lexical match for its own subject line.

    Returns document ids, not hits: the queue shows which documents to look at,
    and anything stronger would be presenting a guess as a finding.
    """
    domain = message.sender.rsplit("@", 1)[-1].replace(".", " ") if "@" in message.sender else ""
    query = " ".join(part for part in (message.subject, domain) if part).strip()
    if not query:
        return []
    skip = set(exclude or ())
    try:
        from .review import incoming_document_ids

        skip |= incoming_document_ids(store)
    except Exception as exc:  # a queue read must never be able to fail an import
        logger.warning("Kunde inte läsa köns bilagor för uteslutning: %s", exc)
    settings = store.settings
    try:
        hits = store.index.search(
            query,
            weight=settings.searchWeighting / 100.0,
            candidates=settings.candidateCount,
            # Over-fetch: exclusions are applied after ranking.
            top_k=limit * 6,
            min_confidence=min(settings.minRelevance, SUGGESTION_MIN_CONFIDENCE),
        )
    except Exception as exc:  # retrieval must never be able to fail an import
        logger.warning("Kunde inte föreslå dokument för importen: %s", exc)
        return []
    seen: list[str] = []
    for hit in hits:
        if hit.document_id in skip or hit.document_id in seen:
            continue
        seen.append(hit.document_id)
        if len(seen) >= limit:
            break
    return seen


def import_eml(
    *,
    store: Store,
    integrations: IntegrationStore,
    raw: bytes,
    filename: str,
    imported_by: str,
) -> SourceEvent:
    """Import one `.eml`. Raises :class:`~app.integrations.eml.EmlRejected` or
    :class:`DuplicateSourceEvent`; on success nothing is left half-done."""

    adapter = EmlFileAdapter()

    # 1. Everything is validated before anything is written.
    message = parse_eml(raw, filename=filename)

    # 2. The same bytes twice is not two events.
    content_sha256 = hashlib.sha256(raw).hexdigest()
    existing = integrations.find_source_event_by_hash(content_sha256)
    if existing is not None:
        raise DuplicateSourceEvent(existing)

    # An attachment that already arrived — same bytes, possibly a different
    # envelope — is linked to the document it produced rather than ingested
    # again. Two copies of one contract in the archive is not a record of two
    # arrivals; it is two things competing in retrieval for the same citation.
    known_by_hash: dict[str, str] = {}
    for earlier in integrations.list_source_events():
        for att in earlier.attachments:
            if att.document_id and att.document_id in store.documents:
                known_by_hash.setdefault(att.sha256, att.document_id)

    # 3. Ingest attachments, remembering what landed so 4 can undo it.
    ingested: list[Attachment] = []
    added_document_ids: list[str] = []
    try:
        for parsed in message.attachments:
            existing_doc = known_by_hash.get(parsed.sha256)
            if existing_doc is not None:
                document_id, reused = existing_doc, True
            else:
                meta = store.add_document(parsed.filename, parsed.data)
                added_document_ids.append(meta.id)
                known_by_hash[parsed.sha256] = meta.id
                document_id, reused = meta.id, False
            ingested.append(
                Attachment(
                    id=uuid.uuid4().hex[:12],
                    filename=parsed.filename,
                    media_type=parsed.media_type,
                    bytes=len(parsed.data),
                    sha256=parsed.sha256,
                    document_id=document_id,
                    ingested=True,
                    reused_existing_document=reused,
                )
            )
    except Exception as exc:
        # 4. Roll back through the product's own delete path.
        for doc_id in added_document_ids:
            try:
                store.delete_document(doc_id)
            except Exception:  # pragma: no cover - best effort, already failing
                logger.error("Kunde inte rulla tillbaka dokument %s efter misslyckad import", doc_id)
        if isinstance(exc, ValueError):
            # Store.add_document refuses page-count limits, missing text layers
            # and unreadable PDFs as ValueError with a Swedish message. That is
            # a rejection of this import, not an internal error.
            raise EmlRejected("attachment_rejected", f"Bilagan kunde inte läsas in: {exc}") from exc
        raise

    # 5. The event is the last thing written.
    event = SourceEvent(
        id=uuid.uuid4().hex[:12],
        tenant_id=integrations.tenant_id,
        source_type="email",
        received_at=utc_now_iso(),
        occurred_at=message.sent_at,
        external_ref=message.message_id,
        content_sha256=content_sha256,
        provenance=Provenance(
            method="manual-file-import",
            adapter=adapter.name,
            origin_filename=filename,
            origin_bytes=len(raw),
            imported_by=imported_by,
        ),
        origin=message.sender,
        origin_display=message.sender_display,
        recipients=message.recipients,
        subject=message.subject,
        body_text=message.body_text,
        attachments=ingested,
        import_status="imported",
        review_status="open",
        suggested_document_ids=suggest_documents(
            store, message, exclude=set(added_document_ids)
        ),
    )
    try:
        return integrations.add_source_event(event)
    except Exception:
        for doc_id in added_document_ids:
            try:
                store.delete_document(doc_id)
            except Exception:  # pragma: no cover
                logger.error("Kunde inte rulla tillbaka dokument %s efter misslyckad import", doc_id)
        raise
