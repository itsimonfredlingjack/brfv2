# Full-corpus ask path (size-gated)

Date: 2026-08-16
Approved approach: **A — gate in `ask()`, same excerpt renderer, retrieval unchanged above the cap**

## Problem

The installed answer path always retrieves `topK=6` chunks (hybrid BM25 + dense, optional rerank), renders them as numbered excerpts, and generates against that window. On a comparable small model, putting the whole corpus in context beat retrieval when it fit (0.7759 vs 0.7516 dense / 0.7549 BM25 top-5 at 16 documents / 21k tokens). Warm prefix-KV cache on llama.cpp made the second question cheap relative to a cold prefill.

Swedish housing-association archives are often 5–50 PDFs. Many will fit in the local Gemma 4 12B slot (`n_ctx=16384` on agenntserver). Retrieval is then the wrong first wall: the 2026-07-18 annual-report diagnosis found every substantive refusal at default `topK=6` was a `retrieval_miss`.

The citation resolver, numeric gate, and PDF highlighter must not change. Only which chunks reach the prompt may change, and only when the archive actually fits.

## Goal

A second answer path, chosen per association from archive token volume:

1. Measure per-association token volume with the **same tokenizer the generator uses**.
2. When volume is under a configurable cap **and** fits in the live context window, skip retrieval and put every chunk in the prompt, in document/page order, through the existing excerpt format.
3. Keep the excerpt prefix byte-identical across questions for the same unchanged archive so llama.cpp’s prefix-KV cache hits. Put the question last on this path only.

Above the cap, today’s path is byte-for-byte unchanged.

## Non-goals

- Changing citation resolution, numeric grounding, highlight rects, or the excerpt label format.
- Removing chunk overlap (measure spill only).
- Raising llama.cpp `n_ctx` or swapping the model.
- Treating Gemma 3 RULER figures (80.3 at 32k / 57.1 at 128k) as a bound on the running Gemma 4 12B (`gemma4:e12b`).
- Changing `refusal_buckets.py` default behaviour (committed evidence behind `docs/evidence/reality-report.md` / `refusal-diagnosis.md`).
- Network traffic outside loopback. Committing anything derived from a real document (only numeric reports).

## Runtime facts (this host, verified 2026-08-16 against the running server)

- Generator: Gemma 4 12B IT, llama.cpp `b9976-e3546c794` on `127.0.0.1:8000`, `--parallel 1` (one slot).
- **`n_ctx` is not on the OpenAI `/v1/models` list shape.** Verified:
  - `GET /props` → **`default_generation_settings.n_ctx = 16384`**. Top-level `n_ctx` is absent.
  - `GET /slots` → `slots[0].n_ctx = 16384`.
  - `GET /v1/models` happens to carry `data[0].meta.n_ctx` on *this* build — do not rely on it. `GET /v1/props` is **404**.
- **Tokenizer:** `POST /tokenize` on the server **origin** (not under `/v1`). `POST /v1/tokenize` is **404**. `BRF_LLM_BASE_URL` is `http://127.0.0.1:8000/v1`; strip the `/v1` suffix before calling `/props` and `/tokenize`.
- Real association PDFs live on the laptop at `/home/aidev/Projects/brfv2-local-archive-2026-08-05/repository-material/DONT_PUSH_brf_stuff` (10 PDFs, one flat folder). Copy **PDFs only** into gitignored `DONT_PUSH_brf_stuff/` on agenntserver for measurement; never summaries or document text.

## Approach (approved)

Gate inside `ask()`. If the archive fits, build `RetrievalHit` objects for every chunk in stable document/page order and hand them to existing `_render_excerpts` → `_synthesize`. Do not run `index.search`, rerank, or `append_linked_table_legends` (legends exist to recover what retrieval missed; that reason is gone when everything is present).

If the archive does not fit, or `n_ctx` / the tokenizer is unavailable: today’s retrieval path, including `FRÅGA` first.

### Threshold rule

Configurable `Settings.fullCorpusTokenThreshold`, default **32000**. That default is an arbitrary starting value, not a measured Gemma 4 quality ceiling.

The path turns on only when **both** hold:

```
chunk_token_sum <= fullCorpusTokenThreshold
prefix_tokens + question_reserve + response_budget <= n_ctx
```

`chunk_token_sum` is the sum of generator-tokenizer counts over every `chunk.text` (overlap counted twice — that is prompt size, and the knob the threshold is compared to).

`prefix_tokens` is tokenize(`system` + `"\n\nUTDRAG:\n"` + the actual `_render_excerpts` string). Using the rendered string (not raw chunk sum) is what must fit; labels and `---` separators are real tokens.

`question_reserve` is **512** tokens. `response_budget` is `maxResponseLength + _CITATION_HEADROOM_TOKENS`.

