# BRF-1:s elva fall — retrieval mot helarkiv — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `4b6b4aa` · **embedder:** `model2vec:potion-multilingual-128M`

Samma elva fall som i `planner-vs-real-model.md` tillägg 7–9 och `eval_real_corpus.py --fall`, mot samma nio handlingar (130 chunkar). Två körningar, samma store: `fullCorpusTokenThreshold=0` (retrieval, dagens väg) och `None` (helarkiv). Fan-out rördes inte. `r01` kördes inte.

Korpusen ryms: `prefix_tokens=47402` under taket `65536 − 512 − 1800 = 63224`, `bound=fits`. Helarkivvägen eldade på alla elva efter-frågorna.

Måttet nedan är omräknat på de körningarna. Ingen ny elva-fallskörning.

## Måttet

Produktens grind *verifierat* (inte vägrad, minst ett godkänt citat) är otillräcklig. R7b var verifierat ur fel handling. Varje fall har en facithandling (`truth` / `doc` i fallfilen). Tre utfall, ömsesidigt uteslutande:

| utfall | definition |
| --- | --- |
| `verifierat_i_facit` | inte vägrad, minst ett godkänt citat, minst ett av dem i facithandlingen |
| `verifierat_i_fel_handling` | inte vägrad, minst ett godkänt citat, inget av dem i facithandlingen |
| `vägrad` | vägrad, eller inget godkänt citat |

Den gamla kolumnen *verifierat* slår ihop de två första. Det är fel sorts träff.

Samma invändning gäller `verifierat_i_facit`: ett ordagrant citat ur rätt handling betyder inte att svaret besvarar frågan. Retrievalvägens svar klassades senare för hand mot frågan: **4 besvarar / 1 ofullständigt / 1 fel handling / 5 vägrade**. Det är baslinjen i `docs/evidence/brf1-doc-path-desc.md`. 5 `verifierat_i_facit` är inte 4 som besvarar frågan.

## Hypotesen, utfallet

Hypotesen var smal: om felet var att fel handling rankades överst ska det felet vara borta när ingen rankning sker.

**Det blev inte bättre**, och det syns tydligare med rätt mått. Rankningsfelet finns: toppträffen låg i fel handling i **10 av 11** retrievalfrågor (bara R1 hade facithandlingen överst — samma mönster som tillägg 9). Att lägga hela arkivet i prompten tar bort rankningen. Facitträffarna blir 5 → 5. Fel citerad handling och vägran finns kvar. Felet satt inte bara i hämtningen.

| | retrieval | helarkiv |
| --- | ---: | ---: |
| `verifierat_i_facit` | 5 | 5 |
| `verifierat_i_fel_handling` | 1 | 1 |
| `vägrad` | 5 | 5 |

Gamla *verifierat* hade räknat 6 → 6 (R1 retrieval och R7b helarkiv som vinster).

## Per fall

| fall | facit | retrieval | helarkiv | vägran före | vägran efter |
| --- | --- | --- | --- | --- | --- |
| R1 | G | verifierat_i_fel_handling (D s11, D s9) | verifierat_i_facit (G s1) | — | — |
| R2 | G | verifierat_i_facit (G s2) | vägrad | — | `insufficient_data` |
| R3 | G | vägrad | vägrad | `insufficient_data` | `grounding_failed` |
| R4 | E | verifierat_i_facit (E s2) | verifierat_i_facit (E s2) | — | — |
| R5 | E | vägrad | verifierat_i_facit (E s2) | `insufficient_data` | — |
| R6 | E | verifierat_i_facit (E s1) | vägrad | — | `insufficient_data` |
| R7 | E | vägrad | vägrad | `insufficient_data` | `grounding_failed` |
| R8 | E | verifierat_i_facit (E s2) | verifierat_i_facit (E s2) | — | — |
| R3b | G | verifierat_i_facit (G s2) | verifierat_i_facit (G s2) | — | — |
| R5b | E | vägrad | vägrad | `numeric_grounding_failed` | `insufficient_data` |
| R7b | E | vägrad | verifierat_i_fel_handling (B s3) | `insufficient_data` | — |

Handlingarna är bokstäver i namnordning, samma konvention som `eval_real_corpus.py`. Ingen avtalstext, inga filnamn.

## Verifierat ur fel handling

Det utfallet träffar mer än ett fall. Det är ett eget fynd, inte en parentes till rankningen.

- **R1, retrieval.** Facithandlingen låg överst (G s1). Citatet som gick igenom grinden var D s11 och D s9.
- **R7b, helarkiv.** Ingen rankning skedde. Citatet som gick igenom var B s3. Facit är E.

