# BRF-1: fem körningar — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit före körning:** `2644150` · **embedder:** `model2vec:potion-multilingual-128M` · loopback · `scripts/eval_brf1_variance.py`

Samma elva fall, samma nio handlingar, samma beskrivningar som `docs/evidence/brf1-doc-path-desc.md`. Svarsdomaren är inkopplad. Ingen default ändrades.

Sampling: `temperature: 0` i requesten, `top_p` och `seed` skickas inte. Serverns `--temp 1.0` vinns över. Se `docs/evidence/brf1-sampling.md`. Femkörningen *är* mätningen vid noll. Ingen andra matris.

Måttet är treutfall mot facithandling (`verifierat_i_facit` / `verifierat_i_fel_handling` / `vägrad`), samma som grindkörningen. Det är inte det handklassade fyrutfallet (besvarar / ofullständigt / fel handling / vägrad).

110 `ask()`. Noll externa anslutningar. `fullCorpusTokenThreshold` återställd till `None` efteråt.

## Spannet

| väg | facit av 11, fem körningar | fel handling | vägrad |
| --- | --- | --- | --- |
| dokumentväg | **6–6** (6, 6, 6, 6, 6) | 1–1 | 4–4 |
| retrieval | **5–5** (5, 5, 5, 5, 5) | 1–1 | 5–5 |

Gällande tal: dokumentväg **6 facit** mot retrieval **5 facit** över fem körningar. Spannet är 6–6 mot 5–5.

**4 → 8** i `docs/evidence/brf1-doc-path-desc.md` var enkörning utan domargrind (handklassat). De tidigare talen är märkta där som just det.

Inom de fem körningarna rörde sig inte treutfallet. Ett fall bytte bara hur många E-citat som accepterades (R4 dokumentväg: tre citat i körning 1, ett citat i körning 2–5). Fortfarande facit.

Tidigare BRF-1-siffror i evidensen är enkörning. De är märkta där de står.

## Dokumentväg, per fall (av fem)

| fall | facit | fel handling | vägran | utfall varje körning | grind (körning 1) |
| --- | ---: | ---: | ---: | --- | --- |
| R1 | 0 | 0 | 5 | vägrad ×5 | `citation_contradicted` |
| R2 | 5 | 0 | 0 | facit ×5 | — |
| R3 | 5 | 0 | 0 | facit ×5 | — |
| R4 | 5 | 0 | 0 | facit ×5 | numerisk reparation `2024` |
| R5 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R6 | 0 | 5 | 0 | fel handling ×5 (C) | — |
| R7 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R8 | 5 | 0 | 0 | facit ×5, alltid markerat | `besvarar_inte` |
| R3b | 5 | 0 | 0 | facit ×5 (G) | — |
| R5b | 5 | 0 | 0 | facit ×5 | — |
| R7b | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |

R8 visades med *Svaret kan vara ofullständigt.* i alla fem. R1 fälldes av domaren i alla fem.

## Retrieval, per fall (av fem)

| fall | facit | fel handling | vägran | utfall varje körning | grind (körning 1) |
| --- | ---: | ---: | ---: | --- | --- |
| R1 | 0 | 5 | 0 | fel handling ×5 (D) | — |
| R2 | 5 | 0 | 0 | facit ×5 | — |
| R3 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R4 | 5 | 0 | 0 | facit ×5 | — |
| R5 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R6 | 5 | 0 | 0 | facit ×5 | — |
| R7 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R8 | 5 | 0 | 0 | facit ×5, alltid markerat | `besvarar_inte` |
| R3b | 5 | 0 | 0 | facit ×5 (G) | — |
| R5b | 0 | 0 | 5 | vägrad ×5 | `numeric_grounding_failed` |
| R7b | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |

Retrievals 5/1/5 i `docs/evidence/brf1-full-corpus.md` återkom identiskt i treutfall. Den handklassade baslinjen 4 besvarar är ett annat mått på samma sorts enkörning; den omklassades inte här.

## Vad nollan i spannet betyder

Requesten är redan greedy. Inom en tätt följd av fem körningar på samma process, samma store och samma prefixcache försvann treutfallsdriften.

Det är inte bevis att varje enkörning landar på samma fall. Grindkörningen samma dag (`docs/evidence/brf1-answer-judge.md`) var också 6/1/4 på dokumentvägen, men med R5 som fel handling (C) och R6 som vägrad. Här är det omvänt: R5 vägrad, R6 fel handling (C). Samma totalsumma, andra fall. Den skillnaden sitter *mellan* sessioner, inte i de fem körningarna. Urvalet i tjugo processer är 20/20 identiskt per fall (`docs/evidence/brf1-selection-stability.md`) — det är inte processgränsen.

R5/R7/R7b:s `insufficient_data` i femkörningen: facittexten fanns inte i prompten (`docs/evidence/brf1-refusal-prompt.md`).

Defaulten rördes inte. Ingen andra matris vid temperature 0 — det var redan noll.

## Produktfrågan

Ska ett citatbundet svar vara deterministiskt? Mot llama.cpp är requesten redan det, och femkörningen rörde inte treutfallet. Det som fortfarande kan skilja en enkörning från nästa är inte `--temp 1.0`.
