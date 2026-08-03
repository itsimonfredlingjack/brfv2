"""The component vocabulary a BRF website is built out of — and its limits.

This module is the *authority* on what a page may contain. Not the editor, not
the model, not the frontend: those all render or propose, and every one of them
is checked against what is written here before anything is stored.

That inversion is the whole point of the feature. A website builder that
accepts generated HTML can produce a page nobody reviewed, in a layout nobody
designed, making a claim nobody can trace. This one cannot express such a page:
there is no ``html`` block, no ``custom`` escape hatch and no free-form style
field. A block is one of the types below, its props are the fields declared for
that type, and a value that does not fit its field is refused — identically
whether a person dragged it or a model asked for it.

**The mirror.** ``brfv2-mockup/src/components/website/websiteConfig.jsx``
declares the same components again, in React, because the editor and the public
renderer need something to draw. Two declarations of one vocabulary is exactly
the kind of pair that drifts, so it is locked: :mod:`app.website.vocabulary`
writes ``VOCABULARY.lock.json`` from *this* file, a backend test fails when the
lock no longer matches, and a frontend test fails when the React config no
longer matches the lock. Changing a component means changing both sides and
re-recording the lock deliberately — the same discipline as
``app.invoices.RULES.lock.json``.

**Swedish labels, English identifiers.** Component and field *ids* are English
because they are code and appear in stored JSON; every label a board member
reads is Swedish, and comes from here so the editor, the AI panel and the
backend's refusals all name a thing the same way.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Field kinds. Deliberately few: every additional kind is another shape the
# editor, the renderer, the validator and the model all have to agree about.
#
# - text      one line, edited inline in the canvas
# - textarea  short unformatted prose (a preamble)
# - richtext  Tiptap HTML, the only field where formatting is allowed at all,
#             and even there only the marks app.website.richtext permits
# - select    one of a declared set of options (variants, alignment)
# - image     an image reference plus its alt text — alt is not optional
# - link      a label and a destination, validated against app.website.links
# - date      ISO ÅÅÅÅ-MM-DD
# - list      an ordered array of objects with their own declared subfields
# - document  a reference to one of the association's own indexed documents
FieldKind = Literal[
    "text", "textarea", "richtext", "select", "image", "link", "date", "list", "document"
]

# Which field kinds carry prose a human reads as a factual claim. The grounding
# gate (app.website.grounding) inspects exactly these when a model wrote them,
# and ignores the rest: a variant name or an image id cannot fabricate a fact,
# and running a numeric check over them would only produce false refusals.
CLAIM_BEARING: frozenset[str] = frozenset({"text", "textarea", "richtext", "list"})


class FieldSpec(BaseModel):
    """One editable value on a block."""

    kind: FieldKind
    label: str
    # Shown in the editor's floating panel under the input. Kept short: it is a
    # hint, not documentation.
    help: str = ""
    required: bool = False
    max_length: int = 0  # 0 = no explicit cap beyond the global one
    options: list[dict] = Field(default_factory=list)  # select: [{value, label}]
    fields: dict[str, "FieldSpec"] = Field(default_factory=dict)  # list: subfields
    max_items: int = 0  # list only
    # Inline-editable in the canvas rather than only in the panel. Headings and
    # button labels are; a select is not.
    inline: bool = False

    def option_values(self) -> tuple[str, ...]:
        return tuple(str(o["value"]) for o in self.options)


class ComponentSpec(BaseModel):
    """One block type."""

    label: str  # Swedish, shown in the editor and in AI summaries
    description: str  # what a board would use it for, one sentence
    category: Literal["innehåll", "information", "kontakt", "förening"]
    fields: dict[str, FieldSpec]
    defaults: dict = Field(default_factory=dict)
    # A block a page should not carry twice (a second hero is a mistake, a
    # second news list is not). Advisory to the editor, enforced on insert.
    singleton: bool = False


def _t(label: str, *, inline: bool = True, required: bool = False, max_length: int = 200, help: str = "") -> FieldSpec:
    return FieldSpec(kind="text", label=label, inline=inline, required=required, max_length=max_length, help=help)


def _rt(label: str, *, help: str = "") -> FieldSpec:
    return FieldSpec(kind="richtext", label=label, help=help)


def _sel(label: str, options: list[tuple[str, str]], *, help: str = "") -> FieldSpec:
    return FieldSpec(
        kind="select",
        label=label,
        help=help,
        options=[{"value": v, "label": la} for v, la in options],
    )


TONE_OPTIONS = [
    ("info", "Information"),
    ("warning", "Viktigt"),
    ("critical", "Akut"),
]


COMPONENTS: dict[str, ComponentSpec] = {
    # ---------- innehåll ----------
    "Hero": ComponentSpec(
        label="Toppsektion",
        description="Sidans första intryck: föreningens namn, en kort rad och en väg vidare.",
        category="innehåll",
        singleton=True,
        fields={
            "heading": _t("Rubrik", required=True, max_length=120),
            "preamble": FieldSpec(
                kind="textarea", label="Ingress", max_length=320,
                help="En eller två meningar. Längre text hör hemma i ett textblock.",
            ),
            "image": FieldSpec(kind="image", label="Bild"),
            "action": FieldSpec(kind="link", label="Knapp", help="Lämna tom för ingen knapp."),
            "variant": _sel("Utseende", [
                ("image", "Med bild"),
                ("plain", "Utan bild"),
                ("compact", "Låg"),
            ]),
        },
        defaults={
            "heading": "Välkommen till föreningen",
            "preamble": "",
            "variant": "image",
            "image": {"src": "", "alt": ""},
            "action": {"label": "", "href": ""},
        },
    ),
    "TextSection": ComponentSpec(
        label="Text",
        description="Löpande text med rubrik — det vanligaste blocket på en föreningssida.",
        category="innehåll",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "body": _rt("Text"),
            "width": _sel("Bredd", [("normal", "Normal"), ("narrow", "Smal"), ("wide", "Bred")]),
        },
        defaults={"heading": "Rubrik", "body": "<p>Skriv här.</p>", "width": "normal"},
    ),
    "ImageWithText": ComponentSpec(
        label="Bild och text",
        description="En bild bredvid en text, för presentationer av huset, gården eller ett projekt.",
        category="innehåll",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "body": _rt("Text"),
            "image": FieldSpec(kind="image", label="Bild", required=True),
            "side": _sel("Bildens placering", [("left", "Vänster"), ("right", "Höger")]),
        },
        defaults={
            "heading": "Rubrik",
            "body": "<p>Skriv här.</p>",
            "image": {"src": "", "alt": ""},
            "side": "left",
        },
    ),

    # ---------- information ----------
    "ImportantNotice": ComponentSpec(
        label="Viktigt meddelande",
        description="Något de boende behöver veta nu: avstängt vatten, ett stambyte, en portkod.",
        category="information",
        fields={
            "heading": _t("Rubrik", required=True, max_length=120),
            "body": _rt("Meddelande"),
            "tone": _sel("Allvarsgrad", TONE_OPTIONS),
            "valid_until": FieldSpec(
                kind="date", label="Gäller till och med",
                help="Efter det här datumet visas meddelandet inte på den publicerade sidan.",
            ),
        },
        defaults={"heading": "Viktigt meddelande", "body": "<p></p>", "tone": "info", "valid_until": ""},
    ),
    "NewsList": ComponentSpec(
        label="Nyheter",
        description="Korta notiser i datumordning, senast först.",
        category="information",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "items": FieldSpec(
                kind="list", label="Nyheter", max_items=24,
                fields={
                    "date": FieldSpec(kind="date", label="Datum", required=True),
                    "title": _t("Rubrik", required=True, max_length=160),
                    "body": _rt("Text"),
                },
            ),
        },
        defaults={"heading": "Nyheter", "items": []},
    ),
    "Calendar": ComponentSpec(
        label="Kalender",
        description="Kommande datum: stämma, städdag, container på gården.",
        category="information",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "events": FieldSpec(
                kind="list", label="Händelser", max_items=36,
                fields={
                    "date": FieldSpec(kind="date", label="Datum", required=True),
                    "title": _t("Vad", required=True, max_length=160),
                    "place": _t("Var", max_length=120),
                    "note": _t("Kommentar", inline=False, max_length=240),
                },
            ),
        },
        defaults={"heading": "Kalender", "events": []},
    ),
    "Faq": ComponentSpec(
        label="Frågor och svar",
        description="Det de boende frågar om ändå — hopfällbart, så sidan inte blir en vägg av text.",
        category="information",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "items": FieldSpec(
                kind="list", label="Frågor", max_items=40,
                fields={
                    "question": _t("Fråga", required=True, max_length=200),
                    "answer": _rt("Svar"),
                },
            ),
        },
        defaults={"heading": "Frågor och svar", "items": []},
    ),
    "ProjectStatus": ComponentSpec(
        label="Projektstatus",
        description="Var ett pågående arbete står, steg för steg — det stambytet får flest frågor.",
        category="information",
        fields={
            "heading": _t("Rubrik", required=True, max_length=120),
            "body": _rt("Beskrivning"),
            "steps": FieldSpec(
                kind="list", label="Steg", max_items=12,
                fields={
                    "label": _t("Steg", required=True, max_length=120),
                    "state": _sel("Läge", [
                        ("done", "Klart"),
                        ("ongoing", "Pågår"),
                        ("planned", "Planerat"),
                    ]),
                    "note": _t("Kommentar", inline=False, max_length=200),
                },
            ),
        },
        defaults={"heading": "Projektstatus", "body": "<p></p>", "steps": []},
    ),

    # ---------- kontakt ----------
    "ContactCard": ComponentSpec(
        label="Kontakt",
        description="Vem man når, och hur. Styrelsen, förvaltaren, felanmälan.",
        category="kontakt",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "intro": FieldSpec(kind="textarea", label="Ingress", max_length=320),
            "entries": FieldSpec(
                kind="list", label="Kontakter", max_items=12,
                fields={
                    "role": _t("Roll", required=True, max_length=120),
                    "name": _t("Namn", max_length=120),
                    "email": _t("E-post", inline=False, max_length=160),
                    "phone": _t("Telefon", inline=False, max_length=60),
                },
            ),
        },
        defaults={"heading": "Kontakt", "intro": "", "entries": []},
    ),
    "FaultReport": ComponentSpec(
        label="Felanmälan",
        description="Vägen in när något är trasigt, med jouren tydligt skild från det som kan vänta.",
        category="kontakt",
        singleton=True,
        fields={
            "heading": _t("Rubrik", required=True, max_length=120),
            "body": _rt("Så här gör du"),
            "phone": _t("Telefon dagtid", inline=False, max_length=60),
            "email": _t("E-post", inline=False, max_length=160),
            "emergency_phone": _t("Jour (akut)", inline=False, max_length=60),
            "emergency_note": _t("När jouren gäller", inline=False, max_length=200),
            "action": FieldSpec(kind="link", label="Knapp"),
        },
        defaults={
            "heading": "Felanmälan",
            "body": "<p></p>",
            "phone": "",
            "email": "",
            "emergency_phone": "",
            "emergency_note": "",
            "action": {"label": "", "href": ""},
        },
    ),

    # ---------- förening ----------
    "DocumentList": ComponentSpec(
        label="Dokument",
        description=(
            "Föreningens egna handlingar — stadgar, årsredovisning, protokoll — hämtade "
            "ur arkivet och inte uppladdade en gång till."
        ),
        category="förening",
        fields={
            "heading": _t("Rubrik", max_length=120),
            "intro": FieldSpec(kind="textarea", label="Ingress", max_length=320),
            "documents": FieldSpec(
                kind="list", label="Dokument", max_items=40,
                fields={
                    "document_id": FieldSpec(kind="document", label="Dokument", required=True),
                    "label": _t("Visas som", max_length=160,
                                help="Lämna tomt för dokumentets eget namn."),
                },
            ),
        },
        defaults={"heading": "Dokument", "intro": "", "documents": []},
    ),
}

# What a model is allowed to insert. Identical to the full set today, and a
# separate name on purpose: the day a component appears that only an
# administrator should place (an embed, a payment link), removing it from here
# is a one-line change with a test behind it, rather than a prompt instruction
# nobody can verify.
AI_INSERTABLE: frozenset[str] = frozenset(COMPONENTS)

CATEGORY_ORDER: tuple[str, ...] = ("innehåll", "information", "kontakt", "förening")


class UnknownComponent(ValueError):
    """A block type that is not in this vocabulary."""


class UnknownField(ValueError):
    """A prop that the block's type does not declare."""


