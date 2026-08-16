# n_ctx cost (A) and document-level ask path (B)

Date: 2026-08-16
Branch / worktree: `feat/full-corpus-ask` at `.worktrees/full-corpus-ask`
Approved approach: **measure n_ctx empirically with a three-depth needle, then add a third `ask()` path that packs whole documents only when the top-scoring document fits**

This spec extends `docs/superpowers/specs/2026-08-16-full-corpus-ask-design.md`. Gate A (full archive) is unchanged. Nothing here raises the installed llama.cpp `-c 16384`.

## Problem

On this host, `n_ctx=16384` is the bound that keeps almost every association archive on chunk retrieval. Effective prefix cap is **14072** (`16384 − 512 − 1800`). Measured 2026-08-16 with the generator tokenizer:

| Corpus | prefix_tokens | bound at 16384 |
| --- | --- | --- |
| One association, 10 PDFs | 54539 | threshold (n_ctx would miss too) |
| One annual report | 19161–24936 | n_ctx |
| One stadgar PDF | 7476 | fits |

Two questions follow, and they must not be mixed.

**A.** What does raising `n_ctx` to 32768 or 65536 *cost* on `gemma4:e12b` here — memory, prefill, stability — and does quality actually hold once the context is *full*? Gemma 3 RULER numbers are not a bound on this model.

**B.** Whole *documents* fit long before the whole *archive*. A third path should retrieve at document granularity and put 1–3 whole documents in the prompt, under the same effective cap as gate A.

## Goal

1. **A — measurement only.** Temporarily run the production image at `-c 16384|32768|65536`, record cost and a three-depth needle table, restore `-c 16384`. Recommend one n_ctx from that needle table plus cost, not from “the server started”.
2. **B — product path.** When the archive does not fit, score documents, and if **and only if** the top-scoring document’s full render fits, pack that document and then as many of the next as fit (max 3). Otherwise today’s chunk retrieval. Same excerpt renderer, question last, same citation and numeric gates, `CitationOut.score = None`.

## Non-goals

- Changing the tracked `docker-compose.yml` or leaving llama.cpp at a non-16384 `-c` after A.
- Treating Gemma 3 RULER (80.3 @ 32k / 57.1 @ 128k) as evidence for Gemma 4 12B.
- Using “Vad heter föreningen?” / “Var har styrelsen sitt säte?” as the n_ctx quality verdict. Those already verified at 16384; they will pass at every window and say nothing about loss in a *filled* context.
- Skipping a too-large top document and answering from document #2.
- Evaluating B’s two-document questions at 16384 (stadgar 7476 + annual report 19–25k = 26–32k > 14072). That comparison is structurally retrieval-vs-retrieval.
- New Settings knobs. `fullCorpusTokenThreshold=0` already forces retrieval; it also disables the document path.
- Stabilising prefix-KV on the document path (selection changes per question).
- Changing citation resolution, numeric grounding, highlight rects, or excerpt label format.
- Network traffic outside loopback. Committing anything derived from a real document (filenames, quotes, needle-unrelated PDF text). Numbers, synthetic canaries, and anonymised doc ids only.

## Runtime facts (this host)

- RTX 4070 12 GB. llama.cpp `b9976`, `ghcr.io/ggml-org/llama.cpp:server-cuda`, GGUF `gemma-4-12b-it-UD-Q4_K_XL`, `--n-gpu-layers 99`, `--cache-type-k q8_0`, `--cache-type-v q8_0`, `--parallel 1`, port `127.0.0.1:8000`.
- Compose: `/home/simon/llama-cpp/docker-compose.yml` (`-c 16384`). A uses a **gitignored** override for `-c` only; the tracked file is not edited. Last step of A is `docker compose up -d` with no override and a health check that `/props` again reports 16384.
- Tokenizer / `n_ctx` read path: unchanged (`GET {origin}/props`, `POST {origin}/tokenize`).
- Real PDFs: gitignored `DONT_PUSH_brf_stuff/` (10 PDFs, copied earlier). Never commit them.

---

## A — cost of higher n_ctx

### Protocol

One n_ctx at a time, same image and weights. Order: 16384 (baseline), 32768, 65536. If a value does not start or OOM, record that and skip its needle/prefill rows. Do not run two servers; one GPU.

Override shape (do not commit):

