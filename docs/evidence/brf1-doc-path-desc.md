# BRF-1: dokumentväg med beskrivningsurval — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `c21db3d` · **embedder:** `model2vec:potion-multilingual-128M`

> **Enkörning utan domargrind.** 4 → 8 (handklassat) och 9/2/0 (citatmått) är en körning per fall, före svarsdomaren. Femkörning med räknetak tre: dokumentväg **6 facit** mot retrieval **5 facit** — `docs/evidence/brf1-variance.md`. Gällande dokumentväg efter frysta beskrivningar och packning till tokentaket: **8–8** — `docs/evidence/brf1-locked-pack.md`.

Sista diagnostiken före arkitekturbeslut, sedan produkt. Samma elva fall, samma nio handlingar, samma beskrivningar som `docs/evidence/brf1-doc-descriptions.md`.

**Vad som mättes:** `evaluate_document_path` fick modellurval över beskrivningarna (1–3 handlingar) i stället för max fused score. Valda handlingar packades hela under `n_ctx`. Helarkiv blockerades. Grind, citat, numerik — oförändrat. Den vägen är nu produktens huvudväg; se slutet.

**Måttlärdom:** tre mått i följd räknade något som låg intill det vi ville veta — citat som fanns, citat ur rätt handling, och först därefter svar som besvarar frågan.

Baslinjen i **den här enkörningen utan grind** är retrieval klassad för hand med samma fyrutfallsmått:

| utfall | retrieval | dokumentväg + beskrivningsurval |
| --- | ---: | ---: |
| besvarar frågan korrekt | **4** | **8** |
| citerar rätt handling men svarar fel eller ofullständigt | 1 | 1 |
| fel handling | 1 | 2 |
| vägrad | 5 | 0 |

**4 → 8** var enkörning utan domargrind, handklassat mot frågan. Det är inte gällande tal. Gällande: dokumentväg 6 facit mot retrieval 5 facit över fem körningar (`docs/evidence/brf1-variance.md`). Retrievals 5 `verifierat_i_facit` och dokumentvägens 9 i tabellerna nedan är samma sorts enkörning utan grind, citatmått.

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

## Retrieval klassad med samma mått

Samma elva fall, `fullCorpusTokenThreshold=0`, samma store, samma modell. Svarstexterna fanns inte i `before.json`; de lästes från en omkörning. Citatmåttet återkom oförändrat (5 / 1 / 5). Klassning för hand mot frågan:

| utfall | fall | n |
| --- | --- | ---: |
| besvarar frågan korrekt | R2, R4, R6, R8 | **4** |
| citerar rätt handling men svarar fel eller ofullständigt | R3b | **1** |
| fel handling | R1 | **1** |
| vägrad | R3, R5, R7, R5b, R7b | **5** |

R2 nej + nio månader. R4 inte fast pris efter 2024-03-31. R6 andel BOA+LOA och 3446/20362 för 117:14. R8 tom 2047-03-31, nio månader. R3b citerar G (facit) men svarar med parkeringsfriskrivningen på en fråga om *gården*. R1 svarar ja utifrån D s11/s9 (10 % / 50 % fasta platser); facit är G. Vägran: R3/R5/R7/R7b `insufficient_data`, R5b `numeric_grounding_failed`.

**4 är retrievalbaslinjen för om frågan besvaras** i den här enkörningen utan grind, handklassat. Dokumentvägen är 8 mot den baslinjen i samma körning, inte 9 mot 5. Gällande treutfall med grind: 6 mot 5 över fem körningar (`docs/evidence/brf1-variance.md`).

---

## Måttet räknar fortfarande fel sorts träff

`verifierat` slogs ihop till `verifierat_i_facit` för att det första räknade fel sorts träff (citat ur fel handling). Samma invändning gäller nu `verifierat_i_facit`: ett ordagrant citat ur rätt handling betyder inte att svaret besvarar frågan. R5-diagnosen visade det redan — citatet var korrekt och prosan innehöll en siffra som inte fanns i källan. Noll vägringar gör hålet skarpare, inte mildare: systemet svarar alltid.

Svarstexterna sparades inte i `result.json`. De lästes från en omkörning av samma patchade väg (samma store, samma beskrivningar, samma 1–3-urval). Urval och fel-handling-fall återkom; R4 gick genom numerisk reparation (`2024`) och släpptes.

Klassning för hand mot frågan, inte mot citatgrinden:

| utfall | fall | n |
| --- | --- | ---: |
| besvarar frågan korrekt | R2, R3, R4, R5, R6, R7, R8, R5b | **8** |
| citerar rätt handling men svarar fel eller ofullständigt | R1 | **1** |
| fel handling | R3b, R7b | **2** |

**8 är inte siffran som gäller framåt.** Det är enkörning utan grind, handklassat, inte 9. Femkörning med räknetak tre var dokumentväg 6 facit mot retrieval 5 facit med grind. Gällande dokumentväg efter att taket togs bort: 8–8 (`docs/evidence/brf1-locked-pack.md`). R1 citerade G s1 men vände meningen: *"Hyresgästen förbinder sig att anvisa de boende en egen plats i garaget då detta strider mot tecknat Mobilitetsavtal."* Facitfrågan är ja/nej om reserverad plats. Svaret är osammanhängande och svarar inte.

R2 nej + nio månader. R3 friskrivning om inte oaktsamhet. R4 inte fast pris efter 2024-04-01 (schablon Q1–3, verkliga kostnader). R5 och R5b 494 i administrationskostnad. R6 andel av BOA+LOA / verkliga kostnader för 117:14. R7 varsko om betydande prisjusteringar. R8 nio månader, gäller tom 2047-03-31.

