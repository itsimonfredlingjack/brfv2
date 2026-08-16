# Occupancy needle and archive ask — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate haystack length from window occupancy in the needle, then fire gate A on the real archive at 65536 only if a 48k haystack holds a fact, then rerun document ranking with model2vec.

**Architecture:** Extend `needle_haystack.py` (structured filler + occupancy gates). Add `--mode occupancy` to `measure_nctx_cost.py`. New `live_full_corpus.py` for archive before/after. `live_document_ask.py` defaults to model2vec.

**Tech Stack:** Same as previous plan (llama.cpp override, pytest, loopback).

## Global Constraints

- Worktree: `/home/simon/brfv2/.worktrees/full-corpus-ask` on `feat/full-corpus-ask`. Do not edit `/home/simon/brfv2`.
- Spec: `docs/superpowers/specs/2026-08-16-occupancy-needle-and-archive-ask-design.md`.
- Do not tear down packer, document path, or `--mode filled-window`.
- Tracked compose untouched. Always restore `-c 16384`.
- No PDF text/filenames in git. Code English; commit messages Swedish.
- Product `fullCorpusTokenThreshold` default stays 32000. Archive live uses 100000 in the temp store only.
- `q_interest` / `q_solidity` are not B evidence until an annual report exists.

---

### Task 1: Structured haystack + occupancy gates (TDD)

**Files:** `backend/app/needle_haystack.py`, `backend/tests/test_nctx_cost.py`

- [ ] Failing tests: filler is not `lorem`; has repeating `Avsnitt` headings; `occupancy_holds_for_archive`; `occupancy_explains_old_miss`.
- [ ] Implement `structured_filler_words`, switch `build_haystack`, add `HAYSTACK_SIZES = (8000, 16000, 32000, 48000, 62000)`, the two gate helpers.
- [ ] `uv run pytest tests/test_nctx_cost.py -q`
- [ ] Commit `feat(eval): strukturerad höstack och beläggningsnål`

### Task 2: Occupancy driver

**Files:** `backend/scripts/measure_nctx_cost.py`, tests for CLI helpers if cheap.

- [ ] `--mode occupancy|filled-window` (default occupancy). Occupancy: one `-c 65536` sweep over `HAYSTACK_SIZES`, one stable check, restore 16384, 16k structured control at 16384, restore again (already 16384).
- [ ] Do not call `recommend_nctx` on occupancy rows. Write `out/nctx-cost/occupancy.json`.
- [ ] Commit `feat(eval): mät nål vid fast 65536 och varierad höstack`

### Task 3: Live occupancy + evidence

- [ ] Confirm `/props` 16384, run occupancy, confirm restore 16384.
- [ ] Write `docs/evidence/nctx-occupancy.md` (hit matrix + occupancy-vs-length + 48k gate).
- [ ] Commit `docs(eval): beläggning mot längd för gemma4:e12b`

### Task 4: Archive live if 48k gate passed

**Files:** `backend/scripts/live_full_corpus.py`

- [ ] threshold 0 vs 100000, questions `q_name`/`q_seat`/`q_notice`, timings Q1 vs Q2/Q3, `compare_ask_cases` per case, network audit, restore 16384.
- [ ] If gate failed: skip script run; note in evidence.
- [ ] Commit code; commit `docs(eval): helarkiv mot retrieval vid 65536` only if the run happened.

### Task 5: Document path with model2vec

- [ ] `live_document_ask.py`: default `model2vec`; refuse hashed without `--allow-hashed`.
- [ ] One-doc at 16384: `q_name`, `q_seat` (omit financial questions).
- [ ] Evidence: classifier vs missing annual report (already known: missing).
- [ ] Commit `fix(eval): dokumentväg mot model2vec` + evidence update.

### Task 6: Offline suite

- [ ] `make test`, ruff on touched files, `/props` 16384.