```yaml
# gitignored, e.g. /tmp/llama-nctx-override.yml
services:
  llama-server:
    command: >-
      -m <same GGUF path as compose>
      --host 0.0.0.0 --port 8000
      -c <N>
      --n-gpu-layers 99 --jinja --reasoning off
      --cache-type-k q8_0 --cache-type-v q8_0
      --no-mmap --parallel 1 --temp 1.0 --top-p 0.95 --top-k 64
```

`docker compose -f docker-compose.yml -f /tmp/llama-nctx-override.yml up -d` then wait until `GET /props` → `default_generation_settings.n_ctx == N`.

### Cost columns (every n_ctx that started)

Record at two points: **loaded** (model up, no prompt yet) and **full** (immediately after the needle haystack prefill).

| Field | Source |
| --- | --- |
| started | container healthy, `/v1/models` 200, `/props` n_ctx matches N |
| stable | still healthy 2 minutes after full prefill; a 16-token completion still succeeds |
| vram_loaded_mib, vram_full_mib | `nvidia-smi --query-gpu=memory.used` |
| ram_loaded_mib, ram_full_mib | `docker stats --no-stream` for `llama-server` |
| kv_full | llama.cpp `/slots` or `/metrics` if a KV/cache byte field exists; otherwise `vram_full − vram_loaded` and say so |
| prompt_n, prompt_ms, cache_n | `timings` on the first needle question (cold prefill of a prompt that fills the window) |

Haystack length: tokenize filler until `haystack_tokens + question_reserve_short ≈ n_ctx − 256` (leave template + short answer). Filler is **synthetic** repeating prose that does not contain any canary. Not association PDFs.

### Quality columns — RULER-lite (this is the verdict)

Trivial product questions do not measure long-context loss. Degradation shows only when the answer sits **deep in a filled context**.

Build **one** haystack per n_ctx. Insert **three unique canaries** at token offsets `⌊0.10 L⌋`, `⌊0.50 L⌋`, `⌊0.90 L⌋` of the haystack (not of n_ctx). Each canary is a code that cannot appear in the filler, e.g. `NEEDLE10-A7K3M2` at marker ALPHA, `NEEDLE50-P9Q4W1` at MID, `NEEDLE90-Z2R8C5` at OMEGA.

Three chat completions against that **same** haystack, question last:

1. `Vilken kod står vid markören ALPHA?`
2. `Vilken kod står vid markören MID?`
3. `Vilken kod står vid markören OMEGA?`

Q1 is the cold prefill used for cost. Q2/Q3 may hit prefix cache; log `prompt_n` / `cache_n` but do not treat cache as a quality signal.

**Hit** = the exact canary for that depth appears as a substring of the completion. Miss = anything else (wrong canary, refuse, garbage). Do **not** run this through `ask()`, citations, or the numeric gate — there is no PDF. Raw loopback chat completions.

Table that **decides** useful n_ctx (not which values started):

| n_ctx | started | 10% | 50% | 90% | vram_full_mib | prompt_ms Q1 |
| --- | --- | --- | --- | --- | --- | --- |
| 16384 | | | | | | |
| 32768 | | | | | | |
| 65536 | | | | | | |

Offline tests (no GPU): haystack builder places canaries at 10/50/90% of a known token length; a stub tokenizer (`count = len(text.split())`) is enough. The live run is the measurement.

### What A does *not* use for the n_ctx recommendation

- Stadgar name/seat questions (already verified; will pass everywhere).
- Annual-report `ask()` at a given n_ctx (confounds window size with retrieval vs full-document routing). Product-path behaviour belongs in B.

Those questions may appear in B’s tables. They are not A’s quality metric.

### Recommendation rule (apply in this order)

1. Discard n_ctx that did not start or did not stay stable.
2. Discard n_ctx whose 90% needle missed, if a smaller started n_ctx hit 90%. A larger window that loses the deep needle is not “more useful”.
3. Among remaining, prefer the **smallest** n_ctx that hits all three depths.
4. If none hit all three: prefer the n_ctx that hits the deepest depth; ties → smaller n_ctx.
5. If 65536 started but `vram_full` leaves less than ~1 GiB free on the 12 GB card, or the process OOMs on the second question, disqualify 65536 even if needles hit.
6. Prefill time is a cost to report, not a veto unless Q1 `prompt_ms` makes the path unusable in practice (record the number; the written recommendation may call out e.g. “32k hits 90% but cold prefill is N seconds”).

