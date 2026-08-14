"""Import one `.eml` into a tenant's review queue — all of it, or none of it.

The failure this module exists to prevent is the half-import: a source event
that exists while one of its attachments does not, or two documents ingested
before the third was refused. Either leaves a queue entry that lies about what
arrived.

So the order is fixed, and it is the only interesting thing here:

1. **Validate everything first.** :func:`app.integrations.eml.parse_eml` reads
   the whole message and refuses on the first violation, before any store is
   touched — and before the lock is taken, because parsing is pure and holding
   a tenant's integration lock through it would serialise imports for no reason.
2. **Take the tenant's integration lock**, and hold it for everything below.
3. **Check for a duplicate** by content hash, and stop if there is one. The
   caller is told which event it already is.
4. **Ingest the attachments**, keeping every ``doc_id`` that lands.
5. **On any failure in step 4, delete every document already added** and raise.
   ``Store.delete_document`` is the same call the product's own delete route
   uses, so the rollback leaves the tenant exactly as ingestion found it.
6. Only then write the ``SourceEvent``.

The event is the last thing written, deliberately: if the process dies at any
point before that, the tenant has at worst some orphaned documents it can see
and delete, never a queue entry pointing at documents that are not there.

**Why steps 2 and 3 are not the same step.** They used to be neither: the hash
check ran outside any lock, and the append inside one. Eight concurrent imports
of the exact same MIME message each read "no duplicate" before any of them had
written, and the queue ended up with seven or eight copies — each with its own
random id, its own re-ingested attachments, and nothing to say which was the
message and which were the ghosts. A lock around only the append cannot fix
that, because by the time the append runs the decision to append has already
been made on stale information.

Two things fix it together. The lock now spans the decision *and* the write, so
the second importer reads the first importer's event. And the event's **id is
derived** from ``(tenant_id, content_sha256)`` rather than minted
(:func:`source_event_id_for`) — so even where a lock cannot reach, two importers
of one message compute one id and the store's own uniqueness check catches the
second. Identity is the idempotency key, the same rule
:mod:`app.invoices.cases` states for invoice cases.

**Lock ordering.** ``integrations.lock`` is taken before ``Store.lock``, never
after — ``store.add_document`` is called from inside it here. Every other module
that holds both holds them in that order; see :meth:`app.store.Store._domain_store`.
"""

from __future__ import annotations

import hashlib
import logging

from ..store import Store
from .eml import EmlFileAdapter, EmlRejected, NormalizedMessage, parse_eml
from .models import Attachment, Provenance, SourceEvent, utc_now_iso
from .store import DuplicateContent, IntegrationStore, SourceEventNotFound
from .threads import thread_key_for

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


def source_event_id_for(tenant_id: str, content_sha256: str) -> str:
    """A queue item's identity, derived from the message rather than minted.

    The same message is the same queue item, whether it arrives twice through
    the mailbox, once by file and once by fetch, or eight times at once from a
    client that retried. Deriving the id says that in the data model instead of
    hoping a check-then-append gets there first.

    The tenant is in the digest for the reason it is in
    :func:`app.invoices.cases.case_id_for`: the stores are already separate, and
    an id that could collide across them would be a trap for future code that
    looked one up without its tenant.
    """
    digest = hashlib.sha256(f"{tenant_id}\x00{content_sha256}".encode("utf-8")).hexdigest()
    return digest[:12]


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
        from .review import unadopted_incoming_document_ids

        # Unadopted only: a contract somebody deliberately put in the archive
        # is a document of the association's and is exactly what a later
        # invoice mail should be suggested against.
        skip |= unadopted_incoming_document_ids(store)
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


class AdoptionError(ValueError):
    """An attachment cannot be adopted into the archive, and the message says why."""


