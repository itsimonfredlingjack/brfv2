# Dokumentväg mot retrieval — mätning 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=16384` efter restore

Första körningen använde `BRF_EMBEDDER=hashed`. Rankningen **är** dokumentvägen; de talen är stubbrus och ska inte användas som B-kvalitet. Kostnaden (prefill, `cache_n`) från den körningen är däremot giltig.

Omkörning: `model2vec:potion-multilingual-128M`, bara frågor korpusen kan bära (`q_name`, `q_seat`). Ränta/soliditet kördes inte om.

## Årsredovisning: saknas, inte felklassad

Filnamnsklassificeraren (`stadgar` / `årsred|arsred|årsr|arsr` / `other`) fick aldrig `annual_report`. Det är inte en bugg som döljer sig som korpusfaktum.

De 10 PDF:erna är stadgar, underhållsplan, förvaltningsavtal, övriga avtal och en 3-sidig utskrift. Ett born-digital förvaltningsavtal nämner ordet årsredovisning i brödtexten; det är fortfarande ett avtal. Åtta filer saknar textlager (skannade, inklusive stadgarna). En 3-sidig utskrift är inte en årsredovisning.

**Dokumentet saknas.** q_interest / q_solidity och två-dokumentsfrågorna väntar på en riktig årsredovisning.

## En-dokumentssnitt @ 16384 — model2vec (giltig rankning)

`threshold=0` mot default 32000. Headline packed-only: **`verified_to_refused=0`**, `refused_to_verified=0`. **`top_miss_rate=0.0`**. Topp dokument: stadgar båda frågorna.

| qid | retrieval refused | documents refused | packed | top kind | top max_score | top n_chunks | retrieval s | documents s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q_name | no | no | 2 | stadgar | 0.9775 | 20 | 3.436 | 8.289 |
| q_seat | no | no | 3 | stadgar | 0.9941 | 20 | 2.732 | 6.559 |

Övriga poäng (max_score / n_matching_chunks):

- q_name: stadgar 0.9775/20, other 0.6709/27, other 0.6155/18
- q_seat: stadgar 0.9941/20, other 0.6295/5, other 0.5998/4

Namn/säte är triviala och verifierade båda vägarna (1 citat). Rankningen sätter stadgar överst med tydlig marginal mot `other`. Det är inte ett test av topp-miss på 19–25k-dokument.

Dokumentväg timings (ingen prefix-kollaps mellan frågor):

| qid | prompt_n | prompt_ms | cache_n |
| --- | --- | --- | --- |
| q_name | 12931 | 5571.721 | 550 |
| q_seat | 10570 | 4493.446 | 550 |

Prefill 4–6× retrieval. `cache_n=550` är systemprefix.

## Hashed-körningen (ogiltig som B-kvalitet; giltig som kostnad)

Samma prefill-mönster: `prompt_n` 10–13k, `cache_n=550` varje gång. `q_interest`/`q_solidity` vägrades båda vägarna mot en korpus utan årsredovisning — det mäter inte retrieval mot dokumentväg. Hashed `max_score` 0.9928 / 0.8137 är brus.

## Två-dokumentssnitt

Vid 16384 ryms inte stadgar + årsredovisning. Vid 65536 skulle 26–32k prefix rymmas under ~63224, men årsredovisningen saknas så tabellen utelämnas fortfarande.

Helarkivvägen eldade däremot på hela de 10 PDF:erna vid 65536 — se `docs/evidence/full-corpus-64k.md`.
