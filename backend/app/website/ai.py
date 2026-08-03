"""The AI partner: a planner that emits commands, and nothing else.

What this module deliberately cannot do is as important as what it does. It has
no access to the DOM, produces no HTML, and never writes to the store. It reads
context, asks a model for a list of **commands**, and hands them to
:mod:`app.website.commands`, which validates and applies them exactly as it does
a command from a person dragging a section. Every rule the editor enforces is
therefore enforced against the model too, without either side knowing about the
other.

**Provider independence.** The only thing here that knows a model exists is
:func:`app.llm.pick_provider`, the same seam the answer pipeline uses, whose
contract is one method: ``complete(system, user, max_tokens=…, model=…) -> str``.
The command vocabulary is this product's, expressed as JSON in a prompt — not a
vendor's tool-calling schema, not the editor library's experimental AI hooks. A
different model, a different runtime, or no model at all (``BRF_LLM=none``,
which refuses rather than guesses) changes nothing below.

**Grounding.** When the model wants to write something the association's own
documents are the source for, it does not write it from memory: it names what it
needs, this module asks the ordinary retrieval-and-verification pipeline
(:func:`app.answer.ask`), and only the citations that pipeline *verified* are
attached to the block. If the pipeline refuses, so does the change. That is why
the AI partner in a document-grounded product can be trusted to write a page at
all — and it is enforced twice, here and again in
:mod:`app.website.grounding`, because a prompt is not a mechanism.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable

from ..answer import ask
from ..llm import LLMError, extract_json_object, pick_provider
from ..schemas import CitationOut
from ..store import Store
from .commands import AI_ALLOWED, COMMAND_NAMES, CommandRefused, parse_commands
from .components import AI_INSERTABLE, COMPONENTS
from .models import Site
from .sanitize import plain_text

logger = logging.getLogger("brf.website.ai")

MAX_OPERATIONS = 24
MAX_TOKENS = 2000
# How much of a page the model is shown. A BRF page is small; this is a guard
# against a pathological page rather than a routine truncation.
MAX_CONTEXT_BLOCKS = 40
MAX_PROP_CHARS = 400


@dataclass
class EditorContext:
    """What the operator is looking at when they type into the AI panel.

    This is what makes "korta den markerade texten" and "flytta detta under
    nyheterna" answerable at all: without it the model would have to guess which
    of eleven blocks "detta" refers to, and a guess that lands on the wrong
    block is a silent edit to the wrong part of a published page.
    """

    page_id: str = ""
    block_id: str = ""
    field: str = ""
    selected_text: str = ""

    def describe(self, site: Site) -> str:
        page = site.page(self.page_id) if self.page_id else None
        lines: list[str] = []
        if page:
            lines.append(f'Öppen sida: "{page.draft.title}" (page_id={page.id}, /{page.slug})')
        if self.block_id and page:
            block = next((b for b in page.draft.content if b.id == self.block_id), None)
            if block:
                spec = COMPONENTS.get(block.type)
                lines.append(
                    f"Markerat block: {spec.label if spec else block.type} "
                    f"(block_id={block.id}, type={block.type})"
                )
        if self.field:
            lines.append(f"Markerat fält: {self.field}")
        if self.selected_text.strip():
            lines.append(f'Markerad text: "{self.selected_text.strip()[:600]}"')
        if not lines:
            lines.append("Inget är markerat — instruktionen gäller sidan eller webbplatsen.")
        return "\n".join(lines)


@dataclass
class AiOutcome:
    """What one AI turn produced. Commands, not changes: nothing is applied here."""

    commands: list = field(default_factory=list)
    summary: str = ""
    message: str = ""
    refusal: str = ""
    sources: list[CitationOut] = field(default_factory=list)
    provider: str = ""
    model: str = ""


def _summarise_props(block_type: str, props: dict) -> dict:
    """A compact view of a block for the prompt.

    Rich text arrives as HTML and goes into the prompt as its readable text: the
    model is being asked to reason about what the page *says*, and feeding it
    markup wastes the window and invites it to answer in markup.
    """
    spec = COMPONENTS.get(block_type)
    if spec is None:
        return {}
    out: dict = {}
    for name, fspec in spec.fields.items():
        value = props.get(name)
        if fspec.kind == "richtext":
            out[name] = plain_text(str(value or ""))[:MAX_PROP_CHARS]
        elif fspec.kind == "list":
            rows = value or []
            out[name] = f"{len(rows)} poster" if len(rows) > 3 else rows
        elif isinstance(value, str):
            out[name] = value[:MAX_PROP_CHARS]
        else:
            out[name] = value
    return out


def build_context(site: Site, ctx: EditorContext) -> str:
    """Everything the model needs about the site, as text it can act on."""
    parts: list[str] = [ctx.describe(site)]

    page = site.page(ctx.page_id) if ctx.page_id else site.home_page()
    if page is not None:
        blocks = [
            {
                "block_id": b.id,
                "type": b.type,
                "props": _summarise_props(b.type, b.props),
            }
            for b in page.draft.content[:MAX_CONTEXT_BLOCKS]
        ]
        parts.append(
            "Sidans innehåll i ordning (page_id="
            + page.id
            + "):\n"
            + json.dumps(blocks, ensure_ascii=False, indent=1)
        )

    parts.append(
        "Sidor på webbplatsen: "
        + json.dumps(
            [
                {"page_id": p.id, "title": p.draft.title, "slug": p.slug, "startsida": p.home}
                for p in site.pages
            ],
            ensure_ascii=False,
        )
    )
    parts.append(
        "Menyn i ordning: "
        + json.dumps([item["label"] + f" (page_id={item['page_id']})" for item in site.navigation_public()], ensure_ascii=False)
    )
    return "\n\n".join(parts)


def _vocabulary_prompt() -> str:
    lines: list[str] = []
    for name, spec in sorted(COMPONENTS.items()):
        if name not in AI_INSERTABLE:
            continue
        fields = ", ".join(
            f"{fname} ({f.kind}"
            + (f": {'|'.join(f.option_values())}" if f.kind == 'select' else "")
            + ")"
            for fname, f in spec.fields.items()
        )
        lines.append(f"- {name} — {spec.label}: {spec.description}\n  fält: {fields}")
    return "\n".join(lines)


SYSTEM_PROMPT = """Du är redigeringsassistent i ett verktyg där en svensk bostadsrättsförening \
bygger sin egen webbplats. Du ändrar aldrig sidan själv: du föreslår operationer som \
programmet validerar och utför.

