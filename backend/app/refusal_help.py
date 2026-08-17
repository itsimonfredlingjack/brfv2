"""Turn an insufficient_data refusal into a three-part answer.

Each clause is either known from this request or marked as a general
statement about the world. The module does not invent a list of documents
an association ought to have, and it does not touch citation verification,
document selection, or the answer judge.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from .document_ask import catalog_entries
from .llm import extract_json_object
from .schemas import DocumentMeta, RetrievalHit

logger = logging.getLogger("brf.refusal_help")

KIND_SYSTEM = (
    "Du säger vilken sorts handling som brukar reglera en fråga. "
    "Du uttalar dig allmänt om världen, inte om en viss förening. "
    "Du hittar inte på en lista över handlingar som borde finnas. "
    "Du svarar inte på frågan. "
    'Svara med JSON {"kind": "..."} där kind är en kort svensk fras '
    'för handlingssorten, till exempel "ett hyresavtal för parkering" '
    'eller "en årsredovisning". Tom sträng om du inte vet.'
)

MATCH_SYSTEM = (
    "Du matchar en handlingssort mot beskrivningar. "
    "Du påstår inte att någon handling innehåller svaret. "
    "Du hittar inte på en lista över handlingar som borde finnas. "
    'Svara med JSON {"matches": ["A", ...]} med bokstäver ur listan, '
    "eller en tom lista."
)

KIND_MAX_TOKENS = 128
MATCH_MAX_TOKENS = 128

_STOP = frozenset(
    {
        "avtal",
        "avtalet",
        "handling",
        "handlingen",
        "mellan",
        "samt",
        "output",
        "under",
        "enligt",
        "genom",
        "dessa",
        "detta",
        "denna",
        "eller",
        "efter",
        "innan",
    }
)


def join_sv(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " och " + items[-1]


def compose_refusal_answer(
    *,
    read_names: list[str],
    kind: str | None,
    matching_names: list[str],
    match_known: bool = True,
) -> str:
    parts: list[str] = []
    if read_names:
        parts.append(f"Jag läste {join_sv(read_names)}.")
    else:
        parts.append("Jag läste inga handlingar.")
    parts.append("Svaret står inte i dem.")
    kind_text = (kind or "").strip()
    if kind_text:
        parts.append(f"Allmänt brukar en sådan fråga regleras i {kind_text}.")
        if matching_names:
            parts.append(
                "I arkivet finns handlingar som beskrivs som den sorten: "
                f"{join_sv(matching_names)}."
            )
        elif match_known:
            parts.append(
                "Ingen handling av den sorten finns bland de beskrivna "
                "handlingarna i arkivet."
            )
    return " ".join(parts)


def kind_prompt(question: str) -> tuple[str, str]:
    return KIND_SYSTEM, f"FRÅGA: {question.strip()}"


def match_prompt(kind: str, catalog: list[tuple[str, str, str]]) -> tuple[str, str]:
    lines = [f"HANDLINGSSORT: {kind}", "", "BESKRIVNA HANDLINGAR:"]
    for letter, name, description in catalog:
        lines.append(f"{letter}. {name} — {description}")
    return MATCH_SYSTEM, "\n".join(lines)


def parse_kind(raw: str) -> str:
    try:
        obj = extract_json_object(raw)
    except Exception:
        return ""
    kind = obj.get("kind") if isinstance(obj, dict) else None
    if not isinstance(kind, str):
        return ""
    cleaned = " ".join(kind.split())
    if len(cleaned) > 160:
        return cleaned[:160].rstrip()
    return cleaned


def parse_matches(raw: str, valid: set[str]) -> list[str]:
    try:
        obj = extract_json_object(raw)
    except Exception:
        return []
    items = obj.get("matches") if isinstance(obj, dict) else None
    if isinstance(items, str):
        items = [items]
    out: list[str] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, str):
                continue
            letter = item.strip().upper()
            if letter in valid and letter not in out:
                out.append(letter)
    return out


def read_document_names(hits: list[RetrievalHit]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        name = hit.document_name
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def distinctive_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[0-9a-zåäö]+", _fold(text))
    return {token for token in tokens if len(token) >= 5 and token not in _STOP}


def extract_kind_clause(answer: str) -> str | None:
    m = re.search(r"Allmänt brukar en sådan fråga regleras i (.+?)\.(?: |\Z)", answer)
    return m.group(1) if m else None


def names_gold_kind(text: str, gold_name: str, gold_description: str = "") -> bool:
    hay = _fold(text)
    needles = distinctive_tokens(gold_name)
    if gold_description:
        needles |= {token for token in distinctive_tokens(gold_description) if len(token) >= 8}
    return any(needle in hay for needle in needles)


def enrich_insufficient_refusal(
    *,
    question: str,
    hits: list[RetrievalHit],
    documents: dict[str, DocumentMeta],
    provider,
    model: str,
) -> str:
    read_names = read_document_names(hits)
    kind = ""
    try:
        system, user = kind_prompt(question)
        raw = provider.complete(system, user, max_tokens=KIND_MAX_TOKENS, model=model)
        kind = parse_kind(raw)
    except Exception as exc:
        logger.warning("vägran: handlingssort misslyckades: %s", exc)
        kind = ""

    matching_names: list[str] = []
    match_known = True
    if kind:
        catalog = [
            (letter, meta.name, meta.description or "")
            for letter, meta in catalog_entries(documents)
        ]
        if catalog:
            try:
                system, user = match_prompt(kind, catalog)
                raw = provider.complete(
                    system, user, max_tokens=MATCH_MAX_TOKENS, model=model
                )
                letters = parse_matches(raw, {row[0] for row in catalog})
                by_letter = {row[0]: row[1] for row in catalog}
                matching_names = [by_letter[letter] for letter in letters if letter in by_letter]
            except Exception as exc:
                logger.warning("vägran: matchning mot beskrivningar misslyckades: %s", exc)
                match_known = False
        else:
            matching_names = []

    return compose_refusal_answer(
        read_names=read_names,
        kind=kind,
        matching_names=matching_names,
        match_known=match_known,
    )
