"""RAG orchestration: retrieve → generate → verify → resolve → respond.

Two refusal gates before and after the LLM (SPEC §2.9), plus the grounding
gate (§2.1): answers whose every citation fails verification are refused when
requireSources is on.
"""

from __future__ import annotations

import logging

from .citations import Rejected, Resolved, resolve_quote
from .llm import LLMError, LLMFormatError, LLMProvider, parse_llm_json, pick_provider
from .schemas import AskResponse, CitationOut, RejectedCitation, RetrievalHit
from .store import Store

logger = logging.getLogger("brf.answer")

GROUNDING_CONTRACT = """Du är en dokumentassistent för en bostadsrättsförenings styrelse. Du svarar på svenska.

ABSOLUTA REGLER:
1. Använd ENDAST informationen i utdragen nedan. Ingen egen kunskap, inga gissningar.
2. Varje sakpåstående i svaret ska stödjas av minst en källhänvisning i "citations".
3. Varje "quote" ska vara ett ORDAGRANT, sammanhängande utdrag ur ETT enda utdrag — kopiera texten exakt som den står, max 40 ord, inga utelämningar, ingen "…".
4. "chunk_id" ska vara exakt det id som står inom hakparentes före utdraget.
5. Citera hellre kort och exakt än långt.
6. Om utdragen inte räcker för att besvara frågan: sätt "insufficient_data": true och förklara kort i "answer" vad som saknas. Hitta ALDRIG på ett svar.

SVARSFORMAT — svara ENDAST med ett JSON-objekt, ingen annan text:
{"answer": "...", "citations": [{"chunk_id": "...", "quote": "..."}], "insufficient_data": false}"""

_RETRY_NUDGE = "\n\nVIKTIGT: Ditt förra svar gick inte att tolka. Svara ENDAST med JSON-objektet, utan kodblock eller extra text."


def _render_excerpts(hits: list[RetrievalHit]) -> str:
    parts = []
    for h in hits:
        parts.append(f"[{h.chunk_id}] ({h.document_name}, sida {h.page})\n{h.text}")
    return "\n---\n".join(parts)


def _refusal(reason: str, message: str, *, retrieval: list[RetrievalHit], provider: str, model: str, rejected=None) -> AskResponse:
    return AskResponse(
        answer=message,
        refusal=True,
        refusal_reason=reason,
        retrieval=retrieval,
        rejected_citations=rejected or [],
        provider=provider,
        model=model,
    )


def ask(store: Store, question: str, provider: LLMProvider | None = None) -> AskResponse:
    provider = provider or pick_provider()
    s = store.settings
    model = s.aiModel

    if len(store.index) == 0:
        return _refusal(
            "no_documents",
            "Det finns inga dokument uppladdade ännu. Ladda upp PDF:er så kan jag svara på frågor om dem.",
            retrieval=[],
            provider=provider.name,
            model=model,
        )

    hits = store.index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=s.candidateCount,
        top_k=s.topK,
        min_confidence=0.0,
    )

    low_relevance = not hits or hits[0].confidence < s.minRelevance
    if low_relevance and s.insufficientDataBehavior == "refuse":
        return _refusal(
            "low_relevance",
            "Jag hittar inget i de uppladdade dokumenten som verkar besvara den frågan, "
            "så jag avstår hellre än att gissa.",
            retrieval=hits,
            provider=provider.name,
            model=model,
        )

    system = (s.systemPrompt.strip() + "\n\n" if s.systemPrompt.strip() else "") + GROUNDING_CONTRACT
    user = f"FRÅGA: {question}\n\nUTDRAG:\n{_render_excerpts(hits)}"

    parsed = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            raw = provider.complete(
                system if attempt == 0 else system + _RETRY_NUDGE,
                user,
                max_tokens=s.maxResponseLength,
                model=model,
            )
            parsed = parse_llm_json(raw)
            break
        except LLMFormatError as exc:
            last_err = exc
            logger.warning("LLM-svar gick inte att tolka (försök %d): %s", attempt + 1, exc)
        except LLMError as exc:
            last_err = exc
            break
    if parsed is None:
        return _refusal(
            "insufficient_data",
            f"Tekniskt fel vid svarsgenerering: {last_err}",
            retrieval=hits,
            provider=provider.name,
            model=model,
        )

    if parsed["insufficient_data"]:
        message = parsed["answer"] or "Dokumenten innehåller inte tillräcklig information för att besvara frågan."
        if s.insufficientDataBehavior == "refuse":
            return _refusal("insufficient_data", message, retrieval=hits, provider=provider.name, model=model)
        return AskResponse(
            answer=message,
            warning="Svaret är osäkert: underlaget bedömdes otillräckligt.",
            retrieval=hits,
            provider=provider.name,
            model=model,
        )

    hit_scores = {h.chunk_id: h.score for h in hits}
    citations: list[CitationOut] = []
    rejected: list[RejectedCitation] = []
    for c in parsed["citations"]:
        chunk = store.chunks.get(c["chunk_id"])
        if chunk is None:
            rejected.append(RejectedCitation(chunk_id=c["chunk_id"], quote=c["quote"], reason="unknown_chunk"))
            continue
        res = resolve_quote(chunk, c["quote"], store.pages)
        if isinstance(res, Resolved):
            citations.append(
                CitationOut(
                    document_id=chunk.document_id,
                    document_name=store.documents[chunk.document_id].name
                    if chunk.document_id in store.documents
                    else chunk.document_id,
                    page=res.page,
                    quote=c["quote"],
                    chunk_id=chunk.id,
                    rects=res.rects,
                    score=hit_scores.get(chunk.id, 0.0),
                )
            )
        else:
            assert isinstance(res, Rejected)
            rejected.append(RejectedCitation(chunk_id=c["chunk_id"], quote=c["quote"], reason=res.reason))

    if s.requireSources and parsed["citations"] and not citations:
        return _refusal(
            "grounding_failed",
            "Jag kunde inte verifiera svarets källhänvisningar mot dokumenten, "
            "så jag visar hellre inget svar än ett ogrundat.",
            retrieval=hits,
            provider=provider.name,
            model=model,
            rejected=rejected,
        )
    if s.requireSources and not parsed["citations"]:
        return _refusal(
            "grounding_failed",
            "Svaret saknade källhänvisningar och visas därför inte.",
            retrieval=hits,
            provider=provider.name,
            model=model,
        )

    warning = None
    if rejected:
        warning = f"{len(rejected)} källhänvisning(ar) kunde inte verifieras och har tagits bort."
    if low_relevance:
        warning = ((warning + " ") if warning else "") + "Osäkert underlag: träffarna hade låg relevans."

    return AskResponse(
        answer=parsed["answer"],
        citations=citations,
        rejected_citations=rejected,
        retrieval=hits,
        warning=warning,
        provider=provider.name,
        model=model,
    )