---

## Noll vägringar är inte en avstängd grind

Samma `_synthesize` som retrieval: `insufficient_data`, `grounding_failed` (requireSources), `numeric_grounding_failed` (med en reparation). Dokumentvägen sätter `low_relevance=False` och hoppar över minRelevance; retrieval vägrade inte på den grinden i de här elva fallen heller.

| fall | retrieval (före) | dokumentväg, grindar | dokumentväg, utfall |
| --- | --- | --- | --- |
| R1 | — (fel handling) | utvärderade, inga föll | svarade, se R1 ovan |
| R2 | — | utvärderade, inga föll | korrekt |
| R3 | `insufficient_data` | utvärderade, inga föll | korrekt |
| R4 | — | numerisk grind föll på `2024`, reparation gick igenom | korrekt |
| R5 | `insufficient_data` | utvärderade, inga föll | korrekt |
| R6 | — | utvärderade, inga föll | korrekt |
| R7 | `insufficient_data` | utvärderade, inga föll | korrekt |
| R8 | — | utvärderade, inga föll | korrekt |
| R3b | — | utvärderade, inga föll | fel handling |
| R5b | `numeric_grounding_failed` | utvärderade, inga föll | korrekt |
| R7b | `insufficient_data` | utvärderade, inga föll | fel handling |

Retrievalvägrade där modellen sa `insufficient_data` eller där numeriken föll. På dokumentvägen sa modellen inte `insufficient_data`, citaten verifierades, och numeriken släppte (R4 efter reparation). Grinden slutade inte fälla för att vägen byttes. Svaren hittades — utom R1 som släpptes med ett citat som inte besvarar frågan, och R3b/R7b som släpptes med citat ur fel handling. Det är måtthålet, inte en avstängd grind.

---

## R7b: enpack mot R5 och R6

Facit E var packad (A, B, E). Modellen citerade B s3 (tilläggsarbete / prislista), inte E s2 (varsko om prisjusteringar).

Enpack av *rätt* handling skulle ta bort felet strukturellt: B finns inte att citera ur. Den enpacken har vi inte vid körning. Isolerat beskrivningsurval (en handling) valde **A** på R7b, inte E. Enpack av modellens förstahandsval hade packat fel handling.

Enpack av 1–3 → 1 som produktregel kostar de fall som behövde flera handlingar i paketet: **R5** (D+E) och **R6** (C+D+E). Gör inte om den upptäckten genom att sätta max 1 som default för att tysta R7b.

**Åtgärd:** behåll 1–3. Inför inte enpack. R7b är ett svarsstegfel bland packade handlingar, inte ett packbreddsfel att "rätta" med max 1. Nästa steg mot R7b är samma klass som R3b — en handskriven koppling fråga→handling — inte en smalare packare.

---

## R3b: första kända fallet som kräver en handskriven koppling

Fråga: *Vem står för kostnaden om en bil får en skada på gården?* Facit G (hyresavtal parkering). Urvalet tog B (teknisk förvaltning). Citatet B s11 handlar om skadegörelse vid avrop, inte bil på gården.

Frågans pekord (*gården*, *bil*, *skada*) finns inte i facithandlingen. G talar om parkering, friskrivning, personbil i lokalen. Det är inte lösbart med en bättre metod på samma underlag: beskrivning, BM25, fused score och titel+struktur missade alla. **Det är det första kända fallet som kräver att någon skriver kopplingen för hand** (den här frågan hör till parkeringsavtalet, inte till teknisk förvaltning eller gården som ord). Bygg inte den kopplingen än.

Motsvarande mekanism är redan mätt: Marcel (Trienes et al., EMNLP 2025 demos, [arXiv:2507.13937](https://arxiv.org/abs/2507.13937)) lade ett handkurerat frågelager — 36 FAQ:er, varje kopplad till relevanta handlingar — ovanpå BM25+dense och fick **+75 % MRR**. Vi behöver inte återupptäcka det. R3b är skälet att införa samma slags lager här, inte ett nytt forskningsproblem.

---

## Produkt

Dokumentvägen med beskrivningsurval är huvudväg (`choose_ask_path` i `app/answer.py`). Beskrivningar genereras en gång per extraherad textversion och skrivs om bara när sidtexten ändras; den gamla texten sparas i `description_previous`. Urvalsprompten ber om 1–3 handlingar; parser och packare har inget räknetak — packning följer modellens ordning tills `n_ctx`. Max fused score styr inte. Helarkiv ligger kvar bakom `Store._prefer_full_corpus`. Retrieval är fallback när urvalet inte kan köras eller paketet inte ryms. Citatkedja, numerisk grind och koordinater oförändrade.

LettuceDetect är **inte** produktyta. EuroBERT-210M (tyskt huvud) på svenska missade R1:s polaritetsfel och flaggade 2 av 8 korrekta svar; tysk kontroll på samma vikter var ren. Svenskan saknas i checkpointen, och tokenförankring kan inte se R1:s felklass. Mätningen och den avstängda diagnostiken står i `docs/evidence/brf1-entailment.md`.

Samma felklass mättes med den lokala modellen som domare (besvarar frågan, givet citaten): `docs/evidence/brf1-answer-judge.md`. Utfallet är delat: `motsager_citatet` fäller, `besvarar_inte` visar med markering, `besvarar` oförändrat. Domaren ser inte handlingen — fel handling är en separat kontroll.
