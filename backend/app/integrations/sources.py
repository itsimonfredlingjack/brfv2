"""Resolving a named invoice source, and turning its failures into 4xx.

Extracted so the two routers that read invoices — the integrations router and
the invoice workspace's — cannot drift about what ``fortnox`` means or about
which failures are the other system's rather than this request's. Two places
deciding that would eventually be two places disagreeing, and the disagreement
would show up as a demo reading live data or a live installation reading the
fixture set.

Nothing here opens a socket. It hands back an adapter that can, and every one
of those has read verbs only (:mod:`app.integrations.protocols`).
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import HTTPException

from ..store import Store
from .connections import ConnectionManager, NotConnected
from .egress import EgressRefused, RemoteError
from .oauth import OAuthError

logger = logging.getLogger("brf.integrations.sources")

# Where an invoice may be read from. "fixture" is the synthetic dataset the
# block shipped with and keeps working with no credential at all; "fortnox" is
# a live, connected company. Named in the request rather than inferred from
# what happens to be connected, so a demo and a live read cannot be confused
# for one another in a screenshot.
INVOICE_SOURCES: tuple[str, ...] = ("fixture", "fortnox")


def live_runner(store: Store, provider: str, manager: ConnectionManager) -> Callable:
    """Run a live call, turning every failure into an operator-readable 4xx.

    Everything that can go wrong here is about the *other* system or the
    connection to it, and none of it is a bug in this request — so none of it
    should read as a 500. The connection also records what happened, so the UI
    can show "återkallad" instead of an error that looks transient.
    """

    def run(fn):
        try:
            return fn()
        except NotConnected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OAuthError as exc:
            raise HTTPException(status_code=409, detail=exc.message) from exc
        except EgressRefused as exc:
            # A refused URL is a bug in *this* product, and it is louder than a
            # 4xx would suggest — so it is logged with its code and returned as
            # a plain refusal rather than dressed up.
            logger.error("Utgående anrop vägrades (%s): %s", exc.code, exc.message)
            raise HTTPException(status_code=502, detail=exc.message) from exc
        except RemoteError as exc:
            manager.note_failure(provider, exc)
            raise HTTPException(status_code=502, detail=f"{provider}: {exc.detail}") from exc

    return run


def accounting_source(store: Store, source: str, *, fixture, manager: ConnectionManager):
    """Resolve a named source to something with the read adapter's shape.

    Two sources, never guessed between. ``fixture`` reads synthetic files and
    needs nothing; ``fortnox`` reads a live, connected company. An installation
    with Fortnox connected can still read the fixture set — which is what keeps
    the demo and the tests honest on a machine where a real integration exists.
    """
    if source not in INVOICE_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Okänd fakturakälla. Tillåtna: {', '.join(INVOICE_SOURCES)}.",
        )
    if source == "fixture":
        return fixture
    return manager.fortnox_adapter()


__all__ = ["INVOICE_SOURCES", "accounting_source", "live_runner"]