`fullCorpusTokenThreshold=0` forces the retrieval path (live before/after on the same commit).

Read `n_ctx` from `GET {origin}/props` → `default_generation_settings.n_ctx`. If that key is missing, try `GET {origin}/slots` → `slots[0].n_ctx`. Cache the value on the self-hosted provider. Tests and FakeLLM have no `n_ctx` unless injected → gate is false → retrieval path. Existing tests therefore do not silently switch.

**Missing `n_ctx` is a WARN, not a silent fallback.** Log that the full-corpus path cannot be considered because context size is unknown, then take the retrieval path. The same WARN if `/props` and `/slots` both fail.

If `/tokenize` fails at ask time: WARN, retrieval path (never a silent substitute tokenizer). Empty archive: existing `no_documents`.

Every routing decision logs **which bound applied**:

| Outcome | `bound` in the log |
| --- | --- |
| `chunk_token_sum > fullCorpusTokenThreshold` | `threshold` |
| threshold holds but `prefix_tokens + 512 + response_budget > n_ctx` | `n_ctx` |
| both hold → full-corpus | `fits` |
| `n_ctx` unknown | `n_ctx_missing` |
| tokenize failed | `tokenizer_error` |
| `fullCorpusTokenThreshold == 0` | `threshold` (forced retrieval) |

On this host, 32000 > 16384, so **`n_ctx` always binds** for any archive that would otherwise pass the knob. The written report must state the **effective** cap (`n_ctx − question_reserve − response_budget − prefix overhead`), not 32000, as the reason a given association stayed on retrieval.

Planned/fan-out: the same gate runs first. If the archive fits, skip the planner (no extra model call whose hits would be discarded).

Cache `chunk_token_sum` and the fit verdict on the store until `_rebuild` or a settings change that affects `system` / threshold / response budget. Do not re-tokenize the archive on every question.

### Prompt

Excerpt format is unchanged:

```
[K1] ({document_name}, sida {page})
{chunk.text}
```

joined with `\n---\n`.

- Full-corpus path: `UTDRAG:\n{excerpts}\n\nFRÅGA: {question}` so the stable prefix is a true prefix.
- Retrieval path: `FRÅGA: {question}\n\nUTDRAG:\n{excerpts}` — unchanged.

`DeterministicTestLLM` must parse both orders.

Sort key for full-corpus hits (must be total and stable — dict insertion order is not a contract):

`(document_name, document_id, page, word_start, chunk_id)`

### Score contract

**Pre-LLM `minRelevance` gate is bypassed**, not fed zeros. Never compute `top_confidence`. Call `_synthesize(..., low_relevance=False)` so the “Osäkert underlag” warning does not fire. The UI list `NO_MODEL_REFUSAL_REASONS` includes `low_relevance`; this path invokes the model, so that label must not appear.

| Field | Full-corpus value | Why |
| --- | --- | --- |
| `RetrievalHit.score` | `0.0` | Same internal convention as legend padding: “not a retrieval score”. |
| `RetrievalHit.confidence` | `0.0` | Same. The relevance gate must never read these. |
| `RetrievalHit.bm25`, `.dense` | `0.0` | Same. |
| `RetrievalHit.rerank_score` | `None` | Rerank did not run. |
| `CitationOut.score` | `None` | User-facing. `0.0` would read as “weak evidence”. |

Frontend check (web `App.jsx` citation pills, PWA `Svar` / `CitationChip`, native `AnswerCard`): **no client renders `citation.score`**. They show quote, document name, and page. Schema: `CitationOut.score: float | None` — **required, no default**. A builder that forgets the field is a type/validation error (watches and incoming review still pass a real float). Retrieval path still sends the fused float. Full-corpus sends JSON `null`. Client TS types: `score: number | null`. No UI rendering change.

Do not invent `1.0` anywhere on this path.

### RetrievalHit consumers when every score is 0.0 / `rerank_score` is None

Grep of `.score` / `.confidence` / `.bm25` / `.dense` / `.rerank_score` on hits (2026-08-16). Full-corpus `ask()` returns the whole archive as `AskResponse.retrieval` with zeros.

