"""Per-tenant persistence for the website. Same shape and isolation as everything else.

The association's site lives in its own directory inside its own tenant
directory, like its tasks and its watches: ``registry.delete()`` sweeps it with
the rest, and there is no shared collection anywhere that a missing ``WHERE``
could leak across — see :mod:`app.integrations.store` for the argument,
unchanged here.

**Two kinds of file, because there are two kinds of data.**

``site.json`` is rewritten on every edit: pages, drafts, the menu, the settings
and the append-only transaction log. ``revisions/<id>.json`` is written once and
never again — a published revision is immutable, and putting immutable content
in the document that gets rewritten on every keystroke would mean re-serialising
the site's entire published history each time somebody fixes a typo.

The ordering when publishing is deliberate: the revision file is written
**first**, and only then does ``site.json`` start pointing at it. A crash
between the two leaves an orphan revision file that nothing references, which is
harmless and detectable. The other order would leave a page whose publication
points at content that does not exist, which is neither.

**Writes are commands.** :meth:`WebsiteStore.mutate` holds the lock across the
whole read-modify-write and hands the caller a site read from disk *inside* it,
so a caller that read the site a second ago cannot write back a version that has
since been edited. Same shape as :meth:`app.tasks.store.TaskStore.mutate_task`
and :func:`app.invoices.cases.mutate`, deliberately.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Callable, Iterable

from pydantic import ValidationError

from ..history import AppendOnlyViolation, check_append_only
from .models import (
    SCHEMA_VERSION,
    PageRevision,
    Publication,
    Site,
    SiteChrome,
    SitePage,
    SiteTransaction,
)

logger = logging.getLogger("brf.website")

META_FILE = "meta.json"
SITE_FILE = "site.json"
REVISIONS_DIR = "revisions"


class WebsiteStoreError(RuntimeError):
    """Refusing to operate on this tenant's website data."""


class PageNotFound(WebsiteStoreError):
    """No page with that id in this tenant's site.

    Its own type so a route can answer 404 for "there is no such page" without
    also answering 404 for "that write would have destroyed history" — two
    different failures that must not be reported to the operator as one.
    """


class RevisionNotFound(WebsiteStoreError):
    """No such revision for this tenant."""


