# 65536 ops, one bound, prefix warmup, edge order — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 65536 the running `-c`, drop the magic 32000 archive ceiling, pay full-corpus prefill at ingest, and measure U-shape document order against page order.

**Architecture:** Compose file is ops. `decide_fit` uses only `n_ctx − 512 − response_budget` plus optional `fullCorpusTokenThreshold` (`None` default, `0` off). `prefix_warmup.py` runs after `_rebuild` off the lock. `edge_order` is a pure function; live script compares three orders; product keeps page or query-independent per spec.

**Tech Stack:** llama.cpp compose, FastAPI store, pytest, loopback Gemma 4.

## Global Constraints

- Worktree: `/home/simon/brfv2/.worktrees/full-corpus-ask` on `feat/full-corpus-ask`.
- Spec: `docs/superpowers/specs/2026-08-16-nctx-ops-warmup-edge-order-design.md`.
- Do not touch citation verification, numeric grounding, or excerpt labels.
- Loopback only. No PDF text/filenames in git. Code English; commit messages Swedish.
- Citation chain and fit *paths* stay; only when prefill runs, and how excerpts are ordered in the experiment.

---

### Task 1: Operational n_ctx=65536

**Files:** `/home/simon/llama-cpp/docker-compose.yml`; `backend/scripts/measure_nctx_cost.py`; `backend/scripts/live_full_corpus.py`; `docs/evidence/nctx-ops-65536.md`

- [ ] Change `-c 16384` to `-c 65536` in the tracked compose file (not an override).
- [ ] `docker compose up -d` in `/home/simon/llama-cpp`. Wait until `/props` `default_generation_settings.n_ctx == 65536`.
- [ ] Rename `_restore_16384` → restore-to-ops targeting **65536**. Occupancy control at 16384 may still override then restore 65536.
- [ ] `cd /home/simon/brfv2/.worktrees/full-corpus-ask && make test`
- [ ] Write `docs/evidence/nctx-ops-65536.md` (n_ctx from `/props`, compose carries 65536).
- [ ] Commit `feat(ops): n_ctx 65536 som driftinställning`

### Task 2: One fit bound (TDD)

**Files:** `backend/app/schemas.py`, `backend/app/full_corpus.py`, `backend/app/document_ask.py`, `backend/tests/test_full_corpus.py`, `backend/scripts/live_full_corpus.py`

- [ ] Failing tests replacing chunk-sum-vs-32000:
  - default `None` + prefix under window → `fits`
  - `threshold=0` → retrieval, bound `threshold`
  - prefix over window, `threshold=None` → bound `n_ctx`
  - prefix 40000, threshold 32000, n_ctx 65536 → bound `threshold` (optional cap)
  - chunk_token_sum 40000, prefix 100, threshold `None`, n_ctx 16384 → **fits** (chunk sum is not a gate)
- [ ] `fullCorpusTokenThreshold: int | None = Field(default=None, ge=0)`
- [ ] `decide_fit(..., threshold: int | None)` as spec. `pack_documents` still treats only `0` as off.
- [ ] Tests that set 32000 for “A on” can drop it (default None). Tests that set `1` to skip A and hit B stay.
- [ ] `live_full_corpus.py`: after threshold `None`, stop 100000.
- [ ] `uv run pytest tests/test_full_corpus.py tests/test_document_ask.py tests/test_multihop.py -q`
- [ ] Commit `feat(ask): en enda arkivgräns, n_ctx minus reserver`

### Task 3: Prefix warmup (TDD)

**Files:** Create `backend/app/prefix_warmup.py`; modify `backend/app/store.py`; `backend/tests/test_prefix_warmup.py`

- [ ] Failing tests:
  - `warm_prefix` calls `complete` with user starting `UTDRAG:` and ending `FRÅGA: .` when gate fits; does not parse the completion.
  - skip when threshold is 0 / runtime missing / archive does not fit.
  - generation counter: a stale warmup does not call complete after a newer rebuild.
  - FakeLLM/BRF_LLM=fake: `_rebuild` does not call the model.
- [ ] Implement `warm_prefix(store, runtime, provider)` and `schedule_warm_prefix(store)` (daemon thread, gen coalescing). Hook from `_rebuild` after publishing new chunks, outside the LLM call (schedule only).
- [ ] Log `prefix_warmup done` / `prefix_warmup skip=`.
- [ ] `uv run pytest tests/test_prefix_warmup.py tests/test_full_corpus.py -q`
- [ ] Commit `feat(ask): värm helarkivprefix efter ingestion`

### Task 4: Edge-order helper (TDD)

**Files:** `backend/app/full_corpus.py` (or `backend/app/edge_order.py`); `backend/tests/test_edge_order.py`

- [ ] `edge_order(["A","B","C","D"]) == ["A","C","D","B"]`
- [ ] `hits_for_full_corpus(..., document_ids=["B","A"])` emits all B chunks (page order) then A.
- [ ] Query-independent order identical for two questions given the same index/probe.
- [ ] Commit `feat(ask): U-formad dokumentordning för utdrag`

### Task 5: Live edge-order experiment

**Files:** `backend/scripts/live_edge_order.py`; `docs/evidence/edge-order.md`

- [ ] Three modes: `page`, `probe` (frozen probe + edge_order, once), `query` (per question). Same 10-PDF folder, `q_name`/`q_seat`/`q_notice`, model2vec, n_ctx 65536. Per case: refused, cites, timings, `cache_n`. Warm prefix once for `page` and `probe` before Q1.
- [ ] Write evidence. Product: if `probe` does not increase verified→refused vs `page`, switch `evaluate_full_corpus` to probe+edge_order; else leave page order. Never default `query`.
- [ ] Commit `docs(eval): kantordning mot sidordning per fall` (and product switch commit if probe is kept).

### Task 6: Offline suite

- [ ] `make test`; ruff on touched files; `/props` still 65536.
- [ ] Commit any leftovers `test(ask): …` / `docs(eval): …`