| Consumer | Reads | When all zeros / None |
| --- | --- | --- |
| `answer.py` pre-LLM `minRelevance` | `max(h.confidence)` | **Must not run** on this path (bypass). If it did, everything would refuse. |
| `answer.py` “Osäkert underlag” | `low_relevance` flag | Passed `False`; warning does not fire. |
| `answer.py` `CitationOut.score` | `h.score` | Spec: pass `None`, not `0.0`. |
| `linked_context.append_linked_table_legends` | does not rank on scores; writes `0.0` on legend hits | Not called on this path. |
| `evidence.expand_context` | writes `0.0` on neighbours | Not called on this path. |
| `rerank.rerank_chunks` | copies hits, sets `rerank_score` | Not called on this path → `rerank_score` stays `None`. |
| `indexer.HybridIndex.search` | produces scores | Not called on this path. |
| `integrations/review.py` `_candidates` | `hit.score` from **its own** `index.search` | Unchanged. Invoice review does not use `ask()`’s hit list. |
| `integrations/intake.py` | `min_confidence` on **its own** search | Unchanged. |
| `kalla-native` `topHitsByDocument` | `hit.confidence` max-per-doc, sort desc, slice 4 | All equal → first-seen document wins; order is insertion (doc/page). Still returns up to 4 docs. |
| `kalla-native` `LivingIndex` | `hit.confidence.toFixed(2)` | Shows **`0.00`**. Looks like weak retrieval. Recorded consequence, not a silent UI rewrite in this change. |
| `kalla-native` `RefusalScreen` | same sort; bar width `confidence / max(0.01, …)` | All bars equal at the 6% minimum. “Högen genomsöktes ändå” still lists document names. |
| `brfv2-mockup` / `xs_mobilapp` | do not read hit scores | No change. |
| `scripts/reality/digital_reality.py` | `resp.retrieval[:6]` **pages**, not scores | First six in document order, not top-k. Numbers-only. |
| `scripts/eval_real_corpus.py`, `eval_fanout_delta.py` | confidence from **their own** `index.search` / pack | Unchanged unless they call `ask()` with the gate on. |
| Tests (`test_answer` legend hit, `test_linked_context`, `test_multihop` expansion, `test_rerank`) | assert `0.0` or real scores | Retrieval-path tests stay on retrieval (`n_ctx` unset). New tests cover full-corpus `None` / zeros. |

### Token measurement script

Script: `backend/scripts/measure_corpus_tokens.py`. `--folder` is required (never a hardcoded laptop path; never a silent default onto customer PDFs).

For each association directory (here: one folder of PDFs = one association):

- Ingest through real `Store.add_document` (OCR path).
- Tokenize with llama.cpp `/tokenize` on loopback only.
- Stdout: numbers only — never document text, never filenames in a committed artefact.

Per association report:

| Field | Definition |
| --- | --- |
| documents, pages, chunks | Store metadata after ingest |
| `chunk_token_sum` | Sum of tokenize(`chunk.text`) over all chunks (overlap double-counted) |
| `unique_tokens` | Sum of tokenize(page_text) over every page, where `page_text = " ".join(w.text for w in page.words)` — the **same join `chunker.chunk_pages` uses for `chunk.text`**. No extra normalize on either side. |
| spill | `chunk_token_sum - unique_tokens` |
| distribution | p50 / p95 / max of per-chunk token counts |

If one side were normalized and the other not, spill would be a lie; the script must use the raw word-join on both. Overlap is not removed from production chunking; spill is measured so a later decision can use it.

Network audit: loopback only; hard-fail otherwise.

### Prefix cache

Fingerprint = hash of `system + rendered UTDRAG` (not the question). Log at INFO when it changes for a tenant (upload, re-OCR, settings that affect the system prompt). A cold prefill after that log line is expected cache invalidation, not a performance regression.

One llama.cpp slot: two associations evict each other. Irrelevant for a single-association run; log it if a second tenant is asked in the same process.

**Do not assume the server reuses KV.** Verified on this build (`b9976`): two chat completions whose applied templates share a **442-token true prefix** still report `timings.cache_n ≈ 11` and `slots[0].n_prompt_tokens_cache = 0`. Sending `"cache_prompt": true` did not change that. The prefix is byte/token-stable; the slot is not keeping it.

Implementation:

1. Send `"cache_prompt": true` explicitly on every `OpenAICompatProvider` completion (harmless if already default).
2. Surface `timings.prompt_n`, `timings.prompt_ms`, `timings.cache_n` (log; do not add AskResponse fields — that lock is frozen).
3. Live check: second question against the same unchanged archive. **`timings.prompt_n` (tokens actually prefilled) must be dramatically lower than the first**, and `cache_n` must cover the shared prefix. If it is not, the report states that this llama.cpp build has no working prefix cache — a finding, not a success. Prefix stability tests still land; they prove the prompt, not the server.

### `refusal_buckets`

The rig is the measuring instrument behind committed evidence. Changing its retrieval would rewrite the baseline and make before/after incomparable.

- Default remains `index.search(..., top_k=settings.topK)` (today: 6).
- New explicit, opt-in mode (CLI flag) uses the same gate as `ask()` and classifies against the chunks that actually reached the prompt.
- On that opt-in mode, when an answer-bearing label row exists in the document, **containment `retrieval_miss` must be 0**. Assert it. A non-zero value means the gate is not routing as designed. The classifier’s existing “no answer-bearing row anywhere in the document” note is a locator miss, not a routing miss — do not treat that as a gate failure.

