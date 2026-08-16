# Helarkivväg i `ask()` — mätning 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Modell:** Gemma 4 12B IT via llama.cpp `b9976` · `n_ctx=16384` · tokenizer `POST {origin}/tokenize`

Effektiva taket är **14072** prefix-token (`n_ctx − 512 − 1800`), inte defaultknappen `fullCorpusTokenThreshold=32000`. På den här hosten binder `n_ctx` så fort tröskeln släpper igenom.

Offlinesvit: `make test` → 1354 passed, 62 skipped.

## Tokenvolym (samma tokenizer som generatorn)

Spill = `chunk_token_sum − unique_tokens`. Unique använder `" ".join(w.text for w in page.words)` — samma join som `chunker.chunk_pages`.

| Arkiv | dokument | sidor | chunkar | chunk_token_sum | unique_tokens | spill | prefix_tokens | bound |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| En förenings 10 PDF:er (platt mapp) | 10 | 123 | 150 | 48923 | 45216 | 3707 | 54539 | threshold (n_ctx skulle också missa) |
| Fyra sample-årsredovisningar, var för sig | 1 | 20–32 | 38–54 | 17661–23224 | 15760–20988 | 1664–2236 | 19161–24936 | n_ctx (under 32000, över 14072) |
| Ett stadgedokument | 1 | 11 | 20 | 6554 | 5800 | 754 | 7476 live / 7656 mätscript | fits |

Live-prefixet 7476 mot mätscriptets 7656 är samma dokument med olika `document_name` i utdragsetiketten, inte olika tokeniserare.

## Live före/efter (stadgarna — enda arkivet som rymdes)

Två generiska frågor, `minRelevance=0`, samma Gemma. Headline: **`verified_to_refused=0`**, `refused_to_verified=0`. Båda verifierade före och efter.

Den rubriken räknade fel sorts träff (`verified` = inte vägrad). Här råkar den sammanfalla med `verifierat_i_facit`: arkivet är ett enda stadgedokument, så varje godkänt citat är ur facithandlingen. Det är inte evidens för att samma rubrik håller mot ett blandat arkiv.

| fall | facit | retrieval | helarkiv |
| --- | --- | --- | --- |
| q_name | stadgar | verifierat_i_facit | verifierat_i_facit |
| q_seat | stadgar | verifierat_i_facit | verifierat_i_facit |

| Väg | threshold | hits | Q1 elapsed_s | Q2 elapsed_s |
| --- | --- | --- | --- | --- |
| retrieval | 0 | 6 | 2.813 | 2.699 |
| helarkiv | 32000 | 20 | 4.956 | 1.580 |

llama.cpp timings (helarkiv, fråga sist):

- Q1: `prompt_n=6953` `prompt_ms=2883.766` `cache_n=550`
- Q2: `prompt_n=17` `prompt_ms=61.646` `cache_n=7489`

Prefix-KV **träffade** när utdragen var ett sant prefix. Retrievalvägen (fråga först) delar inte prefix: Q2 `cache_n=550`. En tidigare stickprovsmätning med ~442 delade token och `cache_n≈11` gäller alltså inte den här promptformen.

Årsredovisningsriggens fyra default-PDF:er kördes inte dubbelt mot Gemma: alla binder på `n_ctx`, så före/efter hade varit samma retrievalväg.
