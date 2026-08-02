"""Fetching what is new, rather than showing the same mailbox again.

The first version of this screen listed the newest 25 messages every time it
was opened. After a fortnight that is a wall of material somebody has already
dealt with, with the two new things buried in it — and a queue whose top item
is usually stale is a queue people stop reading.

So a fetch asks a narrower question: *what has arrived since the last time we
looked?* The answer needs three things, and none of them is a sync loop:

1. **A checkpoint.** :class:`~app.integrations.models.MailboxCheckpoint` holds
   the timestamp of the newest message the last successful fetch saw. It lives
   in the tenant's own directory like everything else here.
2. **A narrower read.** ``receivedDateTime ge <checkpoint>`` goes to Graph, so
   the filtering happens where the messages are rather than after transferring
   them (:meth:`app.integrations.graph_mail.GraphMailAdapter.list_messages`).
3. **A second guard that does not depend on time.** Every candidate is checked
   against the queue's own ``external_ref`` values, and the importer still
   refuses a duplicate by content hash. Clocks are not a safe deduplicator —
   two messages share a second, a mailbox is migrated and every timestamp
   moves — so the checkpoint is an optimisation and the hash is the rule.

**What this deliberately does not do.** It does not run by itself: there is no
thread, no schedule and no webhook, and this function is only ever called from
a route a person triggered. It does not mark, move or delete anything in the
mailbox. And it does not half-import: a message the `.eml` format refuses
(most often a non-PDF attachment) is *skipped and reported*, not partially
stored — the queue says what it could not take in, and the message is still
sitting in the mailbox where it was.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..store import Store
from .eml import EmlRejected
from .intake import DuplicateSourceEvent, import_eml
from .models import MailboxCheckpoint, SkippedMessage, SourceEvent, utc_now_iso

logger = logging.getLogger("brf.integrations.mailbox")

# How many messages one fetch will take in. A ceiling rather than a page size:
# a first fetch against a mailbox with two years of history should produce a
# reviewable queue, not 800 rows and a very long request. The checkpoint
# advances to what was actually taken in, so pressing "hämta nytt" again
# continues from there.
FETCH_LIMIT = 25
MAX_SKIPPED_KEPT = 20


@dataclass
class FetchResult:
    """What one fetch did, in the terms the screen reports it in."""

    seen: int = 0
    imported: list[SourceEvent] = field(default_factory=list)
    already_known: int = 0
    skipped: list[SkippedMessage] = field(default_factory=list)
    checkpoint: MailboxCheckpoint | None = None

    def public(self) -> dict:
        return {
            "seen": self.seen,
            "new": len(self.imported),
            "alreadyKnown": self.already_known,
            "events": [e.model_dump(mode="json") for e in self.imported],
            "skipped": [s.model_dump(mode="json") for s in self.skipped],
            "checkpoint": self.checkpoint.public() if self.checkpoint else None,
        }


def known_external_refs(store: Store) -> set[str]:
    """Message identifiers already in this tenant's queue.

    Both the ``Message-ID`` and the mailbox's own id are recorded in
    ``external_ref`` depending on which header the message carried, so both
    forms are compared — a message whose ``Message-ID`` was missing at import
    is still recognised by the id Graph gave it.
    """
    refs: set[str] = set()
    for event in store.integrations.list_source_events():
        if event.external_ref:
            refs.add(event.external_ref)
    return refs


def fetch_new(
    *,
    store: Store,
    adapter,
    provider: str,
    folder: str,
    user_id: str,
    limit: int = FETCH_LIMIT,
    only_with_attachments: bool = False,
) -> FetchResult:
    """Take in what has arrived since the last successful fetch.

    ``only_with_attachments`` defaults to **False** here, unlike the browse
    listing it shares an adapter with. That default is the whole point of this
    block: the messages a board loses money to — an approval, an accepted
    quote, a stated notice period, an unanswered question — usually carry no
    attachment at all, and a queue that filters them out was answering "which
    files arrived" while claiming to answer "what arrived".

    The checkpoint only advances on success, and only to a message that was
    actually taken in or already known. A fetch that failed halfway leaves the
    checkpoint where it was, so the next one re-reads rather than skipping.
    """
    checkpoint = store.integrations.get_mailbox_checkpoint(provider, folder)
    messages = adapter.list_messages(
        limit=limit,
        only_with_attachments=only_with_attachments,
        since=checkpoint.high_water_mark,
    )

    result = FetchResult(seen=len(messages))
    known = known_external_refs(store)
    high_water = checkpoint.high_water_mark
    # The timestamp of the oldest message this fetch could not read at all. The
    # checkpoint is never advanced past it, because a message that failed
    # transiently — a timeout, a throttle, a byte range the mailbox would not
    # serve — has to be offered again. Without this clamp a later, newer
    # message would move the mark beyond it and the failure would become
    # permanent and silent, which is the worst shape a fetch bug can take.
    stalled_at = ""

    # Oldest first: a thread's first message should enter the queue before its
    # replies, so that grouping and the "senaste avsändare" on a card are right
    # the first time rather than after a re-read.
    for message in sorted(messages, key=lambda m: (m.received_at, m.id)):
        if message.internet_message_id and message.internet_message_id in known:
            result.already_known += 1
            high_water = max(high_water, message.received_at or "")
            continue
        if message.id in known:
            result.already_known += 1
            high_water = max(high_water, message.received_at or "")
            continue

        try:
            raw = adapter.get_message_mime(message.id)
        except Exception as exc:
            # One unreadable message must not abandon the rest of the fetch —
            # but it must not silently advance the checkpoint past itself
            # either, so the loop moves on without touching the high-water
            # mark and the next fetch will try it again.
            logger.warning("Kunde inte hämta %s ur brevlådan: %s", message.id, exc)
            result.skipped.append(
                SkippedMessage(
                    external_ref=message.internet_message_id or message.id,
                    subject=message.subject,
                    sender=message.from_address,
                    received_at=message.received_at,
                    code="unreadable",
                    reason=f"Meddelandet kunde inte hämtas: {exc.__class__.__name__}.",
                )
            )
            if not stalled_at:
                stalled_at = message.received_at or ""
            continue

        try:
            event = import_eml(
                store=store,
                integrations=store.integrations,
                raw=raw,
                filename=f"{message.id[:40]}.eml",
                imported_by=user_id,
                method="graph-mailbox-import",
                adapter_name=provider,
                external_hint=message.id,
            )
        except DuplicateSourceEvent:
            # The same bytes under a different id: a forward of something
            # already in the queue, or a mailbox that re-delivered. Counted,
            # not reported as a problem.
            result.already_known += 1
        except EmlRejected as exc:
            # Refused whole, by design (app.integrations.eml). Recorded so the
            # queue can say what it did not take in — silence here would let an
            # operator believe the queue is the mailbox.
            result.skipped.append(
                SkippedMessage(
                    external_ref=message.internet_message_id or message.id,
                    subject=message.subject,
                    sender=message.from_address,
                    received_at=message.received_at,
                    code=exc.code,
                    reason=exc.message,
                )
            )
        else:
            result.imported.append(event)
            known.add(event.external_ref or message.id)

        high_water = max(high_water, message.received_at or "")

    if stalled_at:
        high_water = min(high_water, stalled_at) if high_water else stalled_at

    result.checkpoint = store.integrations.put_mailbox_checkpoint(
        MailboxCheckpoint(
            provider=provider,
            folder=folder,
            high_water_mark=high_water,
            last_fetched_at=utc_now_iso(),
            last_fetch_by=user_id,
            last_new_count=len(result.imported),
            last_seen_count=result.seen,
            last_skipped=result.skipped[:MAX_SKIPPED_KEPT],
            last_error="",
        )
    )
    return result


def note_fetch_failure(
    *, store: Store, provider: str, folder: str, error: str
) -> MailboxCheckpoint:
    """Record that a fetch did not happen, without moving the checkpoint.

    Kept separate from the success path so there is exactly one place the
    high-water mark advances. A failure that quietly kept the old timestamp and
    a fresh ``last_fetched_at`` would make a fetch that never ran look like one
    that found nothing — which is the single most misleading thing this screen
    could say.
    """
    checkpoint = store.integrations.get_mailbox_checkpoint(provider, folder)
    return store.integrations.put_mailbox_checkpoint(
        checkpoint.model_copy(update={"last_error": error})
    )


__all__ = ["FETCH_LIMIT", "FetchResult", "fetch_new", "known_external_refs", "note_fetch_failure"]