def spec_for(component_type: str) -> ComponentSpec:
    spec = COMPONENTS.get(component_type)
    if spec is None:
        raise UnknownComponent(
            f"Okänd blocktyp {component_type!r}. Tillåtna: {', '.join(sorted(COMPONENTS))}."
        )
    return spec


def field_for(component_type: str, field_name: str) -> FieldSpec:
    spec = spec_for(component_type)
    field = spec.fields.get(field_name)
    if field is None:
        raise UnknownField(
            f"Blocktypen {spec.label} ({component_type}) har inget fält {field_name!r}. "
            f"Fält: {', '.join(sorted(spec.fields))}."
        )
    return field


def vocabulary() -> dict:
    """The whole vocabulary as plain JSON.

    Serves three readers that must not be allowed to disagree: the editor (which
    builds its panels from it), the model (which is told what it may ask for),
    and ``VOCABULARY.lock.json`` (which fails the build when either drifts).
    """
    return {
        "categories": list(CATEGORY_ORDER),
        "components": {
            name: {
                **spec.model_dump(mode="json"),
                "ai_insertable": name in AI_INSERTABLE,
            }
            for name, spec in sorted(COMPONENTS.items())
        },
    }


__all__ = [
    "AI_INSERTABLE",
    "CATEGORY_ORDER",
    "CLAIM_BEARING",
    "COMPONENTS",
    "ComponentSpec",
    "FieldSpec",
    "UnknownComponent",
    "UnknownField",
    "field_for",
    "spec_for",
    "vocabulary",
]