Before/after is a **per-(document, question) case diff**, not totals. Totals can stay flat while wins and losses swap. Produce a table with one row per case: verified-before → verified-after (and refusal reason before → after). The report’s headline number is **how many cases went from verified to refused**. If that count is greater than zero it is a finding even when the sum improved. Also list newly verified cases. Latency (prefill / answer, first vs second question) stays a separate column on the same rows. No new quality metric.

## Components

| Unit | Responsibility |
| --- | --- |
| Token counter | Count tokens via llama.cpp `/tokenize`; injectable stub for tests. |
| Fit gate | both bounds; log `bound=threshold\|n_ctx\|fits\|n_ctx_missing\|…`; `n_ctx` from `GET {origin}/props`. |
| Hit builder | All chunks → `RetrievalHit` with zero retrieval scores, `rerank_score=None`, stable sort. |
| `ask()` branch | If fit: skip search/rerank/legends, bypass `minRelevance`, question-last user prompt. Else: unchanged. |
| `CitationOut.score` | `None` on full-corpus; fused float on retrieval. |
| Measurement script | Per-association numeric report including unique tokens and spill. |
| Prefix fingerprint log | INFO on change; tests hash two questions’ prefixes. |
| `refusal_buckets` flag | Default old search; opt-in prompt-chunk mode + `retrieval_miss==0` assert. |

## Error handling

- No documents → existing `no_documents`.
- Tokenizer / `n_ctx` unavailable → WARN + retrieval path. Never silent.
- Archive larger than the cap → retrieval path.
- llama.cpp prompt overflow must not happen if the gate is correct; if the server still 400s, existing `provider_error`.
- External TCP → existing network audit hard-fail.

## Tests (TDD)

Offline FakeLLM tests, injected tokenizer + `n_ctx`:

1. Under cap: no `index.search`; excerpt count == `len(store.chunks)`; aliases `K1…Kn` in document/page order; user prompt is UTDRAG then FRÅGA.
2. Over cap, or no `n_ctx`: retrieval path, `FRÅGA` first, `topK` excerpts.
3. `minRelevance=1.0` still reaches the LLM on the full-corpus path (gate bypassed). Same setting still refuses on the retrieval path.
4. `CitationOut.score is None` on full-corpus; float on retrieval. `RetrievalHit` zeros + `rerank_score is None`.
5. Prefix hash identical for two different questions on the same unchanged tenant; changes when a document is added.
6. `len(rendered excerpts) == len(store.chunks)` on the full-corpus path (catches a leftover `topK` cut).
7. Planned path does not call the planner when the archive fits.
8. `DeterministicTestLLM` still answers under both prompt orders.
10. Missing `n_ctx`: retrieval path **and** a WARN log (not silent).
11. Bound log: archive over threshold → `bound=threshold`; under threshold but over `n_ctx` → `bound=n_ctx`; both hold → `bound=fits`.
12. `CitationOut(...)` without `score=` is a validation error (no default).

Do not require llama.cpp for the offline suite. Live measurement and before/after runs use the self-hosted endpoint with the network audit.

## Verification (live, this host)

1. `make test` before and after (offline).
2. Copy the 10 real PDFs into gitignored local `DONT_PUSH_brf_stuff/` (PDFs only).
3. Run the token script; keep only numeric stdout / gitignored JSON.
4. Run `scripts.reality.annual_reports` and the other reality README entry points **as they are** (retrieval; `fullCorpusTokenThreshold=0` after the change, or `main` before it), then again with the gate on, **same documents and same questions**. Emit a **case table** (document × question): verified/refused before → after. Headline: count of verified→refused. The 10-PDF association is the live corpus for token measurement and for that before/after once ingested as one tenant.
5. On the opt-in bucket mode for the full-corpus run: assert containment `retrieval_miss == 0` where answer-bearing rows exist.
6. Report the **effective** cap the numbers support (`n_ctx` vs the 32000 knob), plus spill, plus whether Q2 `prompt_n` actually dropped.

## Invariants

- No non-loopback network.
- Nothing derived from a real document is committed.
- Citation chain and numeric gate unchanged.
- Retrieval path unchanged above the cap.
- Code in English; user-facing strings and commit messages in Swedish.

## Success

- Small archives that fit skip retrieval and still produce verifier-accepted citations.
- Large archives behave as they do on `main` today.
- Second question against an unchanged archive is **measured**. Warm prefill is a success only if `prompt_n` drops; otherwise the report records that this server does not cache prefixes.
- `retrieval_miss` is empty on the opt-in full-corpus bucket run whenever the fact is in the document.
- The written report states per-association token numbers, the before/after table from the existing rigs, the threshold those numbers support, and what broke along the way.