class NothingToPublish(WebsiteStoreError):
    """The draft says nothing the published revision does not.

    Its own type because the route answers it with a 409 and a sentence the
    operator can act on, rather than with the 500 a bare store error would
    become.
    """


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class WebsiteStore:
    """One association's website."""

    def __init__(self, data_dir: str | Path, tenant_id: str) -> None:
        if not tenant_id:
            raise WebsiteStoreError("WebsiteStore kräver ett tenant-id.")
        self.tenant_id = tenant_id
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover
            logger.debug("Kunde inte sätta 0700 på %s", self.dir)
        self.lock = threading.RLock()
        self._check_schema()

    def _check_schema(self) -> None:
        path = self.dir / META_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        except (OSError, json.JSONDecodeError) as exc:
            raise WebsiteStoreError(
                f"{path} går inte att läsa ({exc}) — vägrar öppna webbplatsdata för "
                f"'{self.tenant_id}'."
            ) from exc
        version = raw.get("schemaVersion") if isinstance(raw, dict) else None
        if version == SCHEMA_VERSION:
            return
        if isinstance(version, int) and version < SCHEMA_VERSION:  # pragma: no cover
            # Migration lives here, in the product, and not inside the editor
            # library's own state — which is why the schema version is ours.
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        raise WebsiteStoreError(
            f"Webbplatsdata för '{self.tenant_id}' har schemaVersion {version!r}; den här "
            f"versionen förstår {SCHEMA_VERSION}. En nyare datakatalog får inte öppnas av "
            "en äldre installation — då skrivs fält bort."
        )

    # ---------- io ----------

    def _read(self) -> Site:
        path = self.dir / SITE_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Site(tenant_id=self.tenant_id)
        except (OSError, json.JSONDecodeError) as exc:
            raise WebsiteStoreError(f"{path} går inte att läsa: {exc}") from exc
        try:
            site = Site.model_validate(raw)
        except ValidationError as exc:
            raise WebsiteStoreError(f"Ogiltigt innehåll i {path}: {exc}") from exc
        if site.tenant_id != self.tenant_id:
            raise WebsiteStoreError(
                f"{path} innehåller en webbplats för tenant {site.tenant_id!r} i "
                f"{self.tenant_id!r}s katalog."
            )
        return site

    def _write(self, site: Site) -> None:
        _atomic_write_json(self.dir / SITE_FILE, site.model_dump(mode="json"))

    def _revision_path(self, revision_id: str) -> Path:
        # Revision ids are minted here and never taken from a request, but the
        # check is cheap and keeps a future caller from turning one into a path.
        if not revision_id or "/" in revision_id or "." in revision_id:
            raise RevisionNotFound(f"Ogiltigt versions-id: {revision_id!r}")
        return self.dir / REVISIONS_DIR / f"{revision_id}.json"

    # ---------- reads ----------

    def site(self) -> Site:
        with self.lock:
            return self._read()

    def revision(self, revision_id: str) -> PageRevision:
        path = self._revision_path(revision_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RevisionNotFound(f"Okänd version: {revision_id}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise WebsiteStoreError(f"{path} går inte att läsa: {exc}") from exc
        try:
            return PageRevision.model_validate(raw)
        except ValidationError as exc:
            raise WebsiteStoreError(f"Ogiltig version i {path}: {exc}") from exc

    def revisions_for(self, page_id: str) -> list[PageRevision]:
        """Every recorded version of one page, newest first.

        Reads the directory rather than an index kept in ``site.json``: the
        files *are* the record, and an index beside them would be a second
        source of truth to keep in step.
        """
        directory = self.dir / REVISIONS_DIR
        if not directory.exists():
            return []
        rows: list[PageRevision] = []
        for path in directory.glob("*.json"):
            try:
                revision = PageRevision.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                logger.warning("Hoppar över oläsbar version %s: %s", path, exc)
                continue
            if revision.page_id == page_id:
                rows.append(revision)
        return sorted(rows, key=lambda r: r.seq, reverse=True)

    def _published_revision(self, page: SitePage) -> PageRevision | None:
        """The published revision, or None. Safe to call with the lock held."""
        if page.publication is None:
            return None
        try:
            return self.revision(page.publication.revision_id)
        except (RevisionNotFound, WebsiteStoreError) as exc:
            logger.warning(
                "Sidan %s pekar på version %s som inte går att läsa: %s",
                page.id, page.publication.revision_id, exc,
            )
            return None

    def published_page(self, page: SitePage) -> PageRevision | None:
        if page.publication is None:
            return None
        try:
            return self.revision(page.publication.revision_id)
        except (RevisionNotFound, WebsiteStoreError) as exc:
            # The orphan case from the other direction: a publication pointing
            # at a file that is gone. Reported as "not published" rather than as
            # a crash, because the draft is intact and the board can republish.
            logger.warning(
                "Sidan %s pekar på version %s som inte går att läsa: %s",
                page.id,
                page.publication.revision_id,
                exc,
            )
            return None

    # ---------- writes ----------

    def mutate(self, apply: Callable[[Site], SiteTransaction]) -> tuple[Site, SiteTransaction]:
        """Change the site, safely against every other request.

        ``apply`` receives the site as it is on disk *inside* the lock, mutates
        it, and returns the transaction that describes what it did. The
        transaction is appended to the history here rather than by the caller,
        so there is no way to write a change without writing the record of it.

        Anything ``apply`` raises propagates with nothing written — the site it
        was mutating is a fresh object that is simply discarded, which is what
        makes a multi-command transaction all-or-nothing.
        """
        with self.lock:
            site = self._read()
            # A *value* snapshot, not a list of the same objects. The shallow
            # copy this replaced shared its entries with the list being checked,
            # so an entry that was edited in place compared equal to itself and
            # the check passed — which is exactly how a record already on disk
            # came to be rewritten under a heading that says append-only.
            before = [t.model_dump(mode="json") for t in site.history]
            transaction = apply(site)
            site.history = [*site.history, transaction]
            try:
                check_append_only(
                    [SiteTransaction.model_validate(t) for t in before],
                    site.history[:-1],
                    what="Webbplatsens historik",
                )
            except AppendOnlyViolation as exc:  # pragma: no cover - defensive
                raise WebsiteStoreError(str(exc)) from exc
            # And the ids matching is not enough: every stored entry must still
            # say what it said. This is the check that would have caught it.
            if [t.model_dump(mode="json") for t in site.history[: len(before)]] != before:
                raise WebsiteStoreError(
                    "En redan skriven post i webbplatsens historik ändrades. Historiken "
                    "är append-only: en ändring skrivs som en ny post, aldrig över en gammal."
                )
            self._write(site)
            return site, transaction

    def _snapshot_chrome(self, site: Site, *, at: str, by: str) -> None:
        """Make the menu and the settings the public sees match the canvas.

        Called by every publication. Pressing publicera means "make what I am
        looking at live", and the menu is part of what the operator is looking
        at — while *not* snapshotting it was how a model rearranging the draft
        menu changed a visitor's navigation with nobody publishing anything.
        """
        site.published_chrome = SiteChrome(
            navigation=[n.model_copy(deep=True) for n in site.navigation],
            settings=site.settings.model_copy(deep=True),
            published_at=at,
            published_by=by,
        )

    def publish_current(
        self,
        page_id: str,
        *,
        now: str,
        user_id: str,
        note: str,
        make_revision: Callable[[SitePage, int], PageRevision],
        make_transaction: Callable[[SitePage, PageRevision | None], SiteTransaction],
    ) -> tuple[Site, PageRevision | None]:
        """Cut the current draft into a revision and publish it — all under one lock.

        The route used to read the site, decide there was something to publish,
        work out the next version number, build the revision from *that* copy of
        the draft, and only then call in here. Everything between the first read
        and this lock was a window: an edit that landed in it was published
        without anyone having seen it, and two operators pressing publicera at
        the same moment both computed version 2 and both believed they had it.
        Reading the draft here, inside the lock, is what closes that.

        The revision file is written before the pointer that references it, so a
        crash between the two leaves an unreferenced file rather than a
        publication pointing at content that does not exist.
        """
        with self.lock:
            site = self._read()
            page = site.page(page_id)
            if page is None:
                raise PageNotFound(f"Okänd sida: {page_id}")

            current = self._published_revision(page)
            page_dirty = page.dirty_against(current)
            # The menu and the site settings are published too, and can be the
            # *only* thing that changed — somebody renames the association, or
            # reorders the menu, and touches no page. Refusing that as "inget
            # nytt att publicera" would leave a draft change with no way to ever
            # reach the public.
            chrome_dirty = site.chrome_dirty()
            if not page_dirty and not chrome_dirty:
                raise NothingToPublish(
                    "Sidan är redan publicerad i det här skicket. Det finns inget nytt "
                    "att publicera."
                )

            revision: PageRevision | None = None
            if page_dirty:
                seq = max(
                    max((r.seq for r in self.revisions_for(page_id)), default=0),
                    page.revision_seq,
                ) + 1
                revision = make_revision(page, seq)

                path = self._revision_path(revision.id)
                if path.exists():  # pragma: no cover - the lock makes this unreachable
                    raise WebsiteStoreError(
                        f"Version {revision.id} finns redan och versioner skrivs aldrig om."
                    )
                _atomic_write_json(path, revision.model_dump(mode="json"))

                page.revision_seq = max(page.revision_seq, revision.seq)
                page.publication = Publication(
                    revision_id=revision.id,
                    seq=revision.seq,
                    published_at=now,
                    published_by=user_id,
                    rollback=False,
                    note=note,
                )
                page.draft.based_on_revision_id = revision.id

            self._snapshot_chrome(site, at=now, by=user_id)
            site.history = [*site.history, make_transaction(page, revision)]
            self._write(site)
            return site, revision

    def republish(
        self,
        page_id: str,
        *,
        revision: PageRevision,
        published_at: str,
        published_by: str,
        note: str = "",
        transaction: SiteTransaction,
    ) -> tuple[Site, PageRevision]:
        """Put an existing revision in front of the public a second time.

        A rollback writes no new revision file: what is being published already
        exists and is deliberately unchanged. The chrome is snapshotted like any
        other publication, because this is equally a human saying "make this
        live".
        """
        with self.lock:
            site = self._read()
            page = site.page(page_id)
            if page is None:
                raise PageNotFound(f"Okänd sida: {page_id}")
            page.publication = Publication(
                revision_id=revision.id,
                seq=revision.seq,
                published_at=published_at,
                published_by=published_by,
                rollback=True,
                note=note,
            )
            page.draft.based_on_revision_id = revision.id
            self._snapshot_chrome(site, at=published_at, by=published_by)
            site.history = [*site.history, transaction]
            self._write(site)
            return site, revision

    def unpublish(
        self, page_id: str, *, transaction: SiteTransaction
    ) -> Site:
        """Take a page off the public site without touching a single revision.

        The revisions stay exactly where they are — what was published remains
        readable, because "we took it down" and "it never existed" are different
        statements and only one of them is true.
        """
        with self.lock:
            site = self._read()
            page = site.page(page_id)
            if page is None:
                raise PageNotFound(f"Okänd sida: {page_id}")
            if page.publication is None:
                raise WebsiteStoreError("Sidan är inte publicerad.")
            page.publication = None
            site.history = [*site.history, transaction]
            self._write(site)
            return site

    def next_seq(self, page_id: str) -> int:
        with self.lock:
            site = self._read()
            page = site.page(page_id)
            existing = max((r.seq for r in self.revisions_for(page_id)), default=0)
            return max(existing, page.revision_seq if page else 0) + 1

    def prune_orphan_revisions(self, *, keep: Iterable[str] = ()) -> list[str]:
        """Remove revision files no page's history refers to. Never called on a
        request path — kept for the operator runbook, and safe because a
        revision that no publication and no page id references is unreachable."""
        keep_set = set(keep)
        with self.lock:
            page_ids = {p.id for p in self._read().pages}
            directory = self.dir / REVISIONS_DIR
            removed: list[str] = []
            for path in directory.glob("*.json") if directory.exists() else []:
                if path.stem in keep_set:
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if raw.get("page_id") not in page_ids:
                    path.unlink(missing_ok=True)
                    removed.append(path.stem)
            return removed


__all__ = [
    "META_FILE",
    "NothingToPublish",
    "PageNotFound",
    "REVISIONS_DIR",
    "RevisionNotFound",
    "SITE_FILE",
    "WebsiteStore",
    "WebsiteStoreError",
]
