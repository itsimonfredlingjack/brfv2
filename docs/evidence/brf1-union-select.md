# BRF-1: unionsurval hela vägen — två vyer, två urval, pack, `ask()` — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `d8e85e8` · loopback · `scripts/eval_brf1_union_select.py`

Fem körningar, 55 `ask()`. Låset `97b4e7bfc71f` skrevs inte om (`n_describe_calls=0`). Noll externa anslutningar. Vyer i `backend/out/brf1-union-select/` (gitignorerad). Den här filen har bokstäver, packstorlek och treutfall.

Två **fristående** beskrivningar per handling, olika genereringsprompt — inte fyra fält i samma text. Isolerat urval, en handling, mot vardera vyn (samma urvalsprotokoll som unionstestet 9/11). Unionen packades under dagens tokentak. Därefter produktens `ask()` (citat, numerik, svarsdomare). Ingen ny svarsväg i `app/answer.py`.

---

## Slutsats

Unionsvinsten låg i variation mellan genereringstillfällen, inte i vinkeln på genereringsprompten. Två medvetet olika vyer konvergerade och missade samma fall (R5 och R6 båda C). Vägen är inte bättre än den som redan är i produkt och ska inte skeppas.

| mått | baslinje | den här vägen |
| --- | ---: | ---: |
| facit i paketet | 9 / 11 (unionstestet, bara urval) | **7–7 / 11** |
| `verifierat_i_facit` | 6 / 11 över fem körningar | **6–6 / 11** |
| `verifierat_i_fel_handling` | 1 | **1–1** |

9/11 från unionstestet höll **inte** när vyerna var nygenererade med olika prompt. OR av två missar är en miss. Komplementet som bar 9/11 satt i två stickprov av samma slags produktbeskrivning (gammal cache mot lås), inte i att prompten bytte vinkel.

Fel-handling-citatet steg inte. Det enda `verifierat_i_fel_handling` är R6 ×5, citat ur C — samma fall och samma tal som femkörningen. R7 och R7b packade *två* fel handlingar; båda vägrades. Tokentaket kapade inget (`n_union = n_packed` i alla 55).

---

## Spannet

| | av 11, fem körningar |
| --- | --- |
| facit i paketet | **7–7** (7, 7, 7, 7, 7) |
| `verifierat_i_facit` | **6–6** (6, 6, 6, 6, 6) |
| `verifierat_i_fel_handling` | **1–1** (1, 1, 1, 1, 1) |
| `vägrad` | **4–4** (4, 4, 4, 4, 4) |

Treutfallet är identiskt med dokumentvägen i `docs/evidence/brf1-variance.md` (6/1/4), fall för fall. Det är under produktens 8–8 efter lås och borttaget räknetak (`docs/evidence/brf1-locked-pack.md`), där urvalet är 1–3 på låset och R5/R6 får E som fjärde handling.

---

## Per fall (av fem)

| fall | facit | a (reglerar) | b (frågor) | packat | n | prefix | facit i paket | treutfall |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| R1 | G | G | G | G | 1 | 2132 | ja | vägrad ×5 (`citation_contradicted`) |
| R2 | G | G | G | G | 1 | 2132 | ja | facit ×5 |
| R3 | G | G | G | G | 1 | 2132 | ja | facit ×5 |
| R4 | E | E | E | E | 1 | 2389 | ja | facit ×5 |
| R5 | E | C | C | C | 1 | 2532 | **nej** | vägrad ×5 |
| R6 | E | C | C | C | 1 | 2532 | **nej** | fel handling ×5 (C) |
| R7 | E | G | D | D, G | 2 | 11740 | **nej** | vägrad ×5 (`grounding_failed`) |
| R8 | E | E | E | E | 1 | 2389 | ja | facit ×5, alltid markerat |
| R3b | G | G | G | G | 1 | 2132 | ja | facit ×5 |
| R5b | E | E | E | E | 1 | 2389 | ja | facit ×5 |
| R7b | E | G | I | G, I | 2 | 13646 | **nej** | vägrad ×5 (`insufficient_data`) |

Urvalet var identiskt i alla fem körningar per fall. Prefix och `n_packed` rörde sig inte.

R5: en körning `insufficient_data`, fyra `numeric_grounding_failed`. Tom citatlista. C packad, E inte. R8 visades med *Svaret kan vara ofullständigt.* i alla fem, som i de andra femkörningarna.

---

## De fem hårda

| fall | unionstestet (gamla ∨ lås) | två nya vyer, pack | treutfall |
| --- | --- | --- | --- |
| R5 | ja (gamla = E) | nej (C ∨ C) | vägrad |
| R6 | ja (gamla = E) | nej (C ∨ C) | fel handling (C) |
| R7 | nej | nej (G ∨ D) | vägrad |
| R3b | ja (lås = G) | ja (G ∨ G) | facit |
| R7b | nej | nej (G ∨ I) | vägrad |

R3b träffade för att **båda** vyerna tog G, inte för att OR räddade en miss. R5 och R6 är där unionstestets 9/11 tog slut: den gamla cachen bar E, de två nya promptarna gjorde det inte.

---

## Packstorlek och prefix

`n_packed` **1–2** av 9. Största prefix **13 646** mot låsta produktvägens 17 883 (R5/R6 med fyra handlingar) och helarkivets ~47 k. Tak ~63 k. Kapning: ingen.

| fall | n | prefix | mot låst produktväg |
| --- | ---: | ---: | --- |
| R1, R2, R3, R3b | 1 | 2132 | samma |
| R4, R8, R5b | 1 | 2389 | samma |
| R5, R6 | 1 | 2532 | **färre** handlingar (4 och 17 883 där, med E i paketet) |
| R7 | 2 | 11740 | **fler** (1 och 6 337 där) — två fel, inte facit |
| R7b | 2 | 13646 | **fler** (1 och 3 777 där) — två fel, inte facit |

Fler handlingar i paketet förekom bara när vyerna var oense *om fel handling*. Det höjde prefixet. Det gav inte facit. Det gav inte heller `verifierat_i_fel_handling` — båda vägrades.

---

## R7 och R7b

De står emot varje mekanism vi mätt: BM25, doc2query, query2doc, isolerat beskrivningsurval, union av två låsta uppsättningar, fyra vinklar i en lista, och nu unionsurval med två nygenererade vyer.

De är de två dokumenterade fallen som kräver en **handskriven koppling** mellan frågespråk och handling. Inte ett urvalsproblem att jaga med fler promptar.

---

## Vad 7 mot 9 betyder

Unionstestet 9/11 var två stickprov av samma slags produktbeskrivning, skrivna vid olika tillfällen. Fyra vinklar i en prompt gav 7. Två medvetet olika genereringspromptar, två urval, OR, pack och `ask()` gav åter 7 i paketet och 6 i treutfall — sämre än produktvägen 8–8. Skeppas inte.

---

## Invarianter

- `app/answer.py` rördes inte. Eval monkeypatchar `evaluate_document_path` i processen.
- Låset `97b4e7bfc71f` oförändrat.
- Trafik bara loopback.
- Inget ur handlingarna eller vyerna committat.

Körbar mätning: `uv run python -m scripts.eval_brf1_union_select` från `backend/`. Tester: `uv run pytest -q tests/test_query_expansion.py`.