Svara ENDAST med ett JSON-objekt:
{"summary": "<kort svensk rubrik för ändringen>",
 "message": "<en eller två meningar till användaren>",
 "operations": [ ... ]}

Varje operation är ett objekt med fältet "command". Tillåtna kommandon:
%(commands)s

Blocktyper du får använda och deras fält:
%(components)s

Regler som gäller utan undantag:
1. Hitta aldrig på en blocktyp eller ett fält som inte står ovanför. Programmet vägrar dem.
2. Skriv aldrig en sakuppgift om föreningen — belopp, datum, avgifter, regler, tider — \
som du inte har fått i instruktionen. Behöver du en sådan uppgift ur föreningens egna \
dokument sätter du "grounded_from": "<frågan som besvarar det>" på operationen, så hämtar \
programmet uppgiften med källhänvisning. Kan den inte beläggas skrivs ingenting.
3. Text i richtext-fält skrivs som enkel HTML med <p>, <h2>-<h4>, <strong>, <em>, <ul>, \
<ol>, <li>, <blockquote>, <a href>. Inget annat.
4. Använd "after_block_id" när användaren beskriver en placering ("under nyheterna").
5. Ändrar du befintlig text, använd update_text med block_id och fältnamn.
6. Håll dig till vad som efterfrågades. Föreslå inte extra block ingen bett om.
7. Kan du inte göra det som efterfrågas: svara med tom "operations" och förklara i "message".

