"""Per-document regulatory descriptions for ask-path selection.

Generated once per extracted-text version with the same local model that
answers questions. Cached on DocumentMeta. Regenerated only when the
extracted text actually changes; the previous description is kept beside
the new one. Not a summary of the text — what the document regulates.
"""

from __future__ import annotations

import hashlib
import json
import logging

from .llm import extract_json_object, pick_provider
from .schemas import DocumentMeta, PageData

logger = logging.getLogger("brf.document_describe")

_MAX_SOURCE_CHARS = 80_000
_FAKE_PROVIDERS = frozenset({"fake", "none"})


def content_fingerprint(pages: list[PageData]) -> str:
    digest = hashlib.sha256()
    for page in pages:
        for word in page.words:
            digest.update(word.text.encode("utf-8"))
            digest.update(b"\0")
        digest.update(b"\n")
    return digest.hexdigest()[:32]


def document_text_from_pages(pages: list[PageData]) -> str:
    parts: list[str] = []
    for page in pages:
        parts.append(" ".join(w.text for w in page.words))
    text = "\n".join(parts)
    if len(text) > _MAX_SOURCE_CHARS:
        return text[:_MAX_SOURCE_CHARS]
    return text


def description_prompt(title: str, text: str) -> tuple[str, str]:
    system = (
        "Du beskriver vad en föreningshandling reglerar. "
        "Skriv inte en sammanfattning av texten utan vad handlingen styr: "
        "vilka frågor den kan besvara, vilka parter och belopp den rör. "
        'Svara med JSON {"description": "..."} — 2–4 meningar på svenska.'
    )
    user = f"HANDLING: {title}\n\nINNEHÅLL:\n{text}"
    return system, user


def parse_description(raw: str) -> str:
    try:
        obj = extract_json_object(raw)
        desc = obj.get("description") if isinstance(obj, dict) else None
        if isinstance(desc, str) and desc.strip():
            return desc.strip()
    except Exception:
        pass
    cleaned = raw.strip()
    return cleaned[:800] if cleaned else ""


def generate_description(provider, title: str, text: str, *, model: str) -> str:
    system, user = description_prompt(title, text)
    raw = provider.complete(system, user, max_tokens=512, model=model)
    return parse_description(raw)


def _description_rows(documents: dict[str, DocumentMeta]) -> list[dict[str, str]]:
    return [
        {
            "id": meta.id,
            "name": meta.name,
            "description": meta.description or "",
        }
        for meta in sorted(
            documents.values(),
            key=lambda m: (m.name.casefold(), m.name, m.id),
        )
    ]


def description_set_version(documents: dict[str, DocumentMeta]) -> str:
    """Stable id of the description texts currently on the documents."""
    blob = json.dumps(
        [(row["name"], row["description"]) for row in _description_rows(documents)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def snapshot_description_lock(store) -> dict:
    rows = _description_rows(store.documents)
    fps = {meta.id: meta.description_fp or "" for meta in store.documents.values()}
    return {
        "version": description_set_version(store.documents),
        "documents": [{**row, "description_fp": fps.get(row["id"], "")} for row in rows],
    }


def freeze_descriptions(store) -> str:
    """Pin fingerprints to current extracted text and refuse regeneration.

    Eval uses this so a measurement records a version and cannot rewrite
    descriptions mid-run. Product ask() does not freeze — it regenerates
    only when the fingerprint of extracted text changes.
    """
    with store.lock:
        for doc_id, meta in list(store.documents.items()):
            pages = store.pages.get(doc_id)
            if not meta.description or pages is None:
                continue
            fp = content_fingerprint(pages)
            if meta.description_fp != fp:
                store.documents[doc_id] = meta.model_copy(update={"description_fp": fp})
        store._descriptions_frozen = True
        version = description_set_version(store.documents)
    logger.info("beskrivningar låsta version=%s n=%s", version, len(store.documents))
    return version


def apply_description_lock(store, payload: dict) -> str:
    """Install a versioned description set and freeze it for the process."""
    by_id = {entry["id"]: entry for entry in payload["documents"]}
    by_name = {entry["name"]: entry for entry in payload["documents"]}
    with store.lock:
        for doc_id, meta in list(store.documents.items()):
            entry = by_id.get(doc_id) or by_name.get(meta.name)
            if entry is None or not entry.get("description"):
                continue
            pages = store.pages.get(doc_id)
            fp = content_fingerprint(pages) if pages is not None else meta.description_fp
            store.documents[doc_id] = meta.model_copy(
                update={
                    "description": entry["description"],
                    "description_fp": fp,
                }
            )
        store._descriptions_frozen = True
        version = description_set_version(store.documents)
    logger.info(
        "beskrivningslås applicerat version=%s lock_version=%s n=%s",
        version,
        payload.get("version"),
        len(payload.get("documents") or []),
    )
    return version


def refresh_document_description(store, doc_id: str, provider=None) -> None:
    """Write a cached description when missing or the extracted text changed.

    Never raises: ingestion must not fail because a description could not be
    produced. Fake/none providers skip — tests do not talk to a model.
    Frozen stores (eval) keep the installed text even if the fingerprint
    no longer matches.
    """
    provider = provider or pick_provider()
    if provider.name in _FAKE_PROVIDERS:
        return
    with store.lock:
        meta = store.documents.get(doc_id)
        pages = store.pages.get(doc_id)
        if meta is None or pages is None:
            return
        fp = content_fingerprint(pages)
        if meta.description and meta.description_fp == fp:
            return
        if getattr(store, "_descriptions_frozen", False) and meta.description:
            logger.info("beskrivning låst, hoppar över omskrivning document=%s", doc_id)
            return
        title = meta.name
        previous = meta.description
        text = document_text_from_pages(pages)
        model = getattr(provider, "model", "") or store.settings.aiModel
    try:
        desc = generate_description(provider, title, text, model=model)
    except Exception:
        logger.exception("beskrivning misslyckades för %s (%s)", doc_id, title)
        return
    if not desc:
        logger.warning("tom beskrivning för %s (%s)", doc_id, title)
        return
    with store.lock:
        current = store.documents.get(doc_id)
        if current is None:
            return
        update = {"description": desc, "description_fp": fp}
        if previous:
            update["description_previous"] = previous
            logger.info(
                "beskrivning omskriven document=%s title=%s old_chars=%s new_chars=%s fp=%s",
                doc_id,
                title,
                len(previous),
                len(desc),
                fp,
            )
        else:
            logger.info("beskrivning sparad document=%s chars=%s", doc_id, len(desc))
        store.documents[doc_id] = current.model_copy(update=update)
        store._save_documents()


def ensure_descriptions(store, provider) -> None:
    if provider.name in _FAKE_PROVIDERS:
        return
    for doc_id in list(store.documents):
        refresh_document_description(store, doc_id, provider)


def described_documents(documents: dict[str, DocumentMeta]) -> list[DocumentMeta]:
    return [
        meta
        for meta in sorted(documents.values(), key=lambda m: (m.name.casefold(), m.name, m.id))
        if meta.description
    ]
