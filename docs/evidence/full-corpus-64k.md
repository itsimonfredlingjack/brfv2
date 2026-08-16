# Helarkivväg mot retrieval vid n_ctx=65536 — 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Modell:** Gemma 4 12B IT · tillfällig `-c 65536` · restore `/props` **16384** · embedder `model2vec:potion-multilingual-128M`

> **Enkörning.** Headline och per-fråge-tider är en körning. Spann för BRF-1:s elva fall: `docs/evidence/brf1-variance.md`.

Gate A eldade på föreningens 10 PDF:er för första gången. `chunk_tokens=48923`, `prefix_tokens=54539`, `bound=fits` vid `threshold=100000` (produktens default 32000 skulle fortfarande bundit på tröskeln; den knoppen ändrades inte i git). Retrieval-före: `threshold=0`.

Headline per fall: **`verified_to_refused=0`**, `refused_to_verified=0`. Alla tre efter-vägarna `full_corpus`.

Den rubriken räknade fel sorts träff. `compare_ask_cases` sätter `verified` = inte vägrad. Facit för `q_name` / `q_seat` / `q_notice` är stadgarna. Körningens JSON sparade inte vilken handling citatet pekade på, så fallen kan inte delas i `verifierat_i_facit` / `verifierat_i_fel_handling` / `vägrad` efteråt. Nollan betyder "ingen vägran tillkom", inte "rätt handling". Samma rubrik hade räknat BRF-1:s R7b som vinst — ett verifierat citat ur fel handling, se `docs/evidence/brf1-full-corpus.md`.

| qid | retrieval refused | full_corpus refused | cites r/f | retrieval s | full_corpus s | retrieval prompt_n | full_corpus prompt_n | full_corpus cache_n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q_name | no | no | 1/1 | 3.184 | 33.272 | 3126 | 54016 | 550 |
| q_seat | no | no | 1/1 | 2.734 | 2.032 | 2421 | 17 | 54552 |
| q_notice | no | no | 1/1 | 5.314 | 4.275 | 2480 | 25 | 54552 |

Kall prefill ~30.7 s (`prompt_ms=30676`). Fråga två och tre: `prompt_n` 17 och 25, `prompt_ms` ~70 ms, `cache_n=54552`. Prefix-KV är poängen med vägen och den höll.

Frågorna är stadgar-formade (namn, säte, kallelsetid). Retrieval släppte också igenom dem utan vägran — det här är inte ett retrieval-miss-experiment. Det är evidens att arkivet **rymmer**, att vägen **eldar**, och att den andra frågan är billig. Ränte- och soliditetsfrågor väntade på en årsredovisning som inte fanns i de 10 PDF:erna; den ligger nu i arkivet som J (`docs/evidence/brf1-annual-report.md`) men är inte omkörd här. Att båda vägarna inte vägrade är inte `verifierat_i_facit`.

Drift efter den här mätningen (65536 i compose, tröskel `None`, förvärmning, sidordning): `docs/evidence/nctx-ops-65536.md`.