Skriv all text till användaren och all text på sidan på svenska."""


def _system() -> str:
    return SYSTEM_PROMPT % {
        "commands": "\n".join(f"- {name}" for name in COMMAND_NAMES if name in AI_ALLOWED),
        "components": _vocabulary_prompt(),
    }


def _ground(
    store: Store, query: str, *, trusted_names: Iterable[str]
) -> tuple[list[CitationOut], str]:
    """Ask the association's own documents. Returns (citations, refusal).

    The answer text is deliberately discarded. What the block needs is the
    *evidence* — the verified spans the grounding gate will check the model's
    prose against — and letting the retrieval answer become website copy would
    put an un-reviewed generated paragraph on a public page.
    """
    response = ask(store, query, trusted_names=trusted_names)
    if response.refusal:
        return [], (
            f"Föreningens dokument svarar inte på ”{query}”, så ingenting skrevs. "
            + (response.answer or "")
        ).strip()
    return list(response.citations), ""


def plan(
    store: Store,
    site: Site,
    instruction: str,
    *,
    ctx: EditorContext,
    trusted_names: Iterable[str] = (),
    provider=None,
) -> AiOutcome:
    """Turn one instruction into validated commands, grounding what needs it."""
    provider = provider or pick_provider()
    model = getattr(provider, "model", "") or store.settings.aiModel

    user = (
        f"{build_context(site, ctx)}\n\n"
        f"Användarens instruktion:\n{instruction.strip()}"
    )

    try:
        raw = provider.complete(_system(), user, max_tokens=MAX_TOKENS, model=model)
        payload = extract_json_object(raw)
    except LLMError as exc:
        logger.info("AI-planeringen gav inget användbart svar: %s", exc)
        return AiOutcome(
            refusal=(
                "AI-assistenten svarade med något som inte gick att tolka som ändringar. "
                "Ingenting skrevs. Försök formulera om."
            ),
            provider=provider.name,
            model=model,
        )

    operations = payload.get("operations")
    if not isinstance(operations, list):
        operations = []
    if len(operations) > MAX_OPERATIONS:
        return AiOutcome(
            refusal=(
                f"AI-assistenten föreslog {len(operations)} operationer, vilket är fler än "
                f"{MAX_OPERATIONS}. Ingenting skrevs — dela upp begäran i mindre steg."
            ),
            provider=provider.name,
            model=model,
        )

    # Grounding runs before validation and before anything is applied: an
    # operation that needs evidence either gets the verified citations or takes
    # the whole turn down with it. Half a page written from documents and half
    # from nothing would be the worst outcome available.
    collected: list[CitationOut] = []
    prepared: list[dict] = []
    for op in operations:
        if not isinstance(op, dict):
            return AiOutcome(
                refusal="AI-assistenten svarade med en operation som inte gick att läsa. Ingenting skrevs.",
                provider=provider.name,
                model=model,
            )
        op = dict(op)
        query = str(op.pop("grounded_from", "") or "").strip()
        if query:
            citations, refusal = _ground(store, query, trusted_names=trusted_names)
            if refusal:
                return AiOutcome(refusal=refusal, provider=provider.name, model=model)
            op["sources"] = [c.model_dump(mode="json") for c in citations]
            collected.extend(citations)
        prepared.append(op)

    try:
        commands = parse_commands(prepared)
    except CommandRefused as exc:
        # The model asked for something the vocabulary does not contain. Not an
        # error to log and swallow: the operator is told, in the same panel, that
        # nothing was written and why.
        return AiOutcome(
            refusal=f"AI-assistentens förslag gick inte att utföra: {exc}",
            provider=provider.name,
            model=model,
        )

    return AiOutcome(
        commands=commands,
        summary=str(payload.get("summary") or "AI-ändring").strip()[:120],
        message=str(payload.get("message") or "").strip()[:600],
        sources=collected,
        provider=provider.name,
        model=model,
    )


__all__ = ["AiOutcome", "EditorContext", "MAX_OPERATIONS", "build_context", "plan"]
