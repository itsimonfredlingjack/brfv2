# 65536 as ops, one fit bound, prefix warmup, edge-order experiment

Date: 2026-08-16
Branch / worktree: `feat/full-corpus-ask` at `.worktrees/full-corpus-ask`
Extends: occupancy needle + archive live (`docs/superpowers/specs/2026-08-16-occupancy-needle-and-archive-ask-design.md`)

The occupancy needle held facts at 10 % and 90 % from 8k–62k in a 64k window. The 10-PDF archive fitted (`prefix_tokens=54539`, `bound=fits` at a raised knob). Cold prefill was 30.7 s, then ~70 ms. This spec turns that measurement into operations, removes the knob that blocked the path, pays prefill when the archive changes, and measures lost-in-the-middle ordering without touching the citation chain.

## Problem

1. `-c 65536` was a temporary override. Ops is still 16384, so the archive path never fires in the running server.
2. `fullCorpusTokenThreshold=32000` is a second, magic ceiling. It bound the 10-PDF archive (`chunk_token_sum=48923`) even when `n_ctx=65536` had room. The live run had to set 100000 in a temp store to see the path work.
3. Question one pays the 30.7 s prefill. Prefix-KV already makes Q2/Q3 cheap; the cold cost belongs to ingestion, not the first ask.
4. The needle misses 50 % depth from 8k to 62k. Excerpts are rendered in document/page order, which is arbitrary vs relevance. Putting high-score documents at the edges is an experiment, not a citation change.

## Goal (four steps, in order)

1. Make **65536 the operational `-c`** in the tracked compose file (`/home/simon/llama-cpp/docker-compose.yml`). Restart, verify `/props`, run the offline suite.
2. **One real bound:** `n_ctx − question_reserve − response_budget`. The settings knob is an optional extra ceiling, default **none**. `0` stays the before/after off switch.
3. **Warm the prefix in the background** after the archive text changes (ingestion, including OCR). Log when it is done. Question one should hit warm cache in the normal case. Do not change the citation chain or the fit gate — only *when* prefill runs.
4. **Edge-order experiment** on the full-corpus excerpt block: highest-scoring documents first and last, lowest in the middle. Two variants: query-independent (once per archive) and query-dependent. Report quality and cache per case vs document/page order. If the query-independent variant matches the quality win, keep that one (stable prefix). Do not keep a question-dependent order as the product default if it kills the cache for no extra quality.

## Non-goals

- Changing citation resolution, numeric grounding, highlight rects, or excerpt labels (`K1`…).
- Changing the fit *meaning* of gate A/B (still: archive fits → full corpus; else document pack if top document fits; else retrieval).
- Shipping query-dependent excerpt order as the default.
- Filling 50 % needle misses by shuffling chunks *inside* a document (page order inside a document stays).
- Financial questions until an annual report exists.
- Hosted providers. Loopback only.

## 1 — Operational n_ctx=65536

Edit `/home/simon/llama-cpp/docker-compose.yml` (`-c 16384` → `-c 65536`). No gitignored override. `docker compose up -d`, wait until `GET http://127.0.0.1:8000/props` → `default_generation_settings.n_ctx == 65536`.

Measurement restore helpers that currently force 16384 become restore-to-ops (`65536`). Occupancy/filled-window scripts may still *temporarily* override `-c` for experiments, then restore **65536**.

`make test` from the worktree after the restart. Evidence: one line in `docs/evidence/nctx-ops-65536.md` with `/props` n_ctx and that the compose file (not an override) carries `-c 65536`.

VRAM headroom from occupancy (~4 GiB free at 8266 MiB) is the cost evidence; do not re-run the needle.

## 2 — One bound

Today `decide_fit` requires both `chunk_token_sum <= threshold` and `prefix_tokens + 512 + response_budget <= n_ctx`. Drop the chunk-sum comparison.

```
window_cap = n_ctx − 512 − (maxResponseLength + 600)
effective_cap = window_cap                           if threshold is None
              = min(window_cap, threshold)           if threshold > 0
```

Fit when `prefix_tokens <= effective_cap`.

