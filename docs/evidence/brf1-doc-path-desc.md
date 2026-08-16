# BRF-1: dokumentväg med beskrivningsurval — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `c21db3d` · **embedder:** `model2vec:potion-multilingual-128M`

Sista diagnostiken före arkitekturbeslut. Samma elva fall, samma nio handlingar, samma beskrivningar som `docs/evidence/brf1-doc-descriptions.md`.

**Vad som ändrades (mätning, inte produkt):** `evaluate_document_path` fick modellurval över beskrivningarna (1–3 handlingar) i stället för max fused score. Valda handlingar packades hela under `n_ctx`. Helarkiv blockerades. Grind, citat, numerik — oförändrat.

**Baslinjer:**

| väg | `verifierat_i_facit` | `verifierat_i_fel_handling` | `vägrad` |
| --- | ---: | ---: | ---: |
| retrieval (`docs/evidence/brf1-full-corpus.md`) | 5 | 1 | 5 |
| helarkiv + katalog (`docs/evidence/brf1-doc-descriptions.md`) | 6 | 1 | 4 |
| **dokumentväg + beskrivningsurval** | **9** | **2** | **0** |

---

## Urvalet

| mått | träff |
| --- | ---: |
| isolerat beskrivningsurval (1 handling, `brf1-doc-descriptions.md`) | 7 / 11 |
| guld i modellens 1–3 val | **10 / 11** |
| guld faktiskt packad | **10 / 11** |

Att tillåta 1–3 handlingar höjer urvalet från 7 till 10. Enda missen är **R3b** (valde B, facit G). R6 fick C+D+E med E med — det isolerade urvalet hade bara C.

## Svarssteget

| fall | guld packad | utfall | kommentar |
| --- | --- | --- | --- |
| R7b | ja (A, B, E) | `verifierat_i_fel_handling` | enda förlusten *efter* korrekt urval — citerade B s3 trots E i prompten |

Övriga nio facit-fall hade guld packad och nådde facit. **Förlusten sitter i svarssteget i ett fall**, inte i urvalet (10/11).

---

## `verifierat_i_fel_handling` gick inte till noll

Hypotesen var: packas bara valda handlingar, och valet är rätt, finns fel handling inte att citera ur.

**Stämmer inte när modellen väljer fler än en handling.**

| fall | valt | citerat | orsak |
| --- | --- | --- | --- |
| R3b | B | B s11 | urval miss — guld fanns inte i paketet |
| R7b | A, B, E | B s3 | urval rätt (E med), men B packades också och modellen citerade den |

R7b är det strukturella motbeviset: även med facit i prompten väljer modellen fel handling bland de packade. En enda handling i paketet hade eliminerat felet — men då tappas R6 (behövde C+D+E) och R5 (D+E).

**Slutsats:** beskrivningsurval + multipack löser inte fel-handling-citat strukturellt. Det kräver antingen striktare pack (en handling) med acceptabel förlust i underspecificerade fall, eller en grind som avvisar citat ur icke-förstahandsval.

---

## Per fall

| fall | facit | valt | packat | utfall |
| --- | --- | --- | --- | --- |
| R1 | G | G | G | verifierat_i_facit |
| R2 | G | G | G | verifierat_i_facit |
| R3 | G | B, G | B, G | verifierat_i_facit |
| R4 | E | E | E | verifierat_i_facit |
| R5 | E | D, E | D, E | verifierat_i_facit |
| R6 | E | C, D, E | C, D, E | verifierat_i_facit |
| R7 | E | B, E | B, E | verifierat_i_facit |
| R8 | E | E | E | verifierat_i_facit |
| R3b | G | B | B | verifierat_i_fel_handling |
| R5b | E | E | E | verifierat_i_facit |
| R7b | E | A, B, E | A, B, E | verifierat_i_fel_handling |

Alla elva gick `ask_path=documents`. Prefix per fall: 2132–15530 tokens (medel ~7200), jämfört med 48782 för helarkiv+katalog.

---

## Prefixcache

Urvalet beror på frågan → inget gemensamt helarkivprefix. Ingen försök att rädda cachen.

| mått | helarkiv+katalog | dokumentväg+urval |
| --- | ---: | ---: |
| prefix per fråga | ~48782 (delas) | 2132–15530 (varierar) |
| `cache_n` per LLM-anrop (snitt) | ~47000+ vid svar | **~178** |
| `sum_prompt_n` (11 fall, alla anrop) | — | 88903 |
| medel tid per fall | ~4–5 s (cachad) | **8,2 s** |

Urvalsanropet (~1250 tokens) får `cache_n≈72` (beskrivningslistan). Svarsgenereringen får `cache_n=0` eller låg (~550) — packade utdrag skiljer sig per fråga. Kostnaden är reell: nästan dubbel latens mot cachad helarkivväg.

---

## R5: katalogen och den numeriska grinden

Utan katalog: `verifierat_i_facit` — svar *"På varje faktura tillkommer 494 i administrationskostnad."*, citat E s2 ordagrant.

Med katalog: `vägrad` (`numeric_grounding_failed`). Modellens faktiska svar (före vägran):

> Stena Fastigheter Ekebäckshöjd **2** AB lägger på en administrativ avgift på 494 kr per faktura för sophantering och gårdsskötsel, samt 494 kr i administrationskostnad för mobilitetsåtgärder.

Accepterade citat: *"På varje faktura tillkommer 494 i administrationskostnad."* (E s2).

**Grinden flaggade siffran `2`** — inte 494. Den kommer från bolagsnamnet *Ekebäckshöjd 2 AB* i prosa, inte från källan. Katalogen ledde modellen att skriva ett längre svar som nämnde både D (mobilitet) och E (sophantering), vilket gav en entitetsreferens med en siffra som inte finns i citatet.

Det är inte att 494 var fel — det är att ett tillägg som skulle ge översikt gjorde prosa som grinden korrekt stoppade.

---

## Arkitekturrekommendation

**Beskrivningsurval + dokumentväg är den starkaste vägen på facit (9/11)** och eliminerar alla vägringar i den här körningen. Den slår retrieval, helarkiv och helarkiv+katalog på det måttet.

Men:

1. **`verifierat_i_fel_handling` går inte till noll** med 1–3-handlingspack — R7b kvarstår när distraktor packas med.
2. **Urvalet är 10/11**, inte 7/11 — multipelval hjälper. Förlust i svarssteget: **ett fall** (R7b).
3. **Cachen faller** — ~8 s/fall mot ~4–5 s cachad helarkiv, och `cache_n` i princip noll på svarsgenerering.

Beskrivningarna hör hemma i produkten som urvalsstyrning för dokumentvägen. Helarkiv+katalog är billigare men svagare. Enpack-vs-multipack är nästa designfråga: enpack eliminerar R7b-strukturfel men tappar R5/R6.