Write the recommendation and which rows it rests on into `docs/evidence/nctx-cost.md` (numbers only). Restore `-c 16384` before starting B’s live runs, then temporarily raise again **only** for B’s two-document slice at the recommended n_ctx, and restore again.

---

## B — whole documents between archive and chunks

### Routing in `ask()` (after empty-corpus, after `evidence=` short-circuit, before chunk topK)

`fullCorpusTokenThreshold=0` → retrieval, both new paths off (before/after switch). Missing `n_ctx` / tokenizer error → retrieval + existing WARN.

Otherwise:

1. **Gate A (unchanged).** Archive fits → full-corpus path (no search, all chunks, question last).
2. **Document path.** Archive does not fit. Wide hybrid search, score documents, test whether the **top** document’s full render fits the same effective cap as gate A (`n_ctx − 512 − (maxResponseLength + 600)`).
   - Top does **not** fit → **chunk retrieval** (today’s path, `FRÅGA` first). Log `ask_path=retrieval bound=top_document_n_ctx`. Do not pack document #2.
   - Top fits → pack top, then #2 and #3 in score order **only if each added document still fits**. Skip a later document that does not fit; never drop top to make room for a smaller later one. Max 3. Question last. Log `ask_path=documents n_docs=… prefix_tokens=…`.
3. **Chunk retrieval.** Default when step 2 packed nothing (should not happen if top-fit is the gate) or search returned no hits.

`append_linked_table_legends` and rerank do not run on the document path (selected documents are already whole). `minRelevance` is bypassed; `_synthesize(..., low_relevance=False, full_corpus=True)` so prompt order and `CitationOut.score=None` match gate A. Hit scores on the packed chunks are the full-corpus contract: `0.0` / `rerank_score=None`.

Search **does** run (unlike gate A): it is how documents get scores. Widen `top_k` to `len(chunks)` (and `candidates` to at least that) so aggregation is not starved by `topK=6`.

### Scoring (rank by max; report both)

For each `document_id` in the wide hit list:

| Field | Definition |
| --- | --- |
| `max_score` | `max(hit.score)` among that document’s hits. **This is the rank key.** |
| `n_matching_chunks` | Count of hits from that document in the same list. |

Tie-break for rank: `(-max_score, document_name, document_id)`.

`n_matching_chunks` is **not** the rank key. Sum-of-scores is not used (it favours long PDFs). Both numbers are written on every live case so a later pass can check whether max-rank picked a one-chunk fluke while another document had many matching chunks. Re-ranking by `n_matching_chunks` is out of scope until that report says so.

Committed evidence anonymises documents (`doc_01`, kind `stadgar|annual_report|other`). Gitignored JSON may keep filenames.

### Packing fit

A candidate set of documents fits when `prefix_tokens + 512 + response_budget <= n_ctx`, where `prefix_tokens` is tokenize(`system + "\n\nUTDRAG:\n" + _render_excerpts(chunks of those documents in document/page order)`). Same `hits_for_full_corpus` sort key, filtered to the packed document ids.

Per-document token sums may be cached on `Store` and invalidated on `_rebuild` / settings change, same as archive sums.

### Planner

`ask_planned`: if gate A would fire, skip planner (already implemented). If gate A would not fire but the document path **would pack** (top document fits), skip planner too — otherwise `evidence=` bypasses the new branch. If top does not fit, planner + chunk retrieval as today.

### Prefix cache

Document selection changes with the question. Q2 `prompt_n` is **not** expected to collapse. Log timings. Do not add a stable dummy prefix or reorder documents to fake a cache hit.

### Offline tests (TDD, FakeLLM + stub tokenizer)

1. Two small docs under cap, archive over threshold: document path runs; excerpts are **all** chunks of the packed docs, not `topK`; user prompt is UTDRAG then FRÅGA; `CitationOut.score is None`.
2. `threshold=0`: retrieval, FRÅGA first, even if docs would fit.
3. Top document’s render does not fit; a smaller second document would: **retrieval**, not the second document. Bound log `top_document_n_ctx`.
4. Top fits, second does not, third does: pack top (+ third if it still fits). Never pack second instead of top.
5. Archive itself fits: gate A still wins (no search).
6. Missing `n_ctx`: retrieval + WARN.
7. `ask_planned` does not call `plan_query` when the document path would pack.
8. Score helper returns both `max_score` and `n_matching_chunks` per document; sort order is max_score.

