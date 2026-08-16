"""Per-document regulatory descriptions for ask-path selection.

Generated at ingestion (and when extracted text changes) with the same local
model that answers questions. Cached on DocumentMeta. Not a summary of the
text — what the document regulates.
"""

from __future__ import annotations

import hashlib
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


def refresh_document_description(store, doc_id: str, provider=None) -> None:
    """Write a cached description when missing or the extracted text changed.

    Never raises: ingestion must not fail because a description could not be
    produced. Fake/none providers skip — tests do not talk to a model.
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
        title = meta.name
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
        store.documents[doc_id] = current.model_copy(
            update={"description": desc, "description_fp": fp}
        )
        store._save_documents()
        logger.info("beskrivning sparad document=%s chars=%s", doc_id, len(desc))


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