| Setting | Meaning |
| --- | --- |
| `None` (default, “ingen”) | Only the window cap. |
| `0` | Force retrieval (and document path off), before/after switch. Bound `threshold`. |
| `N > 0` | Optional extra ceiling on **prefix_tokens**. Binds as `threshold` only when `N` is tighter than `window_cap` and prefix exceeds `N`. |

`Settings.fullCorpusTokenThreshold: int | None = None` (`ge=0`). Persisted `32000` in an old `settings.json` still binds until cleared — do not silently rewrite tenant files.

Gate B (`pack_documents`): `0` still disables; `None` or `N > 0` pack against **n_ctx** only (the extra ceiling is an archive-size knob, not a document-pack knob). Tests that set `threshold=1` to skip A and exercise B stay valid.

Log still includes `bound`, `n_ctx`, `threshold`, `effective_cap`. `chunk_token_sum` remains a metric, not a gate.

`live_full_corpus.py`: after = default/`None`, before = `0`. Stop using 100000.

## 3 — Prefix warmup

Prefill is the same tokens `ask()` would send as the cacheable prefix: `system + "\n\nUTDRAG:\n" + excerpts` with question last. Warmup sends that prefix plus a tiny dummy question (`"."`) through the same self-hosted chat path (`cache_prompt: true`), discards the completion (catch `LLMError` — `max_tokens=1` often truncates JSON).

When: after the archive *text* changes — `Store._rebuild` (upload, delete, wipe, rechunk, and OCR-inside-`add_document`). Not on ask. Not on settings that do not rechunk.

How: daemon thread, **not** under `Store.lock`, **not** blocking the upload response. Coalesce with a generation counter: overlapping rebuilds skip stale warmups so ten sequential PDFs pay one final prefill.

Skip when `live_corpus_runtime()` is None (`BRF_LLM=fake|scripted|none` or no base URL), when the tenant has no chunks, or when `decide_fit` is not `use_full_corpus`. Log `prefix_warmup skip=…` or `prefix_warmup done tenant=… prefix_tokens=… prompt_ms=… cache_n=…`.

Question one after a completed warmup should look like today’s Q2 (`prompt_n` ≈ question tokens, `cache_n` ≈ prefix). If warmup is still running, ask waits behind `--parallel 1` (acceptable). If warmup failed, ask is cold (acceptable).

Do not change `_synthesize`, citation verification, or `decide_fit` predicates.

## 4 — Edge order (experiment)

Lost-in-the-middle: 50 % depth missed at every haystack size. Documents are the reorder unit. Chunks inside a document stay page/`word_start` order.

U-shape from a high-to-low ranked document list `D0, D1, …`:

```
left gets even indices, right gets odd; return left + reversed(right)
# 4 docs A>B>C>D → A, C, D, B  (best first and last, worst toward the middle)
```

**Page order (control):** today’s `hits_for_full_corpus` sort `(name, document_id, page, word_start, id)`.

**Query-independent:** score documents once per archive with a **frozen probe** (not the user question):

```
"stadgar styrelse förening kallelse årsredovisning ekonomi"
```

Same `index.search` + `score_documents` as path B. Edge-order those ids. Prefix is stable across questions → cache lives. Compute at rebuild/warmup time; reuse for every ask until the archive changes.

**Query-dependent:** same scoring against the *user* question, then edge-order. Prefix changes every question → cache dies. Measurement only.

Live: 10-PDF tenant, `n_ctx=65536`, `model2vec`, questions `q_name` / `q_seat` / `q_notice`. Three runs, same docs. Per case: refused, cites, `prompt_n`, `prompt_ms`, `cache_n`, path. Headline is per-case verified→refused vs page order, plus whether Q1 is warm.

Keep query-independent in the product **only if** it does not worsen verified→refused vs page order. If it ties page order on quality and keeps Q2-style cache, it is the one to keep (needle says middle is the problem; edges without cache death is the point). If query-dependent is the only quality win, write that and **do not** ship it as default.

## Success

- `/props` n_ctx is 65536 from the tracked compose file. Offline tests green.
- Default settings let the 10-PDF archive take gate A at 65536 without a temp 100000 knob. `0` still forces retrieval.
- After ingest, logs show warmup done; a following ask shows collapsed `prompt_n` when warmup finished first.
- Edge-order evidence table, per case, with cache columns; product order is page or query-independent per the rule above.
- Citation tests unchanged in behaviour.
