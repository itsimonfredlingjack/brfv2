"""The association's public website, as this product's own domain model.

The editor library has a data shape of its own (``{content: [{type, props}]}``)
and it is deliberately *not* what is stored here. A page in this product is a
``SitePage``: an identity that outlives any editor, a **draft** somebody is
working in, a chain of **immutable revisions**, and a **publication** that says
which revision the public sees. Puck's shape is derived from that on the way to
the canvas and folded back on the way in — so the day the editor changes, or is
replaced, what the association wrote survives the change.

Four things follow from that, and they are the reason for the split:

1. **Editing is not publishing.** Everything a person or the AI does lands in
   the draft. Nothing reaches the public site until somebody presses publicera,
   and that act is recorded with a name and a time.
2. **A revision is immutable.** Publishing copies the draft into a numbered
   revision that is never written again. Rollback does not restore or rewrite
   anything; it publishes an *existing* revision a second time, so the history
   still reads as what actually happened.
3. **Blocks carry their sources.** A block whose text the AI derived from the
   association's own documents keeps the citations it was derived from — the
   same :class:`~app.schemas.CitationOut` the answer pipeline produces, opening
   the same PDF at the same page. A page can therefore be audited long after
   the chat that produced it is gone.
4. **History is append-only, and it is made of commands.** Every change is a
   :class:`SiteTransaction` holding the commands that produced it and the
   commands that would undo it. Manual edits and AI edits are the same records
   in the same list, which is what makes one undo button correct for both.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CitationOut

# Bumped when the stored shape changes in a way an older installation would
# misread. Owned here, in the product — never inferred from the editor library's
# own versioning, which moves for reasons that have nothing to do with this data.
SCHEMA_VERSION = 2

# Who made a change. Not a formality: the AI partner's work is applied straight
# into the draft so the board sees it immediately, which is only defensible if
# every screen can say which sentences a model wrote.
Actor = Literal["human", "ai"]

ACTOR_LABELS: dict[str, str] = {"human": "Redigerat för hand", "ai": "AI-ändring"}

# How a block's text came to be, and therefore what may be believed about it.
#
# - "authored"   a person wrote it, or took it over by editing it. The product
#                makes no claim about it; the association does.
# - "grounded"   a model wrote it from the association's own documents, and the
#                citations that supported it are attached below.
# - "editorial"  a model wrote it and it *cannot* carry a factual claim: only
#                labels — headings, button text, menu words. Never prose.
# - "unverified" a model wrote prose with nothing behind it. It is in the draft,
#                visible, editable and clearly marked — and the page **cannot be
#                published** while it is there.
#
# That last state is the honest answer to a problem the numeric gate does not
# solve. `check_numeric_grounding` catches an invented amount or date, because a
# number either appears in a verified quote or it does not. It cannot catch
# "Grillning är förbjuden i föreningen" — a complete fabrication with no digit
# in it, which sailed through as "editorial" and would have been publishable.
#
# Rather than pretend to detect fabricated prose semantically, the product does
# what it does everywhere else: the engine proposes and a **human decides**. A
# model may write prose; a person must adopt it before anyone outside the
# association can read it. Editing the text is adoption; so is pressing
# "Bekräfta texten". Neither is something the model can do for itself.
Grounding = Literal["authored", "grounded", "editorial", "unverified"]

GROUNDING_LABELS: dict[str, str] = {
    "authored": "Skrivet av föreningen",
    "grounded": "Hämtat ur föreningens dokument",
    "editorial": "AI-formulerad rubrik",
    "unverified": "AI-skriven text utan källa — behöver bekräftas",
}

# Blocks in this state stop a publication. Named rather than inlined so the
# route, the store and the workspace count all mean the same thing by it.
NEEDS_REVIEW: tuple[str, ...] = ("unverified",)


class Block(BaseModel):
    """One section of a page.

    ``props`` is validated against :mod:`app.website.components` on every write,
    so it is never an arbitrary bag: its keys are exactly the fields the block's
    type declares, and its values are exactly what those fields permit.
    """

    id: str
    type: str
    props: dict = Field(default_factory=dict)

    grounding: Grounding = "authored"
    # The citations behind this block's text, when a model derived it from the
    # association's documents. Copied rather than referenced, exactly as a task
    # copies its origin's evidence: re-indexing a document must not silently
    # re-describe what a published page says.
    sources: list[CitationOut] = Field(default_factory=list)
    # Which AI transaction wrote it, so the panel can show "den här texten kom
    # från den ändringen" months later.
    written_by_transaction: str = ""

    def public(self) -> dict:
        return {
            **self.model_dump(mode="json"),
            "grounding_label": GROUNDING_LABELS[self.grounding],
        }


class PageDraft(BaseModel):
    """What the page looks like right now, to whoever is editing it."""

    title: str
    content: list[Block] = Field(default_factory=list)
    updated_at: str = ""
    updated_by: str = ""
    # The revision this draft was last aligned with — either published from or
    # rolled back to. ``""`` means the page has never been published, which is
    # what the editor shows as "utkast, aldrig publicerad".
    based_on_revision_id: str = ""

    def dirty_against(self, revision: "PageRevision | None") -> bool:
        """Whether the draft says something the given revision does not.

        Compared on the *stored content*, not on a timestamp: opening the editor
        and closing it again must not be able to make a page look unpublished.
        """
        if revision is None:
            return True
        return (
            self.title != revision.title
            or [b.model_dump(mode="json") for b in self.content]
            != [b.model_dump(mode="json") for b in revision.content]
        )


class PublishWindow(BaseModel):
    """When a published page is actually shown.

    The draft keeps its own copy on :class:`SitePage`; this second copy belongs
    to the immutable publication and is the only one the public endpoint reads.
    """

    starts: str = ""  # ÅÅÅÅ-MM-DD, inclusive
    ends: str = ""    # ÅÅÅÅ-MM-DD, inclusive

    def visible_on(self, day: str) -> bool:
        if self.starts and day < self.starts:
            return False
        if self.ends and day > self.ends:
            return False
        return True


class PageRevision(BaseModel):
    """A published state of a page, written once and never again.

    Held in its own file per revision (see :mod:`app.website.store`) precisely
    because it is immutable: nothing that is never rewritten belongs in a
    document that is rewritten on every keystroke.

    It carries the page's **address** as well as its content, and that is not a
    detail. The published view used to read the slug off the live page, so
    renaming a draft moved a published page's address under the public's feet
    without anyone publishing anything.
    """

    id: str
    page_id: str
    seq: int  # 1, 2, 3… — what the UI calls "version 3"
    title: str
    slug: str = ""
    content: list[Block] = Field(default_factory=list)
    # These are page-level public state, not editor metadata. Keeping them in
    # the revision prevents a draft scheduling or home-page change from
    # changing what a visitor sees before the next human publication.
    publish_window: PublishWindow = Field(default_factory=PublishWindow)
    home: bool = False
    created_at: str
    created_by: str
    note: str = ""
    # The draft transaction this revision was cut at, so a revision can be read
    # back to the edits that produced it.
    from_transaction: str = ""

    def public(self, *, with_content: bool = False) -> dict:
        data = self.model_dump(mode="json", exclude={"content"})
        data["block_count"] = len(self.content)
        if with_content:
            data["content"] = [b.public() for b in self.content]
        return data


class Publication(BaseModel):
    """The act of putting one revision in front of the public.

    Separate from the revision because the same revision can be published twice
    — that is precisely what a rollback is — and because "when did this text go
    live, and who decided that" is a different question from "what does it say".
    """

    revision_id: str
    seq: int
    published_at: str
    published_by: str
    # True when this publication re-published an already-existing revision
    # instead of a freshly cut one.
    rollback: bool = False
    note: str = ""


class SitePage(BaseModel):
    """A page's identity, its draft, and what the public currently sees."""

    id: str            # stable, derived from the first slug, never reused
    slug: str          # the address segment: "for-boende"
    draft: PageDraft
    publication: Publication | None = None
    publish_window: PublishWindow = Field(default_factory=PublishWindow)
    # Every page has a revision count so "version 4" means the same thing to
    # everyone; the revisions themselves are loaded on demand.
    revision_seq: int = 0
    created_at: str = ""
    created_by: str = ""
    # The one page that answers "/" — exactly one page carries it, enforced by
    # the store rather than by whoever happens to be writing a route.
    home: bool = False

    @property
    def title(self) -> str:
        return self.draft.title

    @property
    def published(self) -> bool:
        return self.publication is not None

    def dirty_against(self, revision: "PageRevision | None") -> bool:
        """Whether this page says anything the published revision does not.

        Wider than the draft's own check by exactly one field: the address.
        A renamed slug is an unpublished change like any other, and treating it
        as one is what stops "publicera" from looking like a no-op on a page
        whose address has moved.
        """
        if revision is None:
            return True
        if revision.slug and revision.slug != self.slug:
            return True
        if revision.publish_window != self.publish_window or revision.home != self.home:
            return True
        return self.draft.dirty_against(revision)

    def needs_review(self) -> list["Block"]:
        """Blocks a model wrote and nobody has adopted. Publication blockers."""
        return [b for b in self.draft.content if b.grounding in NEEDS_REVIEW]

    def public(self, *, day: str = "") -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.draft.title,
            "home": self.home,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "block_count": len(self.draft.content),
            "updated_at": self.draft.updated_at,
            "updated_by": self.draft.updated_by,
            "published": self.published,
            "publication": self.publication.model_dump(mode="json") if self.publication else None,
            "revision_seq": self.revision_seq,
            "publish_window": self.publish_window.model_dump(mode="json"),
            "visible": bool(self.published and (not day or self.publish_window.visible_on(day))),
        }


