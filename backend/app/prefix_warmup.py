"""Warm the full-corpus prefix after the archive text changes.

Prefill belongs to ingestion, not question one. The completion is discarded;
only the llama.cpp prefix-KV side effect matters.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from .full_corpus import live_corpus_runtime, user_prompt
from .llm import LLMError, pick_provider

logger = logging.getLogger("brf.prefix_warmup")

WARMUP_QUESTION = "."


def warm_prefix(
    store,
    runtime,
    provider,
    *,
    expected_gen: int | None = None,
) -> dict[str, Any]:
    """Run one tiny completion on the current full-corpus prefix. Never raises."""
    if expected_gen is not None and getattr(store, "_warmup_gen", 0) != expected_gen:
        logger.info("prefix_warmup skip=stale tenant=%s", getattr(store, "tenant_id", "?"))
        return {"status": "skip", "reason": "stale"}
    if runtime is None:
        logger.info("prefix_warmup skip=runtime tenant=%s", getattr(store, "tenant_id", "?"))
        return {"status": "skip", "reason": "runtime"}

    _index, chunks, _pages, documents = store.snapshot()
    if not chunks:
        logger.info("prefix_warmup skip=empty tenant=%s", getattr(store, "tenant_id", "?"))
        return {"status": "skip", "reason": "empty"}

    from .answer import _render_excerpts, _system_prompt, evaluate_full_corpus

    evaluated = evaluate_full_corpus(store, chunks, documents, runtime)
    if evaluated is None:
        logger.info("prefix_warmup skip=tokenizer_error tenant=%s", getattr(store, "tenant_id", "?"))
        return {"status": "skip", "reason": "tokenizer_error"}
    decision, full_hits = evaluated
    if not decision.use_full_corpus:
        logger.info(
            "prefix_warmup skip=%s tenant=%s",
            decision.bound,
            getattr(store, "tenant_id", "?"),
        )
        return {"status": "skip", "reason": decision.bound}

    if expected_gen is not None and getattr(store, "_warmup_gen", 0) != expected_gen:
        logger.info("prefix_warmup skip=stale tenant=%s", getattr(store, "tenant_id", "?"))
        return {"status": "skip", "reason": "stale"}

    system = _system_prompt(store.settings)
    excerpts, _alias = _render_excerpts(full_hits)
    user = user_prompt(WARMUP_QUESTION, excerpts, full_corpus=True)
    try:
        provider.complete(system, user, max_tokens=1, model=store.settings.aiModel)
    except LLMError:
        pass
    logger.info(
        "prefix_warmup done tenant=%s prefix_tokens=%s n_ctx=%s",
        getattr(store, "tenant_id", "?"),
        decision.prefix_tokens,
        decision.n_ctx,
    )
    return {
        "status": "done",
        "prefix_tokens": decision.prefix_tokens,
        "n_ctx": decision.n_ctx,
    }


def schedule_warm_prefix(store) -> None:
    """Coalesce rebuilds: only the latest generation talks to the model."""
    if os.environ.get("BRF_PREFIX_WARMUP", "1").strip().lower() in ("0", "false", "no"):
        return
    runtime = live_corpus_runtime()
    if runtime is None:
        return
    gen = getattr(store, "_warmup_gen", 0) + 1
    store._warmup_gen = gen

    def _run() -> None:
        try:
            provider = pick_provider()
            warm_prefix(store, live_corpus_runtime(), provider, expected_gen=gen)
        except Exception:
            logger.exception("prefix_warmup failed tenant=%s", getattr(store, "tenant_id", "?"))

    threading.Thread(target=_run, name="brf-prefix-warmup", daemon=True).start()