def adopt_attachment(
    *,
    store: Store,
    integrations: IntegrationStore,
    event_id: str,
    attachment_id: str,
    user_id: str,
    note: str,
) -> SourceEvent:
    """Make a queued attachment part of the association's own archive.

    This is the answer to the question the first version of this block left
    open: *how does a contract that arrived by mail become something the review
    may cite?* The conservative default — never — was right about the danger
    and wrong about the situation. The danger is that an invoice corroborates
    itself, which is what happens when incoming material is evidence by
    default. The situation is that boards receive contracts by mail, and a
    product that can see the contract and refuses to use it is not being
    careful, it is being useless.

    So adoption is an act, not a setting:

    * a **named administrator** does it, and their id is recorded;
    * they must say **why** — a sentence, required, because a document entering
      the evidence base on nobody's stated authority is how an archive stops
      meaning anything;
    * it is **per attachment**, not per message: a mail carrying a contract and
      an invoice adopts the contract and leaves the invoice where it is;
    * the document itself does not move or change. It was already ingested and
      citable; what changes is that it is no longer excluded from being
      evidence (:func:`app.integrations.review.unadopted_incoming_document_ids`).

    An invoice's own attachments stay excluded for that invoice's review even
    after adoption — see
    :func:`app.integrations.review.evidence_excluded_document_ids`.
    """
    reason = (note or "").strip()
    if not reason:
        raise AdoptionError(
            "Ange varför bilagan ska räknas som föreningens underlag. Ett dokument som "
            "blir bevis utan att någon säger varför är inte ett arkiv."
        )

    def apply(event: SourceEvent) -> SourceEvent:
        """Adopt, decided against the event as it stands under the lock.

        Adopting used to read the event, build a whole replacement and write it
        back, so an adoption landing between another request's read and write
        threw that request's change away — including, in the resolution path, a
        preservation recorded a moment earlier.
        """
        attachments = list(event.attachments)
        for i, attachment in enumerate(attachments):
            if attachment.id != attachment_id:
                continue
            if not attachment.document_id or attachment.document_id not in store.documents:
                raise AdoptionError(
                    "Bilagan finns inte som dokument längre och kan inte arkiveras."
                )
            if attachment.archived:
                # Already ours. Idempotent by design: pressing the button twice
                # is not two adoptions, and a retry after a timeout must not
                # overwrite the reason and the name already recorded.
                return event
            attachments[i] = attachment.model_copy(
                update={
                    "archived": True,
                    "archived_by": user_id,
                    "archived_at": utc_now_iso(),
                    "archive_note": reason,
                }
            )
            return event.model_copy(update={"attachments": attachments})
        raise AdoptionError("Okänd bilaga.")

    try:
        return integrations.mutate_source_event(event_id, apply)
    except SourceEventNotFound as exc:
        raise AdoptionError("Okänd källhändelse.") from exc


def withdraw_attachment(
    *,
    integrations: IntegrationStore,
    event_id: str,
    attachment_id: str,
) -> SourceEvent:
    """Undo an adoption. The document stays; it stops counting as evidence.

    Reversible on purpose. An irreversible decision is one people avoid making,
    and the point of adoption is that it should be easy to do correctly.
    """

    def apply(event: SourceEvent) -> SourceEvent:
        attachments = list(event.attachments)
        for i, attachment in enumerate(attachments):
            if attachment.id == attachment_id:
                attachments[i] = attachment.model_copy(
                    update={
                        "archived": False,
                        "archived_by": None,
                        "archived_at": None,
                        "archive_note": None,
                    }
                )
                return event.model_copy(update={"attachments": attachments})
        raise AdoptionError("Okänd bilaga.")

    try:
        return integrations.mutate_source_event(event_id, apply)
    except SourceEventNotFound as exc:
        raise AdoptionError("Okänd källhändelse.") from exc