class NavigationItem(BaseModel):
    """One entry in the site menu.

    A menu entry points at a page by id and carries no address of its own: a
    renamed page keeps its place in the menu, and there is no way to write a
    menu that links somewhere the site does not have.
    """

    page_id: str
    label: str = ""  # empty = use the page's own title


class SiteSettings(BaseModel):
    """The few things that are true of the whole site."""

    name: str = ""          # "Brf Gjutformen 12" — falls back to the tenant name
    tagline: str = ""
    accent: Literal["koppar", "skog", "hav", "sten"] = "koppar"
    footer_text: str = ""
    contact_email: str = ""
    contact_phone: str = ""


class SiteChrome(BaseModel):
    """The published state of everything that is true of the whole site.

    A page's blocks were versioned from the start; the menu and the site's name
    were not, and read straight off the draft. So removing a page from the menu,
    or renaming the association, changed what a visitor saw immediately — and
    the menu was something the AI partner was allowed to rearrange. The
    publication boundary was real for a page's middle and imaginary around its
    edges.

    Snapshotting both here, and serving the public from the snapshot, closes
    that. Any publication updates it: pressing publicera makes what is on the
    canvas live, chrome included, which is what the operator means by it.
    """

    navigation: list[NavigationItem] = Field(default_factory=list)
    settings: SiteSettings = Field(default_factory=SiteSettings)
    # A page's `home` flag is draft state. This id is the one home selection
    # that was made public by the last human publication action.
    home_page_id: str = ""
    published_at: str = ""
    published_by: str = ""


