"""Measurement helpers for document-level doc2query and query2doc.

Not on the product ask path. BM25 here is one post per document with the
same tokenizer as the hybrid index, and without query-side expansion.
"""

from __future__ import annotations

import re

from app.indexer import BM25, tokenize
from app.llm import extract_json_object

QUERY2DOC_REPEATS = 5
DOC2QUERY_N = 20


def parse_questions(raw: str) -> list[str]:
    try:
        obj = extract_json_object(raw)
    except Exception:
        obj = {}
    items = obj.get("questions") if isinstance(obj, dict) else None
    out: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str) and item.strip() and item.strip() not in out:
                out.append(item.strip())
    return out


def parse_passage(raw: str) -> str:
    try:
        obj = extract_json_object(raw)
        passage = obj.get("passage") if isinstance(obj, dict) else None
        if isinstance(passage, str) and passage.strip():
            return passage.strip()
    except Exception:
        pass
    return raw.strip()


def concatenate_query2doc(
    question: str,
    passage: str,
    *,
    repeats: int = QUERY2DOC_REPEATS,
) -> str:
    query = " ".join(question.split())
    body = " ".join(passage.split())
    return " ".join([query] * repeats + [body])


def expand_document_text(text: str, questions: list[str]) -> str:
    extra = [q.strip() for q in questions if q.strip()]
    if not extra:
        return text
    return text.rstrip() + "\n" + "\n".join(extra)


def doc2query_prompt(text: str, *, n: int = DOC2QUERY_N) -> tuple[str, str]:
    system = (
        "Du skriver frågor som en styrelseledamot skulle kunna ställa. "
        "Frågorna ska kunna besvaras av just den här handlingen. "
        "Använd vardagliga ord, inte handlingens juridiska termer. "
        f'Svara med JSON {{"questions": ["...", ...]}} — exakt {n} frågor på svenska.'
    )
    return system, f"INNEHÅLL:\n{text}"


def query2doc_prompt(question: str) -> tuple[str, str]:
    system = (
        "Du skriver ett kort stycke på svenska som skulle kunna stå i handlingen "
        "som besvarar frågan. Du svarar inte som assistent. Du ber inte om förtydligande."
    )
    user = (
        "Skriv ett kort hypotetiskt svarsstycke på frågan.\n"
        f"Fråga: {question}\n"
        'Svara med JSON {"passage": "..."}.'
    )
    return system, user


def isolated_selection_prompt(
    entries: list[tuple[str, str]],
    question: str,
) -> tuple[str, str]:
    system = (
        "Du väljer vilken handling som kan besvara frågan. "
        "Välj exakt en handling. Du svarar inte på frågan. Du citerar inte. "
        'Svara med JSON {"document": "X"} där X är en bokstav ur listan.'
    )
    lines = ["HANDLINGAR:"]
    for letter, description in entries:
        lines.append(f"{letter}. {description}")
    lines.append("")
    lines.append(f"FRÅGA: {question}")
    return system, "\n".join(lines)


def parse_selected_document(raw: str, valid: set[str]) -> str | None:
    try:
        obj = extract_json_object(raw)
    except Exception:
        obj = {}
    if isinstance(obj, dict):
        single = obj.get("document")
        if isinstance(single, str):
            letter = single.strip().upper()
            if letter in valid:
                return letter
        docs = obj.get("documents")
        if isinstance(docs, str):
            docs = [docs]
        if isinstance(docs, list):
            for item in docs:
                if not isinstance(item, str):
                    continue
                letter = item.strip().upper()
                if letter in valid:
                    return letter
    for letter in re.findall(r"\b([A-Z])\b", raw.upper()):
        if letter in valid:
            return letter
    return None


def fit_document_bm25(texts: list[str]) -> BM25:
    bm25 = BM25()
    bm25.fit([tokenize(t) for t in texts])
    return bm25


def rank_letters(bm25: BM25, query: str, letters: list[str]) -> list[str]:
    scores = bm25.scores(tokenize(query))
    order = sorted(range(len(letters)), key=lambda i: (-scores[i], i))
    return [letters[i] for i in order]


def index_growth(before: list[str], after: list[str]) -> dict:
    rows = []
    tokens_before = 0
    tokens_after = 0
    for i, (old, new) in enumerate(zip(before, after, strict=True)):
        n_before = len(tokenize(old))
        n_after = len(tokenize(new))
        tokens_before += n_before
        tokens_after += n_after
        rows.append(
            {
                "index": i,
                "tokens_before": n_before,
                "tokens_after": n_after,
                "tokens_added": n_after - n_before,
            }
        )
    return {
        "n_documents": len(before),
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "tokens_added": tokens_after - tokens_before,
        "per_document": rows,
    }


def token_contains(text: str, term: str) -> bool:
    needles = tokenize(term)
    if not needles:
        return False
    hay = set(tokenize(text))
    return all(token in hay for token in needles)


FOUR_ANGLE_KEYS = ("reglerar", "fragor", "parter", "belopp")


def union_case(case_id: str, gold: str, pick_old: str | None, pick_new: str | None) -> dict:
    hit_old = pick_old == gold
    hit_new = pick_new == gold
    return {
        "id": case_id,
        "gold": gold,
        "old": pick_old,
        "new": pick_new,
        "hit_old": hit_old,
        "hit_new": hit_new,
        "hit_union": hit_old or hit_new,
    }


