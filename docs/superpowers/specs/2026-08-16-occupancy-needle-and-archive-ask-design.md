# Occupancy needle, archive ask, production embedder

Date: 2026-08-16
Branch / worktree: `feat/full-corpus-ask` at `.worktrees/full-corpus-ask`
Extends: `docs/superpowers/specs/2026-08-16-nctx-cost-and-document-ask-design.md`

Nothing here tears down the document path, packer, or the filled-window driver. Those stay. This corrects the **measurement** that decided useful `n_ctx`, then uses a 65536 window only if that correction says the archive can hold facts.

## Problem

The first needle filled every window to ~99 %. The three depths measured **saturation at three sizes**, not “does the model hold a fact at depth when the window is not full”. Prefill and VRAM of `-c 65536` were real; the quality table was the wrong experiment. The 16384 recommendation (`deepest_then_smallest`, only 10 % hit) is therefore provisional.

Document-path live used `BRF_EMBEDDER=hashed`. Ranking **is** path B. Those `max_score` numbers are stub noise. `q_interest` / `q_solidity` were asked against a tenant with no annual report.

## Goal (three steps, in order)

1. **Occupancy needle.** Fix `-c 65536`. Vary haystack length: 8k, 16k, 32k, 48k, 62k tokens. Canaries at 10/50/90 % of each haystack. Report hit per `(haystack, depth)`. Filler is **synthetic årsredovisningsstruktur** (headings + cycling financial vocabulary), not `lorem` and not association PDFs. Association text is its own error source.
2. **If the needle holds:** fire gate A on the real 10-PDF archive at `-c 65536`. Prefix was 54539; effective cap at 65536 is ~63224. Cold prefill once, warm on Q2/Q3. Before/after vs retrieval **per case**. Override via gitignored compose; restore 16384; do not edit the tracked compose file.
3. **Document path with production embedder** (`model2vec`). One-doc slice at restored 16384. Do not treat hashed scores as B evidence.

## Occupancy protocol

Same canaries, same hit rule (exact substring), same raw chat completions (not `ask()`). Question last. Q1 is cold for that haystack; Q2/Q3 may cache — log `prompt_n` / `cache_n`, not as quality.

After the 65536 sweep, restore 16384 and run **one** 16k structured haystack as control.

| Comparison | Isolates |
| --- | --- |
| 16k structured @ 65536 vs 16k structured @ 16384 | occupancy vs length (same filler) |
| 16k structured @ 16384 vs old 16k `lorem` @ 16384 | filler vs `lorem` (same window) |

If 16k in a 64k window hits a depth that 16k in a 16k window missed, occupancy — not length — explained the old miss, and the filled-window recommendation is invalid.

Keep `--mode filled-window` so the old saturation sweep stays reproducible. Default live run is `--mode occupancy`.

### “Needle holds” (gate for step 2)

All of:

- 65536 started and stayed stable, GPU free ≥ 1024 MiB after the last haystack.
- The **48k** haystack (nearest the 54539 archive prefix) hits **at least one** of 10/50/90 %.

If 48k misses all three, do not raise `-c` for the real archive. Write that. Prefill time is a cost column, not a veto unless Q1 at 48k/62k is unusable.

Do not use `recommend_nctx` on occupancy rows (that function ranks **windows**, not haystacks).

## Archive live (step 2 only)

Temp store. `threshold=0` → retrieval. After: `fullCorpusTokenThreshold=100000` so **n_ctx** is the bound under test (product default 32000 would still bind this archive on `chunk_token_sum=48923` even at 65536). Do not change `Settings` default in git.

Questions that this tenant can actually support (generic, not copied from PDFs): `q_name`, `q_seat`, and one stadgar-shaped third (`q_notice`) for a second warm hit. **Not** `q_interest` / `q_solidity` until an annual report exists.

Log Q1 `prompt_n`/`prompt_ms`/`cache_n` (cold) and Q2/Q3 (expect prefix collapse on gate A). Headline remains per-case verified→refused, not totals.

## Annual report in the 10-PDF tenant

Filename classifier: `stadgar` / `årsred|arsred|årsr|arsr` / else `other`. Checked 2026-08-16: **no filename is an annual report**. One born-digital förvaltningsavtal mentions the word in body text; it is still an avtal. Eight PDFs have no text layer (scans, including stadgar). A 3-page print job is not an annual report. **The document is missing, not misclassified.** Interest/solidity wait until a real annual report is added. Do not “fix” the classifier to look inside PDFs.

## Document-path rerun (step 3)

`BRF_EMBEDDER=model2vec`, `HF_HUB_OFFLINE=1`, weights from the local HF cache / `BRF_MODEL2VEC_PATH`. Hard-fail if the provider is hashed unless `--allow-hashed`. Same one-doc questions as before, but `q_interest`/`q_solidity` are **not** B evidence until the annual report exists; they may be omitted. Report `top_document_kind`, `max_score`, `n_matching_chunks` from model2vec. Prefill cost (4–6×, `cache_n≈550`) from the hashed run remains a valid cost observation.

## Non-goals

- Editing tracked `/home/simon/llama-cpp/docker-compose.yml`.
- Leaving llama.cpp off 16384.
- Changing packer / top-must-fit / rank-by-max.
- Committing PDF text or filenames.
- Raising product `fullCorpusTokenThreshold` default.

## Success

- Evidence table: hit per `(hay_tokens ≈ 8k|16k|32k|48k|62k, depth)` at `-c 65536`, plus 16k @ 16384 control.
- Written verdict: occupancy vs length, and whether the old 16384 recommendation stands.
- If the 48k gate passed: archive before/after case table with cold/warm timings; `/props` 16384 afterwards.
- If it failed: no fake archive table.
- Document-path numbers from model2vec, or an explicit skip of financial questions because the annual report is absent.
- `make test` green. Loopback only.