class SiteTransaction(BaseModel):
    """One understandable change, however many operations it took.

    This is the unit the undo button acts on and the unit the AI panel lists.
    An AI response that creates a page, fills it with four blocks and adds it to
    the menu is *one* of these — "Ny sida för nya boende, 6 operationer" — not
    six things a board member has to reason about separately.

    ``inverse`` holds commands, not a snapshot. That is the more expensive
    choice and the correct one: undo then runs through the same validation as
    every other write, so there is no second path into the data that could
    accept something the first one refuses.
    """

    id: str
    at: str
    by: str
    actor: Actor
    summary: str                       # Swedish, one line, shown in the history
    commands: list[dict] = Field(default_factory=list)
    inverse: list[dict] = Field(default_factory=list)
    # What the operator asked for, when a model was involved. Kept because the
    # instruction is the only record of *intent* — the commands say what changed,
    # not what was wanted.
    prompt: str = ""
    # The transaction this one takes back, when it is an undo. There is
    # deliberately no matching `undone_by` field: writing one meant going back
    # and editing a record that was already on disk, in a log this module calls
    # append-only — and the append-only check could not catch it, because it
    # compares entry *ids* and the id had not changed.
    #
    # "Has this been undone?" is therefore *derived* at read time by
    # :meth:`Site.undone_map`, from the later transaction that says so. Same
    # answer, and the log is now append-only in fact rather than in name.
    undoes: str = ""
    # Page ids this touched, so the history can be filtered per page without
    # re-reading every command.
    page_ids: list[str] = Field(default_factory=list)

    def public(self, *, undone_by: str = "") -> dict:
        return {
            **self.model_dump(mode="json"),
            "actor_label": ACTOR_LABELS[self.actor],
            "operation_count": len(self.commands),
            "undone_by": undone_by,
            "undoable": not undone_by and bool(self.inverse),
        }