Do not require llama.cpp for `make test`.

### Live comparison

Reuse `compare_ask_cases.py`. Headline remains **verified → refused** (and refused → verified). Totals are not the story.

**One-document slice — at installed 16384**, 10-PDF tenant, `threshold=0` (retrieval) vs default (document path). Questions (generic, not taken from the PDFs):

- `q_name`: Vad heter föreningen?
- `q_seat`: Var har styrelsen sitt säte?
- `q_interest`: Hur stora var föreningens räntekostnader under året?
- `q_solidity`: Hur stor är föreningens soliditet i procent?

Stadgar-sized top hits can pack. Annual-report top hits at 16384 usually **cannot** (19–25k > 14072) and **must** fall back. Those fallback cases are not a document-path quality measurement; they are the **top-miss** count.

Report for this slice:

- per case: path actually used, top document kind, `max_score`, `n_matching_chunks` for the top 3 scored documents, packed n_docs, verified/refused
- **`top_miss_rate`**: fraction of cases where top did not fit. This is a primary number, not a footnote.
- `verified_to_refused` / `refused_to_verified` **restricted to cases that actually packed**, and the same pair overall (overall will mix fallbacks)

**Two-document slice — at the n_ctx A recommended**, not at 16384. Same 10-PDF tenant. Temporarily raise `-c` to that value, run, restore 16384.

Questions that need two documents:

- `q_fund_vs_stadgar`: Vad säger stadgarna om avsättning till underhållsfond, och hur mycket fanns avsatt enligt årsredovisningen?
- `q_notice_vs_meeting`: Vilken kallelsetid till stämman gäller enligt stadgarna, och vilket datum hölls senaste stämman enligt årsredovisningen?

If A’s recommended n_ctx still cannot fit stadgar + one annual report (26–32k prefix), **do not** publish a retrieval-vs-documents table for these two questions. Write that packing is impossible at the recommended window and stop. That is a finding. Only if both documents can pack is the before/after a document-path measurement.

If A recommended 16384, the two-document slice is that finding by construction.

Cache behaviour: log Q1 vs Q2 `prompt_n` / `cache_n` on the document path (expected: no shared prefix).

Network audit: loopback only; hard-fail otherwise.

## Components

| Unit | Responsibility |
| --- | --- |
| Needle haystack builder | Synthetic filler + canaries at 10/50/90% token offsets; unit-tested |
| n_ctx measure script | Override `-c`, cost probes, three needle questions, restore 16384 |
| Document scorer | Wide search → per-doc `max_score` + `n_matching_chunks`; rank by max |
| Packer | Top must fit or retrieval; then greedy add #2/#3 if they fit; max 3 |
| `ask()` branch | After gate A, before chunk topK; score contract as full-corpus |
| Planner skip | When packer would pack |
| Live reports | One-doc @ 16384; two-doc @ A’s n_ctx; `top_miss_rate`; both score fields |

## Error handling

- Override failed / OOM: record `started=false`, do not leave a crashed container; restore 16384.
- Tokenizer / `n_ctx` unavailable at ask time: existing WARN + retrieval.
- llama.cpp 400 on prompt overflow: existing `provider_error` (a packer bug if the fit check was right).
- External TCP: hard-fail.

## Invariants

- No non-loopback network.
- Nothing derived from a real document is committed.
- Citation chain and numeric gate unchanged.
- Retrieval path byte-for-byte when `threshold=0`, `n_ctx` missing, tokenizer error, or the top-scoring document does not fit.
- Code in English; user-facing strings and commit messages in Swedish.
- Installed `-c` is 16384 when A/B live work is finished.

## Success

- Needle table exists for every n_ctx that started. The written n_ctx recommendation cites that table (especially 90% depth) and the memory/prefill columns, not “65536 booted”.
- Document path never answers from #2 because #1 was too large; live `top_miss_rate` is reported.
- One-doc before/after at 16384 is a case table with packed-only headline numbers.
- Two-doc before/after runs only at A’s recommended n_ctx, and only if packing two docs is possible; otherwise the report says so.
- `make test` stays green. Retrieval tests that do not inject a fitting runtime stay on retrieval.