def union_summary(rows: list[dict]) -> dict:
    return {
        "old": sum(1 for row in rows if row["hit_old"]),
        "new": sum(1 for row in rows if row["hit_new"]),
        "union": sum(1 for row in rows if row["hit_union"]),
        "n": len(rows),
    }


def four_angle_prompt(text: str) -> tuple[str, str]:
    system = (
        "Du skriver fyra korta beskrivningar av samma handling, från olika håll. "
        "Inte en sammanfattning. Fyra skilda texter på svenska: "
        "vad handlingen reglerar, vilka frågor den kan besvara, vilka parter den rör, "
        "och vilka pengar eller belopp den handlar om. "
        'Svara med JSON {"reglerar": "...", "fragor": "...", "parter": "...", "belopp": "..."}. '
        "En till tre meningar per fält."
    )
    return system, f"INNEHÅLL:\n{text}"


def parse_four_angles(raw: str) -> dict[str, str]:
    try:
        obj = extract_json_object(raw)
    except Exception:
        obj = {}
    if not isinstance(obj, dict):
        obj = {}
    aliases = {
        "reglerar": ("reglerar",),
        "fragor": ("fragor", "frågor"),
        "parter": ("parter",),
        "belopp": ("belopp", "pengar"),
    }
    out: dict[str, str] = {}
    for key in FOUR_ANGLE_KEYS:
        value = ""
        for name in aliases[key]:
            raw_value = obj.get(name)
            if isinstance(raw_value, str) and raw_value.strip():
                value = raw_value.strip()
                break
        out[key] = value
    return out


def format_four_angle_entry(letter: str, angles: dict[str, str]) -> str:
    lines = [
        f"{letter}. Vad den reglerar: {angles.get('reglerar', '').strip()}",
        f"   Frågor den kan besvara: {angles.get('fragor', '').strip()}",
        f"   Parter: {angles.get('parter', '').strip()}",
        f"   Belopp: {angles.get('belopp', '').strip()}",
    ]
    return "\n".join(lines)


def four_angle_selection_prompt(
    entries: list[tuple[str, dict[str, str]]],
    question: str,
) -> tuple[str, str]:
    system = (
        "Du väljer vilken handling som kan besvara frågan. "
        "Välj exakt en handling. Du svarar inte på frågan. Du citerar inte. "
        'Svara med JSON {"document": "X"} där X är en bokstav ur listan.'
    )
    lines = ["HANDLINGAR:"]
    for letter, angles in entries:
        lines.append(format_four_angle_entry(letter, angles))
        lines.append("")
    lines.append(f"FRÅGA: {question}")
    return system, "\n".join(lines)


def view_reglerar_prompt(text: str) -> tuple[str, str]:
    system = (
        "Du skriver en fristående beskrivning av vad handlingen reglerar. "
        "Skyldigheter, villkor, vad den styr. Inte en sammanfattning. "
        "Inte en lista med vardagsfrågor. "
        'Svara med JSON {"description": "..."} — 2–4 meningar på svenska.'
    )
    return system, f"INNEHÅLL:\n{text}"


def view_fragor_prompt(text: str) -> tuple[str, str]:
    system = (
        "Du skriver en fristående beskrivning av vilka frågor en styrelseledamot "
        "skulle kunna ställa till just den här handlingen. "
        "Använd vardagliga ord, inte handlingens juridiska termer. "
        "Inte vad handlingen reglerar i avtalspråk. "
        'Svara med JSON {"description": "..."} — 2–4 meningar på svenska.'
    )
    return system, f"INNEHÅLL:\n{text}"


def overlay_descriptions(documents: dict, texts: dict[str, str]) -> dict:
    out = {}
    for doc_id, meta in documents.items():
        if doc_id in texts:
            out[doc_id] = meta.model_copy(update={"description": texts[doc_id]})
        else:
            out[doc_id] = meta
    return out


def union_selected_ids(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    for item in [*first, *second]:
        if item and item not in out:
            out.append(item)
    return out


def gold_in_package(gold: str, packed: list[str]) -> bool:
    return gold in packed


def picks_hit_ids(picks: dict[str, str | None], gold_by_id: dict[str, str]) -> set[str]:
    return {case_id for case_id, gold in gold_by_id.items() if picks.get(case_id) == gold}


def per_set_hit_counts(
    sets: list[dict[str, str | None]],
    gold_by_id: dict[str, str],
) -> list[int]:
    return [len(picks_hit_ids(picks, gold_by_id)) for picks in sets]


def cumulative_union_counts(
    sets: list[dict[str, str | None]],
    gold_by_id: dict[str, str],
) -> list[int]:
    acc: set[str] = set()
    out: list[int] = []
    for picks in sets:
        acc |= picks_hit_ids(picks, gold_by_id)
        out.append(len(acc))
    return out


def hit_spread(counts: list[int]) -> dict:
    return {
        "min": min(counts),
        "max": max(counts),
        "span": max(counts) - min(counts),
        "values": list(counts),
    }


def unique_text_counts(sets: list[dict[str, str]]) -> dict[str, int]:
    by_key: dict[str, set[str]] = {}
    for texts in sets:
        for key, text in texts.items():
            by_key.setdefault(key, set()).add(text)
    return {key: len(values) for key, values in by_key.items()}