def import_eml(
    *,
    store: Store,
    integrations: IntegrationStore,
    raw: bytes,
    filename: str,
    imported_by: str,
    method: str = "manual-file-import",
    adapter_name: str | None = None,
    external_hint: str = "",
    received_at: str | None = None,
) -> SourceEvent:
    """Import one message's raw MIME. All of it, or none of it.

    A message read from Microsoft Graph is the same bytes as a message exported
    to a file — Graph's ``/$value`` returns the MIME as it stands — so the
    parsing, the format ceiling, the attachment rule, the content hash, the
    duplicate check and the rollback are all the same code. What genuinely
    differs is recorded here: which method brought it in, which adapter read
    it, and — when Graph said — when the mailbox received it.

    ``received_at`` is Graph's ``receivedDateTime``. It is not in the MIME
    (the ``Date:`` header is the sender's stamp, stored as ``occurred_at``)
    and a forwarded message's nested headers are not a substitute. Manual
    file import leaves it empty and is stamped with the import time.

    Raises :class:`~app.integrations.eml.EmlRejected` or
    :class:`DuplicateSourceEvent`; on success nothing is left half-done.
    """

    adapter = adapter_name or EmlFileAdapter().name

    # 1. Everything is validated before anything is written, and before the
    #    lock: parsing is pure, and holding a tenant's lock through it would
    #    serialise imports for no benefit at all.
    message = parse_eml(raw, filename=filename)
    content_sha256 = hashlib.sha256(raw).hexdigest()

    # 2. One lock across deciding *and* writing. Everything below is the
    #    read-validate-modify-write this module's whole contract rests on, and
    #    splitting it was what let eight importers of one message each conclude
    #    it was new.
    with integrations.lock:
        # 3. The same bytes twice is not two events.
        existing = integrations.find_source_event_by_hash(content_sha256)
        if existing is not None:
            raise DuplicateSourceEvent(existing)

        # An attachment that already arrived — same bytes, possibly a different
        # envelope — is linked to the document it produced rather than ingested
        # again. Two copies of one contract in the archive is not a record of
        # two arrivals; it is two things competing in retrieval for the same
        # citation.
        known_by_hash: dict[str, str] = {}
        for earlier in integrations.list_source_events():
            for att in earlier.attachments:
                if att.document_id and att.document_id in store.documents:
                    known_by_hash.setdefault(att.sha256, att.document_id)

        # 4. Ingest attachments, remembering what landed so 5 can undo it.
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
                        # Derived from the message and the attachment's own
                        # bytes, so a re-import that somehow got this far
                        # produces the same attachment ids rather than a second
                        # set nothing points at.
                        id=hashlib.sha256(
                            f"{content_sha256}\x00{parsed.sha256}\x00{parsed.filename}".encode(
                                "utf-8"
                            )
                        ).hexdigest()[:12],
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
            # 5. Roll back through the product's own delete path.
            _rollback(store, added_document_ids)
            if isinstance(exc, ValueError):
                # Store.add_document refuses page-count limits, missing text
                # layers and unreadable PDFs as ValueError with a Swedish
                # message. That is a rejection of this import, not an internal
                # error.
                raise EmlRejected(
                    "attachment_rejected", f"Bilagan kunde inte läsas in: {exc}"
                ) from exc
            raise

        # 6. The event is the last thing written.
        event = SourceEvent(
            id=source_event_id_for(integrations.tenant_id, content_sha256),
            tenant_id=integrations.tenant_id,
            source_type="email",
            received_at=received_at or utc_now_iso(),
            occurred_at=message.sent_at,
            external_ref=message.message_id or external_hint or None,
            in_reply_to=message.in_reply_to,
            references=list(message.references),
            content_sha256=content_sha256,
            provenance=Provenance(
                method=method,
                adapter=adapter,
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

        # Which conversation this belongs to, decided once, against the queue as
        # it stands. Computed here rather than on every read so that a card
        # cannot regroup itself under a reader — see app.integrations.threads.
        thread_key, thread_subject = thread_key_for(event, integrations.list_source_events())
        event = event.model_copy(
            update={"thread_key": thread_key, "thread_subject": thread_subject}
        )

        # What this appears to be. A suggestion, computed at import so that the
        # queue is useful the moment it is opened rather than after somebody
        # presses "analysera" on every row — and never allowed to fail the
        # import, because a reading of a message is worth strictly less than the
        # message.
        try:
            from .triage import analyze

            event = event.model_copy(update={"triage": analyze(store, event)})
        except Exception as exc:  # pragma: no cover - analyze() is defensive itself
            logger.warning("Kunde inte analysera %s vid import: %s", event.id, exc)

        try:
            return integrations.add_source_event(event)
        except DuplicateContent as exc:
            # The store's own last-line check, which sees what this function saw
            # under the same lock. Reaching it means the two disagreed, which
            # should be impossible — but the answer is still "you already have
            # it", not a traceback, and the documents this attempt added must go.
            _rollback(store, added_document_ids)
            raise DuplicateSourceEvent(exc.existing) from exc
        except Exception:
            _rollback(store, added_document_ids)
            raise


def _rollback(store: Store, document_ids: list[str]) -> None:
    """Undo the documents one failed import added, through the product's own
    delete path — so the tenant is left exactly as ingestion found it."""
    for doc_id in document_ids:
        try:
            store.delete_document(doc_id)
        except Exception:  # pragma: no cover - best effort, already failing
            logger.error(
                "Kunde inte rulla tillbaka dokument %s efter misslyckad import", doc_id
            )
