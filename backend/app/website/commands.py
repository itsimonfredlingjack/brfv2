"""The one way anything on the website changes.

Every edit in this feature — a board member dragging a section, someone typing
in a heading, the AI partner rewriting a paragraph, and the undo that takes any
of it back — arrives here as a **command**, is validated here, and is applied
here. There is no second path. That is not tidiness; it is the only way the
guarantees below can be stated as facts rather than intentions:

- **Validation happens once.** A prop that the editor would refuse is refused
  for the model too, because neither of them validates anything — this does.
- **The model cannot invent a component.** ``insert_block`` resolves its type
  through :mod:`app.website.components` or raises. There is no free-form node.
- **Permissions apply equally.** The route decides who may issue commands;
  nothing here cares whether a human or a model composed one, except where the
  difference is the point (grounding, and the publish commands a model may
  never issue at all).
- **Undo is not a special case.** Applying a command yields the commands that
  would reverse it, so undo re-enters this module through the same front door
  and is validated like anything else.

**Commands, not replacement objects.** A caller never sends a page back. It says
*move this block after that one*, and the engine reads the page under the
store's lock and does it. Two people editing the same page therefore produce two
changes rather than one silently winning — the failure this repo already learned
the hard way in :mod:`app.history`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Callable, Iterable, Literal, Union

from pydantic import BaseModel, Field, ValidationError

from ..schemas import CitationOut
from ..terms import parse_iso
from .components import (
    AI_INSERTABLE,
    UnknownComponent,
    UnknownField,
    field_for,
    spec_for,
)
from .grounding import check_written_content, grounding_label
from .models import (
    Block,
    NavigationItem,
    PublishWindow,
    Site,
    SitePage,
)
from .sanitize import UnsafeContent, check_href, check_richtext

MAX_PAGES = 40
MAX_BLOCKS_PER_PAGE = 60
MAX_NAV_ITEMS = 12
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CommandRefused(ValueError):
    """A command that will not be applied, with the reason in Swedish.

    One exception type for every refusal in this module so a route can turn all
    of them into one 422 with a sentence the operator can act on — and so the AI
    layer can hand the same sentence back to the model as the reason its
    proposal was not written.
    """


# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------
#
# A discriminated union rather than a dict with a "command" key: an unknown
# command name fails at parse time with a message naming what is allowed, and no
# handler ever runs against a payload that was not validated for it. This is
# what makes "the AI cannot bypass the editor's domain rules" a property of the
# type system rather than a hope about a prompt.


class _Base(BaseModel):
    pass


class ReadPage(_Base):
    """Not a mutation. The AI's way of asking for a page it was not handed.

    It is in the same union as the writes because it is issued the same way and
    must be validated the same way; the engine executes it without touching
    history, and :data:`MUTATING` is what every other part of the system uses to
    tell the two apart.
    """

    command: Literal["read_page"]
    page_id: str


class InsertBlock(_Base):
    command: Literal["insert_block"]
    page_id: str
    type: str
    props: dict = Field(default_factory=dict)
    # Position. `after_block_id` is what a person says ("under nyheterna") and
    # what the AI is told to use; `index` is what a drag produces. Exactly one
    # is needed, and neither means "last".
    after_block_id: str | None = None
    index: int | None = None
    # Supplied by the caller so a retried request lands on the same block
    # instead of a second copy of it (see `_block_id`).
    block_id: str | None = None
    # Set by the AI layer when this block's text was derived from the
    # association's own documents. Never accepted from an untrusted caller as a
    # way to *claim* grounding: the route strips it, and the AI layer fills it
    # from what app.answer actually verified.
    sources: list[CitationOut] = Field(default_factory=list)


class UpdateBlock(_Base):
    """Change some props of one block. Only the keys sent are touched."""

    command: Literal["update_block"]
    page_id: str
    block_id: str
    props: dict
    sources: list[CitationOut] = Field(default_factory=list)


class UpdateText(_Base):
    """One text or rich-text field. The narrow case, and by far the most common.

    Separate from ``update_block`` because it is what inline editing produces
    and what the AI issues for "korta den markerade texten": a command that can
    only touch one field is one that cannot accidentally clear its neighbours.
    """

    command: Literal["update_text"]
    page_id: str
    block_id: str
    field: str
    value: str
    sources: list[CitationOut] = Field(default_factory=list)


class MoveBlock(_Base):
    command: Literal["move_block"]
    page_id: str
    block_id: str
    after_block_id: str | None = None
    index: int | None = None


class DeleteBlock(_Base):
    command: Literal["delete_block"]
    page_id: str
    block_id: str


class DuplicateBlock(_Base):
    command: Literal["duplicate_block"]
    page_id: str
    block_id: str
    block_id_new: str | None = None


class ReplaceImage(_Base):
    command: Literal["replace_image"]
    page_id: str
    block_id: str
    field: str
    src: str
    alt: str


class CreatePage(_Base):
    command: Literal["create_page"]
    title: str
    slug: str = ""            # derived from the title when empty
    page_id: str | None = None
    home: bool = False


class RenamePage(_Base):
    command: Literal["rename_page"]
    page_id: str
    title: str
    slug: str | None = None   # None = leave the address alone


class DeletePage(_Base):
    command: Literal["delete_page"]
    page_id: str


class UpdateNavigation(_Base):
    """One menu entry at a time — add, remove or move it.

    Not "here is the new menu": a whole-menu write is the replacement-object
    shape this codebase has already been bitten by, and it would let a stale
    client drop an entry somebody else added a second earlier.
    """

    command: Literal["update_navigation"]
    action: Literal["add", "remove", "move", "relabel"]
    page_id: str
    # Where. On `move`, None means first — "lägg den överst" is a thing people
    # ask for. On `add`, None means **last**, because "lägg sidan i menyn" with
    # no position said means at the end; defaulting it to the front put every
    # new page ahead of the start page.
    after_page_id: str | None = None
    label: str = ""


class SetPublishWindow(_Base):
    command: Literal["set_publish_window"]
    page_id: str
    starts: str = ""
    ends: str = ""


class ConfirmBlock(_Base):
    """A person adopting text a model wrote. Human-only, and the point of it.

    The model may write prose; until somebody says "yes, that is what we mean",
    the page will not publish. This is that sentence, recorded as a command like
    everything else — so it appears in the history with a name and a time, and
    so it can be taken back.
    """

    command: Literal["confirm_block"]
    page_id: str
    block_id: str
    confirmed: bool = True


class UpdateSettings(_Base):
    """Site-wide values. One field per command, same reasoning as the menu."""

    command: Literal["update_settings"]
    field: Literal["name", "tagline", "accent", "footer_text", "contact_email", "contact_phone"]
    value: str


Command = Annotated[
    Union[
        ReadPage,
        InsertBlock,
        UpdateBlock,
        UpdateText,
        MoveBlock,
        DeleteBlock,
        DuplicateBlock,
        ReplaceImage,
        CreatePage,
        RenamePage,
        DeletePage,
        UpdateNavigation,
        SetPublishWindow,
        ConfirmBlock,
        UpdateSettings,
    ],
    Field(discriminator="command"),
]


class _CommandEnvelope(BaseModel):
    command: Command


COMMAND_NAMES: tuple[str, ...] = (
    "read_page",
    "insert_block",
    "update_block",
    "update_text",
    "move_block",
    "delete_block",
    "duplicate_block",
    "replace_image",
    "create_page",
    "rename_page",
    "delete_page",
    "update_navigation",
    "set_publish_window",
    "confirm_block",
    "update_settings",
)

MUTATING: frozenset[str] = frozenset(COMMAND_NAMES) - {"read_page"}

# Publishing is not in this vocabulary at all, and its absence is the design.
# A model can write the whole site and still cannot show any of it to anyone:
# publicera and återställ are routes of their own, behind `require_admin`, with
# no command that reaches them. "Nothing becomes public until a human publishes
# it" is therefore not a rule the AI is asked to respect — it is one it has no
# way to express.
# Publishing is not in this vocabulary at all (see above), and three more
# commands are withheld from the model for the same reason rather than a
# different one: each of them changes what a *visitor* sees.
#
# - `update_settings` — the site's public name and footer.
# - `set_publish_window` — a scheduling lever that can take a published page
#   off the site outright. A model asking for that is asking to unpublish.
# - `confirm_block` — adopting model-written prose is the one act that must not
#   be available to the thing that wrote it.
#
# `delete_page` stays available, because deleting a *published* page is refused
# for everyone (see `_delete_page`); on a draft page it is ordinary tidying.
AI_ALLOWED: frozenset[str] = frozenset(COMMAND_NAMES) - {
    "update_settings",
    "set_publish_window",
    "confirm_block",
}


def parse_command(raw: dict) -> Command:
    """Turn one JSON object into a validated command, or refuse it in Swedish."""
    if not isinstance(raw, dict):
        raise CommandRefused("En operation måste vara ett JSON-objekt.")
    name = raw.get("command")
    if name not in COMMAND_NAMES:
        raise CommandRefused(
            f"Okänd operation {name!r}. Tillåtna: {', '.join(COMMAND_NAMES)}."
        )
    try:
        return _CommandEnvelope.model_validate({"command": raw}).command
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'][1:]) or 'operationen'}: {err['msg']}"
            for err in exc.errors()[:4]
        )
        raise CommandRefused(f"Operationen {name} gick inte att tolka ({problems}).") from exc


def parse_commands(raw: Iterable[dict]) -> list[Command]:
    return [parse_command(item) for item in raw]


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


class CommandContext(BaseModel):
    """Everything applying a command needs that is not in the command itself."""

    model_config = {"arbitrary_types_allowed": True}

    actor: Literal["human", "ai"] = "human"
    user_id: str = ""
    now: str = ""
    transaction_id: str = ""
    # The operator's own words for this change. Support for the grounding gate
    # (see app.website.grounding for exactly why that is sound here), and
    # nothing else.
    instruction: str = ""
    # The association's own names, so its registered name is not read as a
    # numeric claim.
    trusted_names: tuple[str, ...] = ()
    # Whether a document id is one of *this tenant's* documents. Injected rather
    # than imported so the engine stays free of the store, and so the check is
    # impossible to satisfy with another association's id: the callable the
    # route passes is bound to the resolved tenant's Store.
    document_exists: Callable[[str], bool] | None = None

    def ordinal_id(self, kind: str, *parts: str) -> str:
        """A derived id — never a random one.

        The repo's rule for anything creatable twice: a retried request must
        recompute the same id and converge on the row that exists, rather than
        leaving the association with two blocks nobody can tell apart.
        """
        seed = "\x1f".join((kind, self.transaction_id, *parts))
        return f"{kind}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"


class Applied(BaseModel):
    """What one command did, and what would undo it."""

    summary: str
    inverse: list[dict] = Field(default_factory=list)
    page_ids: list[str] = Field(default_factory=list)
    # Non-mutating commands (read_page) answer here instead of changing anything.
    read: dict | None = None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _slugify(title: str) -> str:
    lowered = (title or "").strip().lower()
    table = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u", "ø": "o", "æ": "a"})
    lowered = lowered.translate(table)
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:60] or "sida"


def _check_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise CommandRefused(
            f"Adressen {slug!r} går inte att använda. Använd små bokstäver, siffror och "
            "bindestreck, till exempel 'for-boende'."
        )
    return slug


def _check_date(value: str, *, what: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if parse_iso(value) is None:
        raise CommandRefused(f"{what} ska skrivas ÅÅÅÅ-MM-DD (fick {value!r}).")
    return value


def _validate_value(field_name: str, spec, value, ctx: CommandContext, *, path: str):
    """One prop against its declared field. Returns the value to store."""
    label = f"{path}{spec.label}"
    kind = spec.kind

    if kind in ("text", "textarea"):
        if not isinstance(value, str):
            raise CommandRefused(f"{label} ska vara text.")
        value = value.strip() if kind == "text" else value
        cap = spec.max_length or 2000
        if len(value) > cap:
            raise CommandRefused(f"{label} får vara högst {cap} tecken (fick {len(value)}).")
        if spec.required and not value:
            raise CommandRefused(f"{label} måste fyllas i.")
        return value

    if kind == "richtext":
        if not isinstance(value, str):
            raise CommandRefused(f"{label} ska vara text.")
        try:
            return check_richtext(value, what=label)
        except UnsafeContent as exc:
            raise CommandRefused(str(exc)) from exc

    if kind == "select":
        allowed = spec.option_values()
        if value not in allowed:
            raise CommandRefused(
                f"{label} måste vara ett av: {', '.join(allowed)} (fick {value!r})."
            )
        return value

    if kind == "date":
        return _check_date(value if isinstance(value, str) else "", what=label)

    if kind == "image":
        if not isinstance(value, dict):
            raise CommandRefused(f"{label} ska vara en bild med adress och alt-text.")
        src = str(value.get("src", "") or "").strip()
        alt = str(value.get("alt", "") or "").strip()
        try:
            src = check_href(src, what=f"Bildadressen för {label}")
        except UnsafeContent as exc:
            raise CommandRefused(str(exc)) from exc
        if src and not alt:
            # Not a style preference. A published page with an unlabelled image
            # is unusable with a screen reader, and the editor has no way to add
            # the alt text later if the model was allowed to skip it now.
            raise CommandRefused(
                f"{label} saknar alt-text. Beskriv kort vad bilden visar — utan det "
                "går bilden inte att uppfatta med skärmläsare."
            )
        if spec.required and not src:
            raise CommandRefused(f"{label} måste ha en bild.")
        return {"src": src, "alt": alt[:200]}

    if kind == "link":
        if not isinstance(value, dict):
            raise CommandRefused(f"{label} ska vara en länk med text och adress.")
        text = str(value.get("label", "") or "").strip()[:120]
        try:
            href = check_href(str(value.get("href", "") or ""), what=label)
        except UnsafeContent as exc:
            raise CommandRefused(str(exc)) from exc
        if href and not text:
            raise CommandRefused(f"{label} har en adress men ingen text att klicka på.")
        return {"label": text, "href": href}

    if kind == "document":
        doc_id = str(value or "").strip()
        if not doc_id:
            if spec.required:
                raise CommandRefused(f"{label} måste peka på ett dokument.")
            return ""
        if ctx.document_exists is not None and not ctx.document_exists(doc_id):
            # 404-shaped by intent: an id that is not this tenant's is reported
            # as "finns inte", never as "finns men inte här".
            raise CommandRefused(
                f"{label} pekar på ett dokument som inte finns i föreningens arkiv."
            )
        return doc_id

    if kind == "list":
        if not isinstance(value, list):
            raise CommandRefused(f"{label} ska vara en lista.")
        cap = spec.max_items or 50
        if len(value) > cap:
            raise CommandRefused(f"{label} får innehålla högst {cap} poster.")
        rows = []
        for i, row in enumerate(value, start=1):
            if not isinstance(row, dict):
                raise CommandRefused(f"{label}: post {i} ska vara ett objekt.")
            unknown = set(row) - set(spec.fields)
            if unknown:
                raise CommandRefused(
                    f"{label}: post {i} har okända fält {sorted(unknown)}. "
                    f"Tillåtna: {sorted(spec.fields)}."
                )
            out = {}
            for sub_name, sub_spec in spec.fields.items():
                sub_value = row.get(sub_name, _default_for(sub_spec))
                out[sub_name] = _validate_value(
                    sub_name, sub_spec, sub_value, ctx, path=f"{label} post {i}: "
                )
            rows.append(out)
        return rows

    raise CommandRefused(f"{label} har en fälttyp som inte stöds ({kind}).")


def _default_for(spec):
    return {
        "text": "", "textarea": "", "richtext": "", "date": "", "list": [],
        "document": "", "image": {"src": "", "alt": ""}, "link": {"label": "", "href": ""},
        "select": spec.option_values()[0] if spec.options else "",
    }[spec.kind]


def validate_props(
    component_type: str, props: dict, ctx: CommandContext, *, partial: bool
) -> dict:
    """Every prop against the block type's declared fields.

    ``partial`` distinguishes an update (only what was sent) from an insert
    (the whole block, with the type's defaults filled in and required fields
    enforced).
    """
    try:
        spec = spec_for(component_type)
    except UnknownComponent as exc:
        raise CommandRefused(str(exc)) from exc

    if not isinstance(props, dict):
        raise CommandRefused("Blockets värden ska vara ett objekt.")

    unknown = set(props) - set(spec.fields)
    if unknown:
        raise CommandRefused(
            f"{spec.label} har inga fält som heter {sorted(unknown)}. "
            f"Fält: {sorted(spec.fields)}."
        )

    out: dict = {}
    names = props.keys() if partial else spec.fields.keys()
    for name in names:
        field = spec.fields[name]
        if partial:
            value = props[name]
        else:
            value = props.get(name, spec.defaults.get(name, _default_for(field)))
        out[name] = _validate_value(name, field, value, ctx, path="")
    return out


def _gate_written(block_type: str, props: dict, sources, ctx: CommandContext) -> None:
    """Refuse model-written text that asserts something nothing supports."""
    if ctx.actor != "ai":
        return
    verdict = check_written_content(
        block_type,
        props,
        sources=sources,
        instruction=ctx.instruction,
        trusted_names=ctx.trusted_names,
    )
    if not verdict.ok:
        raise CommandRefused(verdict.reason)


# --------------------------------------------------------------------------
# Applying
# --------------------------------------------------------------------------


def _page(site: Site, page_id: str) -> SitePage:
    page = site.page(page_id)
    if page is None:
        raise CommandRefused(f"Sidan {page_id!r} finns inte.")
    return page


def _block_index(page: SitePage, block_id: str) -> int:
    for i, block in enumerate(page.draft.content):
        if block.id == block_id:
            return i
    raise CommandRefused(f"Blocket {block_id!r} finns inte på sidan {page.draft.title!r}.")


def _target_index(page: SitePage, after_block_id: str | None, index: int | None) -> int:
    if after_block_id:
        return _block_index(page, after_block_id) + 1
    if index is None:
        return len(page.draft.content)
    return max(0, min(int(index), len(page.draft.content)))


def _touch(page: SitePage, ctx: CommandContext) -> None:
    page.draft.updated_at = ctx.now
    page.draft.updated_by = ctx.user_id


def _label(block: Block) -> str:
    """A short Swedish name for a block, for history lines a person reads."""
    try:
        spec = spec_for(block.type)
    except UnknownComponent:
        return block.type
    heading = block.props.get("heading") or block.props.get("title") or ""
    return f"{spec.label}" + (f" ”{str(heading)[:40]}”" if heading else "")


def apply_command(site: Site, command, ctx: CommandContext) -> Applied:
    """Apply one validated command to the site. Raises :class:`CommandRefused`.

    The caller holds the store's lock and works on a copy read from disk inside
    it, so a raise here leaves nothing written — a transaction is all-or-nothing
    without needing a rollback path of its own.
    """
    name = command.command

    if ctx.actor == "ai" and name not in AI_ALLOWED:
        raise CommandRefused(
            f"AI-assistenten får inte utföra {name}. Den ändringen gör en människa."
        )

    handler = _HANDLERS.get(name)
    if handler is None:  # unreachable: parse_command already refused unknown names
        raise CommandRefused(f"Okänd operation {name!r}.")
    return handler(site, command, ctx)


# ---- handlers ----


def _read_page(site: Site, cmd: ReadPage, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    return Applied(
        summary=f"Läste sidan {page.draft.title}",
        page_ids=[page.id],
        read={
            "page_id": page.id,
            "title": page.draft.title,
            "slug": page.slug,
            "content": [
                {"id": b.id, "type": b.type, "props": b.props, "grounding": b.grounding}
                for b in page.draft.content
            ],
        },
    )


def _insert_block(site: Site, cmd: InsertBlock, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    if len(page.draft.content) >= MAX_BLOCKS_PER_PAGE:
        raise CommandRefused(
            f"Sidan har redan {MAX_BLOCKS_PER_PAGE} block, vilket är så många en sida "
            "kan innehålla. Dela upp innehållet på flera sidor."
        )
    try:
        spec = spec_for(cmd.type)
    except UnknownComponent as exc:
        raise CommandRefused(str(exc)) from exc
    if ctx.actor == "ai" and cmd.type not in AI_INSERTABLE:
        raise CommandRefused(f"AI-assistenten får inte lägga in blocktypen {spec.label}.")
    if spec.singleton and any(b.type == cmd.type for b in page.draft.content):
        raise CommandRefused(
            f"Sidan har redan ett block av typen {spec.label}, och den typen finns bara en gång per sida."
        )

    props = validate_props(cmd.type, cmd.props or {}, ctx, partial=False)
    _gate_written(cmd.type, props, cmd.sources, ctx)

    at = _target_index(page, cmd.after_block_id, cmd.index)
    block_id = cmd.block_id or ctx.ordinal_id("block", cmd.page_id, cmd.type, str(at))
    if any(b.id == block_id for b in page.draft.content):
        raise CommandRefused(f"Det finns redan ett block med id {block_id!r} på sidan.")

    block = Block(
        id=block_id,
        type=cmd.type,
        props=props,
        grounding=(
            grounding_label(cmd.type, props, cmd.sources) if ctx.actor == "ai" else "authored"
        ),
        sources=list(cmd.sources),
        written_by_transaction=ctx.transaction_id if ctx.actor == "ai" else "",
    )
    page.draft.content.insert(at, block)
    _touch(page, ctx)
    return Applied(
        summary=f"La till {_label(block)}",
        page_ids=[page.id],
        inverse=[{"command": "delete_block", "page_id": page.id, "block_id": block_id}],
    )


def _update_props(
    site: Site, page_id: str, block_id: str, changes: dict, sources, ctx: CommandContext
) -> Applied:
    """Shared by update_block, update_text and replace_image.

    The inverse is built from the values actually replaced — only the keys that
    changed — so undoing a change to one field cannot resurrect an older value
    of a field this command never touched.
    """
    page = _page(site, page_id)
    index = _block_index(page, block_id)
    block = page.draft.content[index]

    validated = validate_props(block.type, changes, ctx, partial=True)
    merged = {**block.props, **validated}
    _gate_written(block.type, merged, sources or block.sources, ctx)

    before = {key: block.props.get(key) for key in validated if block.props.get(key) != validated[key]}
    if not before and not sources:
        # Nothing actually differs. Refused rather than recorded, for the same
        # reason app.tasks refuses "Inget att ändra": a history entry that says
        # nothing happened is worse than no entry.
        raise CommandRefused("Ingenting ändrades.")

    block.props = merged
    if ctx.actor == "ai":
        block.grounding = grounding_label(block.type, merged, sources or block.sources)
        if sources:
            block.sources = list(sources)
        block.written_by_transaction = ctx.transaction_id
    elif block.grounding == "unverified":
        # A person editing model-written prose *is* adopting it. Requiring a
        # separate confirmation after they have already rewritten the sentence
        # would be ceremony, and ceremony is what gets clicked through.
        block.grounding = "authored"
    _touch(page, ctx)

    changed_labels = ", ".join(
        field_for(block.type, key).label.lower() for key in sorted(before)
    ) or "innehåll"
    return Applied(
        summary=f"Ändrade {changed_labels} i {_label(block)}",
        page_ids=[page.id],
        inverse=[
            {
                "command": "update_block",
                "page_id": page.id,
                "block_id": block_id,
                "props": before,
            }
        ],
    )


def _update_block(site: Site, cmd: UpdateBlock, ctx: CommandContext) -> Applied:
    if not cmd.props:
        raise CommandRefused("Ingenting att ändra.")
    return _update_props(site, cmd.page_id, cmd.block_id, cmd.props, cmd.sources, ctx)


def _update_text(site: Site, cmd: UpdateText, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    block = page.draft.content[_block_index(page, cmd.block_id)]
    try:
        spec = field_for(block.type, cmd.field)
    except (UnknownField, UnknownComponent) as exc:
        raise CommandRefused(str(exc)) from exc
    if spec.kind not in ("text", "textarea", "richtext"):
        raise CommandRefused(
            f"{spec.label} är inte ett textfält och kan inte ändras med update_text."
        )
    return _update_props(site, cmd.page_id, cmd.block_id, {cmd.field: cmd.value}, cmd.sources, ctx)


def _replace_image(site: Site, cmd: ReplaceImage, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    block = page.draft.content[_block_index(page, cmd.block_id)]
    try:
        spec = field_for(block.type, cmd.field)
    except (UnknownField, UnknownComponent) as exc:
        raise CommandRefused(str(exc)) from exc
    if spec.kind != "image":
        raise CommandRefused(f"{spec.label} är inte ett bildfält.")
    return _update_props(
        site, cmd.page_id, cmd.block_id, {cmd.field: {"src": cmd.src, "alt": cmd.alt}}, None, ctx
    )


def _move_block(site: Site, cmd: MoveBlock, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    frm = _block_index(page, cmd.block_id)
    block = page.draft.content[frm]

    if cmd.after_block_id == cmd.block_id:
        raise CommandRefused("Ett block kan inte flyttas efter sig självt.")

    # The two ways of saying where, which do NOT mean the same thing:
    #
    # `after_block_id` is a position in the list *as it looks now*, with the
    # moving block still in it — "under nyheterna" is how a person describes it,
    # and how the AI is told to. Removing the block first shifts everything after
    # it left by one, hence the adjustment.
    #
    # `index` is the position the block should *end up* at, which is what a drag
    # reports (Puck's reorder gives a destination index in the final list). It
    # needs no adjustment, and applying one is how "move the first block down
    # one" became "it is already there".
    if cmd.after_block_id:
        target = _block_index(page, cmd.after_block_id) + 1
        to = target - 1 if target > frm else target
    elif cmd.index is None:
        to = len(page.draft.content) - 1
    else:
        to = max(0, min(int(cmd.index), len(page.draft.content) - 1))
    if to == frm:
        raise CommandRefused("Blocket ligger redan där.")

    page.draft.content.pop(frm)
    page.draft.content.insert(to, block)
    _touch(page, ctx)

    return Applied(
        summary=f"Flyttade {_label(block)}",
        page_ids=[page.id],
        inverse=[
            {"command": "move_block", "page_id": page.id, "block_id": cmd.block_id, "index": frm}
        ],
    )


def _delete_block(site: Site, cmd: DeleteBlock, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    index = _block_index(page, cmd.block_id)
    block = page.draft.content.pop(index)
    _touch(page, ctx)
    return Applied(
        summary=f"Tog bort {_label(block)}",
        page_ids=[page.id],
        # The whole block comes back, at the index it left from, with the id it
        # had — so undo restores the section rather than something resembling it.
        inverse=[
            {
                "command": "insert_block",
                "page_id": page.id,
                "type": block.type,
                "props": block.props,
                "index": index,
                "block_id": block.id,
                "sources": [s.model_dump(mode="json") for s in block.sources],
            }
        ],
    )


def _duplicate_block(site: Site, cmd: DuplicateBlock, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    index = _block_index(page, cmd.block_id)
    source = page.draft.content[index]
    if len(page.draft.content) >= MAX_BLOCKS_PER_PAGE:
        raise CommandRefused(f"Sidan rymmer högst {MAX_BLOCKS_PER_PAGE} block.")
    try:
        spec = spec_for(source.type)
    except UnknownComponent as exc:
        raise CommandRefused(str(exc)) from exc
    if spec.singleton:
        raise CommandRefused(f"{spec.label} finns bara en gång per sida och kan inte dupliceras.")

    new_id = cmd.block_id_new or ctx.ordinal_id("block", page.id, cmd.block_id, "copy")
    if any(b.id == new_id for b in page.draft.content):
        raise CommandRefused(f"Det finns redan ett block med id {new_id!r} på sidan.")
    copy = source.model_copy(deep=True, update={"id": new_id})
    page.draft.content.insert(index + 1, copy)
    _touch(page, ctx)
    return Applied(
        summary=f"Kopierade {_label(source)}",
        page_ids=[page.id],
        inverse=[{"command": "delete_block", "page_id": page.id, "block_id": new_id}],
    )


def _create_page(site: Site, cmd: CreatePage, ctx: CommandContext) -> Applied:
    if len(site.pages) >= MAX_PAGES:
        raise CommandRefused(f"Webbplatsen rymmer högst {MAX_PAGES} sidor.")
    title = (cmd.title or "").strip()
    if not title:
        raise CommandRefused("Sidan behöver en rubrik.")
    if len(title) > 120:
        raise CommandRefused("Sidans rubrik får vara högst 120 tecken.")

    slug = _check_slug((cmd.slug or "").strip() or _slugify(title))
    if site.page_by_slug(slug) is not None:
        raise CommandRefused(f"Det finns redan en sida med adressen /{slug}.")
    page_id = cmd.page_id or ctx.ordinal_id("page", slug)
    if site.page(page_id) is not None:
        raise CommandRefused(f"Det finns redan en sida med id {page_id!r}.")

    from .models import PageDraft

    page = SitePage(
        id=page_id,
        slug=slug,
        draft=PageDraft(title=title, content=[], updated_at=ctx.now, updated_by=ctx.user_id),
        created_at=ctx.now,
        created_by=ctx.user_id,
        # The first page ever created is the start page; after that, becoming the
        # start page is a deliberate act, never a side effect of adding a page.
        home=cmd.home or not site.pages,
    )
    if page.home:
        for other in site.pages:
            other.home = False
    site.pages.append(page)
    return Applied(
        summary=f"Skapade sidan {title}",
        page_ids=[page.id],
        inverse=[{"command": "delete_page", "page_id": page.id}],
    )


def _rename_page(site: Site, cmd: RenamePage, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    title = (cmd.title or "").strip()
    if not title:
        raise CommandRefused("Sidan behöver en rubrik.")
    if len(title) > 120:
        raise CommandRefused("Sidans rubrik får vara högst 120 tecken.")

    before: dict = {"command": "rename_page", "page_id": page.id, "title": page.draft.title}
    if cmd.slug is not None:
        slug = _check_slug(cmd.slug.strip())
        other = site.page_by_slug(slug)
        if other is not None and other.id != page.id:
            raise CommandRefused(f"Det finns redan en sida med adressen /{slug}.")
        before["slug"] = page.slug
        page.slug = slug
    if title == page.draft.title and cmd.slug is None:
        raise CommandRefused("Ingenting ändrades.")

    page.draft.title = title
    _touch(page, ctx)
    return Applied(summary=f"Döpte om sidan till {title}", page_ids=[page.id], inverse=[before])


def _delete_page(site: Site, cmd: DeletePage, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    if page.home:
        raise CommandRefused(
            "Startsidan kan inte tas bort. Gör en annan sida till startsida först."
        )
    if len(site.pages) <= 1:
        raise CommandRefused("Webbplatsen måste ha minst en sida.")
    if page.published:
        # Deleting a published page used to remove it from the public site
        # instantly — a live page vanishing without anybody publishing anything,
        # and something the AI partner could ask for. Taking a page down is now
        # its own human act, and this is refused until it has happened.
        raise CommandRefused(
            f"{page.draft.title} är publicerad. Avpublicera sidan först — då slutar "
            "den visas för besökare, och först därefter går den att ta bort."
        )

    nav_index = next((i for i, item in enumerate(site.navigation) if item.page_id == page.id), None)
    nav_after = site.navigation[nav_index - 1].page_id if nav_index else None
    nav_label = site.navigation[nav_index].label if nav_index is not None else ""

    site.pages = [p for p in site.pages if p.id != page.id]
    site.navigation = [item for item in site.navigation if item.page_id != page.id]

    # Undo puts the page back with its blocks, in order, and restores its place
    # in the menu — expressed entirely in commands, so it goes back in through
    # the same validation it originally passed.
    inverse: list[dict] = [
        {
            "command": "create_page",
            "title": page.draft.title,
            "slug": page.slug,
            "page_id": page.id,
        }
    ]
    for i, block in enumerate(page.draft.content):
        inverse.append(
            {
                "command": "insert_block",
                "page_id": page.id,
                "type": block.type,
                "props": block.props,
                "index": i,
                "block_id": block.id,
                "sources": [s.model_dump(mode="json") for s in block.sources],
            }
        )
    if nav_index is not None:
        inverse.append(
            {
                "command": "update_navigation",
                "action": "add",
                "page_id": page.id,
                "after_page_id": nav_after,
                "label": nav_label,
            }
        )
    return Applied(
        summary=f"Tog bort sidan {page.draft.title}", page_ids=[page.id], inverse=inverse
    )


def _update_navigation(site: Site, cmd: UpdateNavigation, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    index = next((i for i, item in enumerate(site.navigation) if item.page_id == page.id), None)

    def place(action: str, after: str | None, label: str) -> dict:
        return {
            "command": "update_navigation",
            "action": action,
            "page_id": page.id,
            "after_page_id": after,
            "label": label,
        }

    if cmd.action == "add":
        if index is not None:
            raise CommandRefused(f"{page.draft.title} finns redan i menyn.")
        if len(site.navigation) >= MAX_NAV_ITEMS:
            raise CommandRefused(
                f"Menyn rymmer högst {MAX_NAV_ITEMS} poster. En meny som är längre än så "
                "hjälper ingen att hitta."
            )
        at = _nav_target(site, cmd.after_page_id) if cmd.after_page_id else len(site.navigation)
        site.navigation.insert(at, NavigationItem(page_id=page.id, label=cmd.label.strip()[:60]))
        return Applied(
            summary=f"La in {page.draft.title} i menyn",
            page_ids=[page.id],
            inverse=[place("remove", None, "")],
        )

    if index is None:
        raise CommandRefused(f"{page.draft.title} finns inte i menyn.")
    current = site.navigation[index]
    previous = site.navigation[index - 1].page_id if index else None

    if cmd.action == "remove":
        site.navigation.pop(index)
        return Applied(
            summary=f"Tog bort {page.draft.title} ur menyn",
            page_ids=[page.id],
            inverse=[place("add", previous, current.label)],
        )

    if cmd.action == "relabel":
        label = cmd.label.strip()[:60]
        if label == current.label:
            raise CommandRefused("Ingenting ändrades.")
        before = current.label
        current.label = label
        return Applied(
            summary=f"Ändrade menytexten för {page.draft.title}",
            page_ids=[page.id],
            inverse=[place("relabel", None, before)],
        )

    # move
    if cmd.after_page_id == page.id:
        raise CommandRefused("En menypost kan inte flyttas efter sig själv.")
    target = _nav_target(site, cmd.after_page_id)
    to = target - 1 if target > index else target
    if to == index:
        raise CommandRefused("Menyposten ligger redan där.")
    site.navigation.pop(index)
    site.navigation.insert(to, current)
    return Applied(
        summary=f"Flyttade {page.draft.title} i menyn",
        page_ids=[page.id],
        inverse=[place("move", previous, "")],
    )


def _nav_target(site: Site, after_page_id: str | None) -> int:
    if not after_page_id:
        return 0
    for i, item in enumerate(site.navigation):
        if item.page_id == after_page_id:
            return i + 1
    raise CommandRefused(f"Menyposten {after_page_id!r} finns inte, så inget kan läggas efter den.")


def _set_publish_window(site: Site, cmd: SetPublishWindow, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    starts = _check_date(cmd.starts, what="Startdatum")
    ends = _check_date(cmd.ends, what="Slutdatum")
    if starts and ends and ends < starts:
        raise CommandRefused("Slutdatumet ligger före startdatumet.")
    before = page.publish_window
    if before.starts == starts and before.ends == ends:
        raise CommandRefused("Ingenting ändrades.")
    page.publish_window = PublishWindow(starts=starts, ends=ends)
    return Applied(
        summary=(
            f"Satte visningsperiod för {page.draft.title}"
            if (starts or ends)
            else f"Tog bort visningsperioden för {page.draft.title}"
        ),
        page_ids=[page.id],
        inverse=[
            {
                "command": "set_publish_window",
                "page_id": page.id,
                "starts": before.starts,
                "ends": before.ends,
            }
        ],
    )


def _confirm_block(site: Site, cmd: ConfirmBlock, ctx: CommandContext) -> Applied:
    page = _page(site, cmd.page_id)
    block = page.draft.content[_block_index(page, cmd.block_id)]
    before = block.grounding
    after = "authored" if cmd.confirmed else "unverified"
    if before == after:
        raise CommandRefused("Ingenting ändrades.")
    if cmd.confirmed and before != "unverified":
        raise CommandRefused(f"{_label(block)} behöver ingen bekräftelse.")
    block.grounding = after
    _touch(page, ctx)
    return Applied(
        summary=(
            f"Bekräftade texten i {_label(block)}"
            if cmd.confirmed
            else f"Tog tillbaka bekräftelsen av {_label(block)}"
        ),
        page_ids=[page.id],
        inverse=[{
            "command": "confirm_block",
            "page_id": page.id,
            "block_id": block.id,
            "confirmed": not cmd.confirmed,
        }],
    )


def _update_settings(site: Site, cmd: UpdateSettings, ctx: CommandContext) -> Applied:
    value = (cmd.value or "").strip()
    if cmd.field == "accent":
        allowed = ("koppar", "skog", "hav", "sten")
        if value not in allowed:
            raise CommandRefused(f"Färgtemat måste vara ett av: {', '.join(allowed)}.")
    if len(value) > 300:
        raise CommandRefused("Värdet är för långt (högst 300 tecken).")
    before = getattr(site.settings, cmd.field)
    if before == value:
        raise CommandRefused("Ingenting ändrades.")
    setattr(site.settings, cmd.field, value)
    return Applied(
        summary=f"Ändrade webbplatsens {cmd.field}",
        inverse=[{"command": "update_settings", "field": cmd.field, "value": before}],
    )


_HANDLERS: dict[str, Callable] = {
    "read_page": _read_page,
    "insert_block": _insert_block,
    "update_block": _update_block,
    "update_text": _update_text,
    "move_block": _move_block,
    "delete_block": _delete_block,
    "duplicate_block": _duplicate_block,
    "replace_image": _replace_image,
    "create_page": _create_page,
    "rename_page": _rename_page,
    "delete_page": _delete_page,
    "update_navigation": _update_navigation,
    "set_publish_window": _set_publish_window,
    "confirm_block": _confirm_block,
    "update_settings": _update_settings,
}


__all__ = [
    "AI_ALLOWED",
    "COMMAND_NAMES",
    "MAX_BLOCKS_PER_PAGE",
    "MAX_PAGES",
    "MUTATING",
    "Applied",
    "Command",
    "CommandContext",
    "CommandRefused",
    "apply_command",
    "parse_command",
    "parse_commands",
    "validate_props",
]
