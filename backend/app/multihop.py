"""Planned, evidence-grounded answering across several documents (BRF-1).

    question → query plan → bounded retrieval fan-out → evidence pack
             → synthesis → the EXISTING citation + numeric verification

This is an orchestration surface over the retrieval stack that already
exists, not a second one. It owns exactly three decisions — how many
searches to run, which chunks survive deduplication, and how much page-local
context to pull in — and delegates everything else: `HybridIndex.search` for
retrieval, `answer.ask` for synthesis, and through it
`citations.resolve_citation` and the numeric grounding gate for verification.

What it deliberately is NOT (BRF-2): there is no agent loop, no tool calling,
no persistent memory, and no state that outlives the request. The plan is
produced once, the fan-out width is capped by the application, and execution
is a straight line with no feedback edge back into planning.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from .answer import ask
from .evidence import EvidencePack, expand_context
from .llm import LLMProvider, pick_provider
from .query_plan import QueryPlan, plan_query
from .schemas import AskResponse
from .store import Store

logger = logging.getLogger("brf.multihop")

# Per-subquery retrieval width. Deliberately narrower than a single-search
# topK: three subqueries at the full width would bury the answer in a prompt
# of mostly-irrelevant excerpts, which is the failure mode fan-out is
# supposed to fix rather than cause.
PER_QUERY_TOP_K = 4
# Ceiling on excerpts reaching the prompt after dedup and expansion.
MAX_EVIDENCE_CHUNKS = 10


def planned_ask_enabled() -> bool:
    """Server-side kill switch for the planned path (BRF_PLANNED_ASK).

    Read per call, not at import, so a deployment can flip it without a
    rebuild and so tests can set it per case. Off unless explicitly on: the
    request field alone must never be able to route a tenant onto a path a
    deployment has not enabled.
    """
    return os.environ.get("BRF_PLANNED_ASK", "").strip().lower() in ("1", "true", "yes", "on")


class PlannedAnswer:
    """An answer plus the evidence trail that produced it.

    The pack is returned alongside the response rather than folded into it:
    `AskResponse` is a wire contract the frontend already depends on, and
    BRF-1 does not change it.
    """

    __slots__ = ("response", "plan", "pack")

    def __init__(self, response: AskResponse, plan: QueryPlan, pack: EvidencePack) -> None:
        self.response = response
        self.plan = plan
        self.pack = pack


def catalogue_names(documents: dict) -> list[str]:
    """The document catalogue the planner is shown, in a deterministic order.

    Sorted, not upload-ordered. The planner decodes greedily, so for a fixed
    prompt it is deterministic — which made the ORDER of this list the only
    remaining source of run-to-run variance, and an undesigned one: it was
    `documents.values()`, i.e. upload order, so re-uploading a document could
    silently change how a question got planned. Measured before the fix: with
    the catalogue shuffled, 22 of 59 cases changed mode.

    A total order (casefold first so case cannot reorder, raw name as
    tie-break) makes the plan a function of the corpus, not of its history.
    """
    return sorted((m.name for m in documents.values()), key=lambda n: (n.casefold(), n))


def _clarify_response(plan: QueryPlan, provider_name: str, model: str) -> AskResponse:
    """A clarification is NOT an answer and must never look like one: no
    citations, and the existing `insufficient_data` refusal reason, so every
    consumer that already handles a refusal handles this correctly without
    learning a new state."""
    return AskResponse(
        answer=plan.clarification,
        refusal=True,
        refusal_reason="insufficient_data",
        clarification=plan.clarification,
        retrieval=[],
        provider=provider_name,
        model=model,
    )


def ask_planned(
    store: Store,
    question: str,
    provider: LLMProvider | None = None,
    *,
    trusted_names: Iterable[str] = (),
    expand: bool = True,
) -> PlannedAnswer:
    """Answer `question`, retrieving across documents when the plan says so.

    Tenant isolation is inherited, not re-implemented: everything reads from
    the `store` the caller already resolved for this tenant, through one
    `snapshot()` view, exactly as `ask` does.
    """
    provider = provider or pick_provider()
    s = store.settings
    trusted_names = tuple(trusted_names)
    provider_model = getattr(provider, "model", "") or ""
    generation_model = provider_model or s.aiModel
    model = "" if provider.name in ("fake", "none") else generation_model

    index, chunks, pages, documents = store.snapshot()
    pack = EvidencePack(question=question)

    if len(index) == 0:
        # Same refusal as the single-search path; planning an empty corpus is
        # a waste of a model call.
        return PlannedAnswer(
            ask(store, question, provider, trusted_names=trusted_names),
            QueryPlan(mode="single", subqueries=[question], degraded=True),
            pack,
        )

    doc_names = catalogue_names(documents)
    plan = plan_query(question, provider, document_names=doc_names, model=generation_model)
    pack.planned_subqueries = list(plan.subqueries)

    if plan.mode == "clarify":
        # A clarification is only honest if the corpus really cannot answer.
        # The planner decides BEFORE any retrieval, on the question's wording
        # alone, and it was wrong four times in 46: "När hålls nästa
        # styrelsemöte?" is vague as a sentence and perfectly answerable as a
        # search. So the counter-question becomes a decision AFTER retrieval —
        # it may only stand where the same signal the single path refuses on
        # (`minRelevance`) says there is nothing to find.
        #
        # This costs one search on every clarify, and two on a question the
        # probe rescues: the rescue hands back to the unchanged single path
        # rather than reusing these hits, because `single` staying literally
        # the same code is worth more than one index lookup. It costs no
        # extra model call, which is the expensive resource.
        probe = index.search(
            question,
            weight=s.searchWeighting / 100.0,
            candidates=s.candidateCount,
            top_k=s.topK,
            min_confidence=0.0,
        )
        top_confidence = max((h.confidence for h in probe), default=0.0)
        if top_confidence < s.minRelevance:
            logger.info("Frågan behöver förtydligas: %s", plan.clarification)
            return PlannedAnswer(_clarify_response(plan, provider.name, model), plan, pack)
        logger.info(
            "Planeraren ville förtydliga, men hämtningen hittade material (%.2f ≥ %.2f); söker i stället.",
            top_confidence, s.minRelevance,
        )
        plan = QueryPlan(mode="single", subqueries=[question], downgraded_from="clarify")

    if plan.mode == "single":
        # One search — hand straight back to the unchanged single path so
        # this stays literally the same code, not a copy that can drift.
        resp = ask(store, plan.subqueries[0] if plan.subqueries else question, provider, trusted_names=trusted_names)
        pack.add_query(plan.subqueries[0] if plan.subqueries else question, list(resp.retrieval), plan_index=0)
        return PlannedAnswer(resp, plan, pack)

    # --- multi: bounded fan-out -------------------------------------------
    for i, sub in enumerate(plan.subqueries):
        hits = index.search(
            sub,
            weight=s.searchWeighting / 100.0,
            candidates=s.candidateCount,
            top_k=PER_QUERY_TOP_K,
            min_confidence=0.0,
        )
        record = pack.add_query(sub, hits, plan_index=i)
        logger.debug(
            "Delfråga %d/%d gav %d träffar (%d dubbletter): %s",
            i + 1, len(plan.subqueries), len(record.hit_ids), len(record.duplicate_ids), sub,
        )

    if not pack.hits:
        return PlannedAnswer(
            ask(store, question, provider, trusted_names=trusted_names), plan, pack
        )

    if expand:
        # Budget expansion against what is left under the prompt ceiling.
        room = max(0, MAX_EVIDENCE_CHUNKS - len(pack.hits))
        if room:
            expand_context(pack, chunks, documents, max_added=room)

    if len(pack.hits) > MAX_EVIDENCE_CHUNKS:
        pack.hits = pack.hits[:MAX_EVIDENCE_CHUNKS]

    # The ORIGINAL question is what gets answered — the subqueries were a
    # retrieval instrument, and asking the model to answer one of them would
    # answer a question the board never asked.
    resp = ask(store, question, provider, trusted_names=trusted_names, evidence=pack)
    return PlannedAnswer(resp, plan, pack)