Grinden accepterar ett förankrat citat ur fel handling. Det händer både när retrieval har facit överst och när hela arkivet ligger i prompten. Det kan inte förklaras med topp-miss.

## Vad som faktiskt rörde sig (nya måttet)

Två riktiga vinster: R1 (fel handling → facit) och R5 (vägrad → facit). Två regressioner: R2 och R6 (facit → vägrad). R7b är inte en vinst: vägrad → fel handling.

R5 är det enda fall som ser ut som hypotesen: fel handling överst, vägran, sedan citat i facithandlingen när rankningen är borta.

R1:s vinst på helarkivet syns bara med det nya måttet. Retrieval *såg* verifierad ut.

## Var R2:s och R6:s facit låg i prefixet

Samma nio handlingar, sidordning (produktens helarkivväg), `prefix_tokens=47402`. Tokenposition mot llama.cpp `/tokenize`, samma räknare som `measure_tokens`. Andel = mittpunkt / prefix. Två chunkar per facitsida.

| fall | facit | K | start | mitt | slut | andel mitt |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| R2 | G s2 | 80–81 | 31568 | 31962.5 | 32357 | **0.674** |
| R6 | E s1 | 66–67 | 25289 | 25736.5 | 26184 | **0.543** |

Nålprovet vid `n_ctx=65536` (`docs/evidence/nctx-occupancy.md`) träffade på 0.10 och 0.90 och missade på 0.50, från 8k till 62k höstack.

R6 ligger i mitten. Det är samma zon som nålen missar. Regressionen R6 (facit på retrieval, `insufficient_data` på helarkiv) har den förklaringen.

R2 ligger i bakre tredjedelen, inte på en kant. Det är inte 0.50 och inte 0.90. Lost-in-the-middle är förenligt med utfallet men inte lika rent som för R6.

## U-form mot R2, R6, R7b

Stadgarfrågorna i `edge-order.md` gav noll skillnad för att de var triviala. De här tre är det inte. Samma store, helarkiv, `threshold=None`. `page` = dokumentnamn sedan sida. `probe` = fryst sond + frågeoberoende U-form. Nytt mått.

| fall | sidordning | U-form | vägran sida | vägran U | citat sida | citat U |
| --- | --- | --- | --- | --- | --- | --- |
| R2 | vägrad | verifierat_i_facit (G s2) | `insufficient_data` | — | — | G s2 |
| R6 | vägrad | vägrad | `insufficient_data` | `insufficient_data` | — | — |
| R7b | verifierat_i_fel_handling (A s5, B s4) | vägrad | — | `grounding_failed` | A s5, B s4 | — |

Sidordningen på R2 och R6 matchade elva-fallskörningen. R7b förblev `verifierat_i_fel_handling` (ursprungligen B s3; omkörningen tog A s5 och B s4). Felmoden reproducerades, inte samma felsida.

Facit under U-form, samma tokenizer:

| fall | sidordning mitt | U-form mitt |
| --- | ---: | ---: |
| R2 | 0.674 | 0.391 |
| R6 | 0.543 | 0.524 |

Sonden är stadgarformad (`stadgar styrelse förening kallelse årsredovisning ekonomi`). Den parkerar inte E och G på U-kanterna. R6 stannade i mitten och förblev vägrad. R2 flyttades till 0.39 och blev `verifierat_i_facit`. R7b nådde inte facit.

**U-formen slog inte igenom.** En av tre återställdes, den rena mittmissen (R6) rördes inte, fel-handling (R7b) blev vägran i stället för facit. Den ligger kvar bakom `store._full_corpus_order`. Den prövades mot verkliga fall och höll inte som produktdefault.

## Vad det här inte är

Baslinjen **2 av 11** i `HANDOFF-brf1.md` är fan-out mot budgetmatchad enkelsökning, mätt som bevisrecall. Den siffran är inte omkörd här och inte omprövad.

`r01` är förbrukat som färskt bevis och ingick inte. R4 är den verkliga kusinen (*fast pris för sophämtningen*) och var `verifierat_i_facit` på båda vägarna; det räknas inte som `r01`.

Fan-out ligger avstängd. `ask_planned` anropades inte. `BRF_PLANNED_ASK` sattes inte.

Äldre `verified_to_refused=0` på stadgarfrågorna och en-dokumentssnittet räknade samma fel sorts träff. Se `docs/evidence/full-corpus-64k.md`, `docs/evidence/edge-order.md`, `docs/evidence/document-ask.md`, `docs/evidence/full-corpus-ask.md`.