class Site(BaseModel):
    """Everything about one association's website except its published bytes."""

    tenant_id: str
    schema_version: int = SCHEMA_VERSION
    settings: SiteSettings = Field(default_factory=SiteSettings)
    pages: list[SitePage] = Field(default_factory=list)
    navigation: list[NavigationItem] = Field(default_factory=list)
    history: list[SiteTransaction] = Field(default_factory=list)
    # What the public currently sees at site level. None until the first
    # publication; from then on it is the only thing the public view reads for
    # the menu and the settings.
    published_chrome: SiteChrome | None = None

    def undone_map(self) -> dict[str, str]:
        """{undone transaction id: the transaction that undid it}.

        Derived, never stored — see :class:`SiteTransaction`.
        """
        return {t.undoes: t.id for t in self.history if t.undoes}

    def chrome_dirty(self) -> bool:
        """Whether the menu or the settings say something the public has not seen."""
        published = self.published_chrome
        if published is None:
            return bool(self.navigation) or self.settings != SiteSettings()
        return (
            [n.model_dump(mode="json") for n in self.navigation]
            != [n.model_dump(mode="json") for n in published.navigation]
            or self.settings.model_dump(mode="json") != published.settings.model_dump(mode="json")
        )

    def page(self, page_id: str) -> SitePage | None:
        return next((p for p in self.pages if p.id == page_id), None)

    def page_by_slug(self, slug: str) -> SitePage | None:
        return next((p for p in self.pages if p.slug == slug), None)

    def home_page(self) -> SitePage | None:
        return next((p for p in self.pages if p.home), None)

    def transaction(self, transaction_id: str) -> SiteTransaction | None:
        return next((t for t in self.history if t.id == transaction_id), None)

    def navigation_public(
        self,
        items: list[NavigationItem] | None = None,
        *,
        revisions: dict[str, PageRevision] | None = None,
    ) -> list[dict]:
        """The menu with page titles resolved, dropping entries whose page is gone.

        Dropping rather than erroring is deliberate: a menu is a view of the
        pages, and a dangling entry is a rendering problem, not a reason to
        refuse to show the site.

        ``items`` lets the public view pass the *published* menu instead of the
        draft's. When ``revisions`` is supplied, titles and addresses resolve
        against those immutable public revisions too; otherwise this is the
        editor/workspace view and resolves against the draft.
        """
        rows: list[dict] = []
        for item in (self.navigation if items is None else items):
            page = self.page(item.page_id)
            if page is None:
                continue
            revision = revisions.get(page.id) if revisions is not None else None
            if revisions is not None and revision is None:
                continue
            rows.append(
                {
                    "page_id": page.id,
                    "slug": revision.slug if revision is not None else page.slug,
                    "label": item.label or (revision.title if revision is not None else page.draft.title),
                    "published": revision is not None if revisions is not None else page.published,
                }
            )
        return rows


__all__ = [
    "ACTOR_LABELS",
    "GROUNDING_LABELS",
    "SCHEMA_VERSION",
    "Actor",
    "Block",
    "Grounding",
    "NavigationItem",
    "PageDraft",
    "PageRevision",
    "Publication",
    "PublishWindow",
    "NEEDS_REVIEW",
    "Site",
    "SiteChrome",
    "SitePage",
    "SiteSettings",
    "SiteTransaction",
]
