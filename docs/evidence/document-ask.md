# Dokumentväg mot retrieval — mätning 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Modell:** Gemma 4 12B IT via llama.cpp `b9976` · `n_ctx=16384` · tokenizer `POST {origin}/tokenize` · embedder `hashed`

Samma 10-PDF-arkiv som helarkivmätningen. Helarkivvägen binder fortfarande (`chunk_tokens=48923`, `prefix_tokens=54539` > 14072), så dokumentvägen är den enda nya `ask()`-grenen som kan elda här. Inga filnamn, inga PDF-citat.

A rekommenderade **16384** (`docs/evidence/nctx-cost.md`). `/props` n_ctx före och efter: **16384**. Ingen `-c`-override i den här mätningen.

## En-dokumentssnitt @ 16384

`threshold=0` (retrieval) mot default 32000 (dokumentväg). Fyra generiska frågor. Headline (packed-only): **`verified_to_refused=0`**, `refused_to_verified=0`. Overall samma. **`top_miss_rate=0.0`**.

Alla fyra fallen packade (`bound=fits`). Ingen årsredovisning i den här mappen (`top_document_kind` var `stadgar` eller `other`, aldrig `annual_report`), så 16384-miss på 19–25k-dokument observerades inte. Det är ett korpusfaktum, inte ett packerfel.

| qid | retrieval refused | documents refused | packed | top kind | top max_score | top n_chunks | retrieval s | documents s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q_name | no | no | 2 | stadgar | 0.9928 | 20 | 3.203 | 8.269 |
| q_seat | no | no | 3 | stadgar | 0.9665 | 20 | 2.496 | 6.598 |
| q_interest | yes | yes | 2 | other | 0.8137 | 41 | 1.854 | 7.471 |
| q_solidity | yes | yes | 3 | stadgar | 0.8842 | 20 | 1.959 | 6.328 |

Refusal på ränta/soliditet: `insufficient_data` båda vägarna (0 citat). Namn/säte: 1 citat båda vägarna. Retrieval `n_retrieval=6`; dokumentväg 29–45 (hela packade dokument).

llama.cpp timings, dokumentväg (förväntat: **ingen** prefix-kollaps mellan frågor — urvalet byts):

| qid | prompt_n | prompt_ms | cache_n |
| --- | --- | --- | --- |
| q_name | 12931 | 5558.831 | 550 |
| q_seat | 10570 | 4476.405 | 550 |
| q_interest | 13132 | 5685.596 | 550 |
| q_solidity | 10716 | 4603.566 | 550 |

`cache_n=550` är systemprefix, inte dokumentutdrag. Retrieval Q1 `prompt_n=2672` `cache_n=0`; Q2–Q4 `cache_n=550` med `prompt_n` 1652–2021.

Övriga poäng (max_score / n_matching_chunks) för de tre högst rankade, samma ordning båda körningarna:

- q_name: stadgar 0.9928/20, other 0.8171/27, other 0.7146/18
- q_seat: stadgar 0.9665/20, other 0.6982/27, other 0.6918/5
- q_interest: other 0.8137/41, stadgar 0.6927/20, other 0.5930/4
- q_solidity: stadgar 0.8842/20, other 0.7148/27, other 0.5453/4

Rankning är `max_score`. q_interest har högst chunk-antal på toppdokumentet (41) men lägre max än stadgar-frågorna.

## Två-dokumentssnitt

A rekommenderade 16384. Stadgarprefix ~7476 + en årsredovisning 19–25k = 26–32k > effektiva taket 14072. Packning av två hela dokument är **omöjlig** vid rekommenderat fönster. Ingen före/efter-tabell för `q_fund_vs_stadgar` / `q_notice_vs_meeting` — det vore retrieval mot retrieval. `-c` höjdes inte.

Samma mapp saknar dessutom `annual_report`, så de två frågorna hade inte kunnat packa stadgar+årsredovisning här ens om fönstret räckt.

## Slutsats

Dokumentvägen eldade på alla fyra en-dokumentsfallen vid 16384 utan att tappa verifierade svar eller släppa igenom ränte-/soliditetsfrågor som retrieval vägrade. Prefill blev 4–6× längre än retrieval (10–13k mot 1.6–2.7k prompt_n). Att höja `-c` för två-dokumentsfrågor motiveras inte av nåltabellen och skulle ändå inte rymma stadgar + årsredovisning vid 16384.
