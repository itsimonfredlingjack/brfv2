"""HTTP surface for the website workspace.

Same ``tenant_store`` / ``require_admin`` dependencies as everything else, so
tenant isolation is inherited rather than re-argued: a membership resolves to
exactly one Store, and that Store is the only place this association's site
exists. Reading needs a membership; every write needs ``admin``, because the
association's public face is not something an individual member changes.

Two shapes of write, and only two:

- ``POST /commands`` — a batch of validated commands, applied as one
  transaction. This is what the editor sends when a person edits, and what the
  AI turn sends after planning. It is emphatically *not* a page object: the
  route never accepts content to store as-is.
- ``POST /pages/{id}/publish`` and its neighbours — the acts that change what
  the public sees. Deliberately outside the command vocabulary, so no model can
  reach them (see :data:`app.website.commands.AI_ALLOWED`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..store import Store
from .ai import EditorContext, plan
from .commands import (
    CommandContext,
    CommandRefused,
    apply_command,
    parse_commands,
)
from .components import vocabulary
from .grounding import support_quotes
from .models import (
    Block,
    PageRevision,
    Site,
    SiteSettings,
    SiteTransaction,
)
from .store import NothingToPublish, PageNotFound, RevisionNotFound, WebsiteStoreError

logger = logging.getLogger("brf.website.routes")

MAX_COMMANDS_PER_REQUEST = 40
HISTORY_PAGE_SIZE = 40


class CommandsRequest(BaseModel):
    """A batch of commands that together make one understandable change."""

    operations: list[dict]
    # What to call this in the history. The editor sends what it did ("Flyttade
    # Nyheter"); when it sends nothing, the engine's own per-command summaries
    # are joined instead, so a transaction is never nameless.
    summary: str = ""


class AiRequest(BaseModel):
    instruction: str
    page_id: str = ""
    block_id: str = ""
    field: str = ""
    selected_text: str = ""


class PublishRequest(BaseModel):
    note: str = ""


class RollbackRequest(BaseModel):
    revision_id: str
    note: str = ""


class InitializeRequest(BaseModel):
    title: str = "Startsida"


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    trusted_names_for: Callable[[str], tuple[str, ...]] = lambda _brf_id: (),
    today: Callable[[], date] = date.today,
) -> APIRouter:
    router = APIRouter()

    def _now() -> str:
        from ..integrations.models import utc_now_iso

        return utc_now_iso()

    def _context(store: Store, brf_id: str, *, actor: str, user: dict, instruction: str, transaction_id: str) -> CommandContext:
        return CommandContext(
            actor=actor,
            user_id=user["id"],
            now=_now(),
            transaction_id=transaction_id,
            instruction=instruction,
            trusted_names=tuple(trusted_names_for(brf_id)),
            # Bound to *this* Store, so a document id from another association
            # is simply not found — the 404-not-403 rule applied to a field.
            document_exists=lambda doc_id: doc_id in store.documents,
        )

    def _run(
        store: Store,
        brf_id: str,
        raw_operations: list[dict],
        *,
        actor: str,
        user: dict,
        summary: str,
        instruction: str = "",
        undoes: str = "",
    ) -> tuple[Site, SiteTransaction, list[dict]]:
        """Validate and apply a batch as one all-or-nothing transaction.

        Parsing happens before the lock is taken — a malformed command is a 422
        that never touches the site — and applying happens inside it, against
        the site as it is on disk at that moment.
        """
        if len(raw_operations) > MAX_COMMANDS_PER_REQUEST:
            raise HTTPException(
                status_code=422,
                detail=f"För många operationer i en ändring (högst {MAX_COMMANDS_PER_REQUEST}).",
            )
        if not raw_operations:
            raise HTTPException(status_code=422, detail="Inga operationer att utföra.")

        try:
            commands = parse_commands(raw_operations)
        except CommandRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        transaction_id = uuid.uuid4().hex[:12]
        ctx = _context(store, brf_id, actor=actor, user=user, instruction=instruction, transaction_id=transaction_id)
        reads: list[dict] = []

        def apply(site: Site) -> SiteTransaction:
            summaries: list[str] = []
            inverse: list[dict] = []
            pages: list[str] = []
            for command in commands:
                applied = apply_command(site, command, ctx)
                if applied.read is not None:
                    reads.append(applied.read)
                    continue
                summaries.append(applied.summary)
                # Reversed at the end: undoing three changes means undoing the
                # last one first, or an insert's inverse would run against a
                # list the next inverse has not yet restored.
                inverse = applied.inverse + inverse
                pages.extend(applied.page_ids)
            return SiteTransaction(
                id=transaction_id,
                at=ctx.now,
                by=user["id"],
                actor=actor,
                summary=(summary.strip() or "; ".join(summaries) or "Ändrade webbplatsen")[:200],
                commands=[c.model_dump(mode="json") for c in commands],
                inverse=inverse,
                prompt=instruction[:2000],
                undoes=undoes,
                page_ids=sorted(set(pages)),
            )

        try:
            site, transaction = store.website.mutate(apply)
        except CommandRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except WebsiteStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return site, transaction, reads

    # ---------- reads ----------

    def _workspace(store: Store, site: Site) -> dict:
        day = today().isoformat()
        undone = site.undone_map()
        return {
            "settings": site.settings.model_dump(mode="json"),
            "pages": [
                {
                    **page.public(day=day),
                    "needs_review": len(page.needs_review()),
                }
                for page in site.pages
            ],
            "navigation": site.navigation_public(),
            "history": [
                t.public(undone_by=undone.get(t.id, ""))
                for t in reversed(site.history[-HISTORY_PAGE_SIZE:])
            ],
            "counts": {
                "pages": len(site.pages),
                "published": len([p for p in site.pages if p.published]),
                "unpublished_changes": len(
                    [
                        page
                        for page in site.pages
                        if page.dirty_against(store.website.published_page(page))
                    ]
                ),
                # Blocks a model wrote that nobody has adopted. They hold up a
                # publication, so the number belongs where the operator looks.
                "needs_review": sum(len(page.needs_review()) for page in site.pages),
                "chrome_unpublished": site.chrome_dirty(),
            },
        }

    @router.get("/api/brf/{brf_id}/website")
    def workspace(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """The whole workspace in one read.

        One call rather than four for the same reason the invoice workspace is
        one call: a screen that renders in stages can briefly show a page whose
        badge disagrees with its buttons. This is a read and only a read — it
        does not create a starter site, because a read that writes is a bug this
        repo has already fixed once.
        """
        store, _ = access
        return _workspace(store, store.website.site())

    @router.get("/api/brf/{brf_id}/website/vocabulary")
    def get_vocabulary(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """What a page may contain. The editor builds its panels from this."""
        return vocabulary()

    @router.get("/api/brf/{brf_id}/website/pages/{page_id}")
    def get_page(page_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        store, _ = access
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")
        published = store.website.published_page(page)
        return {
            **page.public(day=today().isoformat()),
            "draft": {
                "title": page.draft.title,
                "content": [b.public() for b in page.draft.content],
                "based_on_revision_id": page.draft.based_on_revision_id,
            },
            "has_unpublished_changes": page.dirty_against(published),
            "needs_review": [b.id for b in page.needs_review()],
            "published_revision": published.public(with_content=True) if published else None,
        }

    @router.get("/api/brf/{brf_id}/website/pages/{page_id}/revisions")
    def list_revisions(page_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        store, _ = access
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")
        return {
            "page_id": page.id,
            "current": page.publication.revision_id if page.publication else "",
            "revisions": [r.public() for r in store.website.revisions_for(page_id)],
        }

    @router.get("/api/brf/{brf_id}/website/revisions/{revision_id}")
    def get_revision(revision_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        store, _ = access
        try:
            revision = store.website.revision(revision_id)
        except RevisionNotFound as exc:
            raise HTTPException(status_code=404, detail="Okänd version.") from exc
        # Cross-tenant safety by construction: the store is this tenant's, so a
        # revision id belonging to another association is simply not on this
        # disk — 404, never 403.
        if store.website.site().page(revision.page_id) is None:
            raise HTTPException(status_code=404, detail="Okänd version.")
        return revision.public(with_content=True)

    @router.get("/api/brf/{brf_id}/website/published")
    def published_site(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """The site as the public sees it: published revisions only.

        The same structured content the editor works on, rendered by the same
        component configuration — there is no second, generated representation
        of a page anywhere in this feature.
        """
        store, _ = access
        site = store.website.site()
        day = today().isoformat()
        pages: list[dict] = []
        for page in site.pages:
            revision = store.website.published_page(page)
            if revision is None or not page.publish_window.visible_on(day):
                continue
            pages.append(
                {
                    "page_id": page.id,
                    # The revision's address, not the draft's. Renaming a page in
                    # the editor must not move a published page under the feet of
                    # everyone who has its link.
                    "slug": revision.slug or page.slug,
                    "home": page.home,
                    "title": revision.title,
                    "revision_id": revision.id,
                    "seq": revision.seq,
                    "published_at": page.publication.published_at if page.publication else "",
                    "content": [b.public() for b in revision.content],
                }
            )
        visible = {p["page_id"] for p in pages}
        # Menu and settings likewise come from the published snapshot. Reading
        # them off the draft was the hole in the publication boundary: it let a
        # draft-side change — including one the AI partner made — reach a visitor
        # without anybody publishing anything.
        chrome = site.published_chrome
        return {
            "settings": (chrome.settings if chrome else SiteSettings()).model_dump(mode="json"),
            "navigation": [
                n
                for n in site.navigation_public(chrome.navigation if chrome else [])
                if n["page_id"] in visible
            ],
            "pages": pages,
            "published_at": chrome.published_at if chrome else "",
        }

    # ---------- writes ----------

    @router.post("/api/brf/{brf_id}/website/initialize")
    def initialize(
        req: InitializeRequest,
        brf_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Create the first page. A deliberate act, not something a read does."""
        site = store.website.site()
        if site.pages:
            raise HTTPException(status_code=409, detail="Webbplatsen är redan påbörjad.")
        operations: list[dict] = [
            {"command": "create_page", "title": req.title.strip() or "Startsida", "slug": "start", "home": True},
        ]
        # The site is named after the association rather than left saying
        # "Föreningens webbplats" — the name comes from the trusted tenant
        # record, never from the request, exactly as it does for the grounding
        # gate. It is an ordinary command, so it is validated and undoable like
        # anything else.
        name = next((n for n in trusted_names_for(brf_id) if n), "")
        if name:
            operations.append({"command": "update_settings", "field": "name", "value": name})
        site, transaction, _ = _run(
            store, brf_id, operations, actor="human", user=user, summary="Skapade webbplatsen"
        )
        page = site.pages[0]
        # The menu is written as its own command against the page that now
        # exists, rather than being assembled here: one path in, always.
        site, _, _ = _run(
            store,
            brf_id,
            [{"command": "update_navigation", "action": "add", "page_id": page.id}],
            actor="human",
            user=user,
            summary="La in startsidan i menyn",
        )
        return _workspace(store, site)

    @router.post("/api/brf/{brf_id}/website/commands")
    def run_commands(
        req: CommandsRequest,
        brf_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Apply one change, however many operations it took.

        This is the only route the editor writes through. A drag, an inline
        edit and a delete all arrive here as commands, so the human path and the
        AI path are validated by the same code with no way to tell them apart.
        """
        site, transaction, reads = _run(
            store, brf_id, req.operations, actor="human", user=user, summary=req.summary
        )
        return {
            "transaction": transaction.public(),
            "reads": reads,
            "workspace": _workspace(store, site),
        }

    @router.post("/api/brf/{brf_id}/website/ai")
    def ai_edit(
        req: AiRequest,
        brf_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """One instruction to the AI partner, applied straight into the draft.

        No pre-approval diff: the change lands in the draft and the board sees
        it in the canvas, which is the honest way round — a diff of structured
        operations is not something anyone can review, and the page is. Nothing
        is public until somebody publishes, and the whole turn is one
        transaction with an "ångra allt" behind it.
        """
        instruction = req.instruction.strip()
        if not instruction:
            raise HTTPException(status_code=422, detail="Skriv vad du vill ändra.")

        site = store.website.site()
        outcome = plan(
            store,
            site,
            instruction,
            ctx=EditorContext(
                page_id=req.page_id,
                block_id=req.block_id,
                field=req.field,
                selected_text=req.selected_text,
            ),
            trusted_names=trusted_names_for(brf_id),
        )
        if outcome.refusal:
            # A refusal is a normal outcome here, not an error: the product
            # refuses rather than fabricates, and the panel shows the sentence.
            return {
                "applied": False,
                "refusal": outcome.refusal,
                "message": outcome.message,
                "provider": outcome.provider,
                "model": outcome.model,
                "workspace": _workspace(store, site),
            }
        if not outcome.commands:
            return {
                "applied": False,
                "refusal": "",
                "message": outcome.message or "AI-assistenten föreslog ingen ändring.",
                "provider": outcome.provider,
                "model": outcome.model,
                "workspace": _workspace(store, site),
            }

        try:
            site, transaction, reads = _run(
                store,
                brf_id,
                [c.model_dump(mode="json") for c in outcome.commands],
                actor="ai",
                user=user,
                summary=outcome.summary,
                instruction=instruction,
            )
        except HTTPException as exc:
            # The engine refused the model's proposal — an unknown component, an
            # ungrounded number, a block that may only appear once. That is a
            # normal outcome of asking a model for something, not a failed
            # request: the operator gets the sentence in the panel and the draft
            # is exactly as they left it. Re-raising would show them a generic
            # error for a decision the product made on purpose.
            if exc.status_code not in (409, 422):
                raise
            return {
                "applied": False,
                "refusal": f"AI-assistentens ändring skrevs inte: {exc.detail}",
                "message": outcome.message,
                "provider": outcome.provider,
                "model": outcome.model,
                "workspace": _workspace(store, store.website.site()),
            }
        return {
            "applied": True,
            "refusal": "",
            "message": outcome.message,
            "provider": outcome.provider,
            "model": outcome.model,
            "sources": [c.model_dump(mode="json") for c in outcome.sources],
            "transaction": transaction.public(),
            "reads": reads,
            "workspace": _workspace(store, site),
        }

    @router.post("/api/brf/{brf_id}/website/transactions/{transaction_id}/undo")
    def undo(
        transaction_id: str,
        brf_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Take one change back — the AI's whole turn, or a manual edit.

        The undo is applied as commands through the same engine and recorded as
        its own transaction, carrying ``undoes``. Nothing is removed from the
        history and — the part that took a second look — nothing already written
        to it is edited either: "has this been undone?" is answered by finding
        the later transaction that says so, not by going back and stamping the
        old one. That is what makes the log append-only in fact rather than in
        name.
        """
        site = store.website.site()
        transaction = site.transaction(transaction_id)
        if transaction is None:
            raise HTTPException(status_code=404, detail="Okänd ändring.")
        if transaction_id in site.undone_map():
            raise HTTPException(status_code=409, detail="Ändringen är redan ångrad.")
        if not transaction.inverse:
            raise HTTPException(status_code=422, detail="Den här ändringen går inte att ångra.")

        site, undo_transaction, _ = _run(
            store,
            brf_id,
            transaction.inverse,
            actor="human",
            user=user,
            summary=f"Ångrade: {transaction.summary}"[:200],
            undoes=transaction_id,
        )
        return {
            "transaction": undo_transaction.public(),
            "workspace": _workspace(store, site),
        }

    @router.post("/api/brf/{brf_id}/website/pages/{page_id}/publish")
    def publish(
        page_id: str,
        req: PublishRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Cut the draft into an immutable revision and put it in front of the public.

        Everything that decides *what* gets published — is there anything new,
        which version number, which blocks — happens inside the store's lock,
        against the draft on disk. The route used to work all of that out from a
        copy it had read moments earlier, which meant an edit landing in between
        was published unseen and two simultaneous publications could both believe
        they were version 2.
        """
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")

        # The review gate. A model may write prose into the draft; nobody
        # outside the association reads it until a person has adopted it, by
        # editing it or by saying so. Checked before the lock for a clear
        # message, and again inside it because that is where it is true.
        unreviewed = page.needs_review()
        if unreviewed:
            names = ", ".join(sorted({b.props.get("heading") or b.type for b in unreviewed}))
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{len(unreviewed)} block är skrivna av AI:n utan källa och behöver "
                    f"bekräftas innan sidan publiceras: {names}. Läs texten och tryck "
                    "”Bekräfta texten”, eller skriv om den själv."
                ),
            )

        now = _now()
        note = req.note.strip()[:300]

        def make_revision(current, seq: int) -> PageRevision:
            if current.needs_review():  # re-checked under the lock
                raise NothingToPublish(
                    "Sidan innehåller AI-skriven text som ingen har bekräftat. "
                    "Bekräfta texten först."
                )
            return PageRevision(
                id=f"rev-{page_id}-{seq:04d}",
                page_id=page_id,
                seq=seq,
                title=current.draft.title,
                slug=current.slug,
                # A deep copy so the immutable record cannot be reached through
                # the draft that keeps being edited after this.
                content=[
                    Block.model_validate(b.model_dump(mode="json")) for b in current.draft.content
                ],
                created_at=now,
                created_by=user["id"],
                note=note,
            )

        def make_transaction(current, revision: PageRevision | None) -> SiteTransaction:
            return SiteTransaction(
                id=uuid.uuid4().hex[:12],
                at=now,
                by=user["id"],
                actor="human",
                summary=(
                    f"Publicerade {current.draft.title} (version {revision.seq})"
                    if revision is not None
                    # Nothing on the page changed, so no version was cut; what
                    # went live was the menu or the site's own settings.
                    else "Publicerade menyn och webbplatsens inställningar"
                ),
                page_ids=[page_id],
            )

        try:
            site, revision = store.website.publish_current(
                page_id,
                now=now,
                user_id=user["id"],
                note=note,
                make_revision=make_revision,
                make_transaction=make_transaction,
            )
        except PageNotFound as exc:
            raise HTTPException(status_code=404, detail="Okänd sida.") from exc
        except NothingToPublish as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WebsiteStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            # None when the page itself had nothing new and what went live was
            # the menu or the settings — no version is cut for that, because no
            # page content changed.
            "revision": revision.public() if revision is not None else None,
            "workspace": _workspace(store, site),
        }

    @router.post("/api/brf/{brf_id}/website/pages/{page_id}/rollback")
    def rollback(
        page_id: str,
        req: RollbackRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Publish an earlier revision again.

        Nothing is rewritten and nothing is deleted: the older revision is
        published a second time, and the history says so. The draft is left
        alone — going back to what the public saw is not the same decision as
        throwing away what somebody has since written.
        """
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")
        try:
            revision = store.website.revision(req.revision_id)
        except RevisionNotFound as exc:
            raise HTTPException(status_code=404, detail="Okänd version.") from exc
        if revision.page_id != page_id:
            raise HTTPException(status_code=404, detail="Okänd version.")
        if page.publication and page.publication.revision_id == revision.id:
            raise HTTPException(status_code=409, detail="Den versionen är redan publicerad.")

        now = _now()
        transaction = SiteTransaction(
            id=uuid.uuid4().hex[:12],
            at=now,
            by=user["id"],
            actor="human",
            summary=f"Återställde {page.draft.title} till version {revision.seq}",
            page_ids=[page_id],
        )
        site, revision = store.website.republish(
            page_id,
            revision=revision,
            published_at=now,
            published_by=user["id"],
            note=req.note.strip()[:300],
            transaction=transaction,
        )
        return {"revision": revision.public(), "workspace": _workspace(store, site)}

    @router.post("/api/brf/{brf_id}/website/pages/{page_id}/unpublish")
    def unpublish(
        page_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")
        transaction = SiteTransaction(
            id=uuid.uuid4().hex[:12],
            at=_now(),
            by=user["id"],
            actor="human",
            summary=f"Avpublicerade {page.draft.title}",
            page_ids=[page_id],
        )
        try:
            site = store.website.unpublish(page_id, transaction=transaction)
        except WebsiteStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"workspace": _workspace(store, site)}

    @router.get("/api/brf/{brf_id}/website/blocks/{page_id}/{block_id}/sources")
    def block_sources(
        page_id: str, block_id: str, access: tuple[Store, str] = Depends(tenant_store)
    ) -> dict:
        """The evidence behind one block's text, for the panel that shows it.

        The same citations the answer pipeline verified, so "varför står det så
        här?" opens the association's own PDF at the page it came from.
        """
        store, _ = access
        site = store.website.site()
        page = site.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Okänd sida.")
        block = next((b for b in page.draft.content if b.id == block_id), None)
        if block is None:
            raise HTTPException(status_code=404, detail="Okänt block.")
        return {
            "block_id": block.id,
            "grounding": block.grounding,
            "citations": [c.model_dump(mode="json") for c in block.sources],
            "quotes": support_quotes(block.sources),
        }

    return router


__all__ = [
    "AiRequest",
    "CommandsRequest",
    "InitializeRequest",
    "PublishRequest",
    "RollbackRequest",
    "build_router",
]
