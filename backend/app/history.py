"""The one rule every human-written history in this product shares.

A task's activity, an invoice case's timeline and a source event's decision
history are all append-only: an entry, once written, is never edited and never
removed. Three stores enforced that independently, and all three enforced it
with the same insufficient test — *is the new history at least as long as the
old one?*

Length is not enough, and the gap is exactly the one concurrency finds. Eight
people commenting on the same task at the same moment each read a history of
four entries, each appended one, and each wrote back a history of five. Every
write passed the length check, and the last one to land was the only comment
that survived. The other seven were not rejected; they were overwritten by
something that looked like a legitimate append.

What actually characterises an append is that **the old history is still there,
in order, at the front**. That is what :func:`check_append_only` tests, by
identity rather than by equality: every event in these domains carries an id, so
a prefix check is cheap, exact, and cannot be satisfied by a concurrent writer's
different-but-equally-long list.

The check is a backstop, not the mechanism. The mechanism is that mutations
read and write under one lock (``mutate_task``, ``mutate_source_event``,
``app.invoices.cases.mutate``), so a stale history never reaches a store in the
first place. This is what catches the next caller that forgets.
"""

from __future__ import annotations

from typing import Iterable, Protocol


class _Identified(Protocol):
    id: str


class AppendOnlyViolation(ValueError):
    """A history was written in a way that is not an append."""


def check_append_only(
    existing: Iterable[_Identified],
    proposed: Iterable[_Identified],
    *,
    what: str,
) -> None:
    """Refuse anything that is not "the old entries, then some new ones".

    ``what`` names the record in the operator-facing Swedish message, because
    the person who has to act on this failure is reading a log, not this file.
    """
    old = list(existing)
    new = list(proposed)
    if len(new) < len(old):
        raise AppendOnlyViolation(
            f"{what} skulle skrivas med kortare historik än den redan har "
            f"({len(new)} poster mot {len(old)}). Historiken är append-only."
        )
    for i, previous in enumerate(old):
        if new[i].id != previous.id:
            raise AppendOnlyViolation(
                f"{what} skulle skrivas med en historik som inte innehåller den "
                f"befintliga: post {i + 1} är {new[i].id!r} där {previous.id!r} står "
                "på disk. Historiken är append-only och skrivs aldrig över."
            )


__all__ = ["AppendOnlyViolation", "check_append_only"]
