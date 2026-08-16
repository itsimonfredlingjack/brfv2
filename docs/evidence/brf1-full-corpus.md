# BRF-1:s elva fall — retrieval mot helarkiv — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `4b6b4aa` · **embedder:** `model2vec:potion-multilingual-128M`

Samma elva fall som i `planner-vs-real-model.md` tillägg 7–9 och `eval_real_corpus.py --fall`, mot samma nio handlingar (130 chunkar). Två körningar, samma store: `fullCorpusTokenThreshold=0` (retrieval, dagens väg) och `None` (helarkiv). Fan-out rördes inte. `r01` kördes inte.

Korpusen ryms: `prefix_tokens=47402` under taket `65536 − 512 − 1800 = 63224`, `bound=fits`. Helarkivvägen eldade på alla elva efter-frågorna.

## Hypotesen, utfallet

Hypotesen var smal: om felet var att fel handling rankades överst ska det felet vara borta när ingen rankning sker.

**Det blev inte bättre.** Rankningsfelet finns: toppträffen låg i fel handling i **10 av 11** retrievalfrågor (bara R1 hade facithandlingen överst — samma mönster som tillägg 9). Att lägga hela arkivet i prompten tar bort rankningen, men vägran och fel citerad handling finns kvar. Felet satt inte bara i hämtningen.

## Per fall

*Verifierat* = produktens egen grind: inte vägrad, minst ett godkänt citat. Det är inte samma sak som att citatet pekar på facithandlingen. Den kolumnen står till höger, för det var just den felmoden baslinjen pekade ut.

| fall | retrieval | helarkiv | vägran före | vägran efter | topp fel handling | citat i facithandling |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | verifierat | verifierat | — | — | nej (G s1) | nej (D) → ja (G s1) |
| R2 | verifierat | vägrad | — | `insufficient_data` | ja (H s3) | ja → — |
| R3 | vägrad | vägrad | `insufficient_data` | `grounding_failed` | ja (D s9) | — → — |
| R4 | verifierat | verifierat | — | — | ja (B s3) | ja → ja |
| R5 | vägrad | verifierat | `insufficient_data` | — | ja (C s2) | — → ja (E s2) |
| R6 | verifierat | vägrad | — | `insufficient_data` | ja (C s2) | ja → — |
| R7 | vägrad | vägrad | `insufficient_data` | `grounding_failed` | ja (F s2) | — → — |
| R8 | verifierat | verifierat | — | — | ja (H s3) | ja → ja |
| R3b | verifierat | verifierat | — | — | ja (D s9) | ja → ja |
| R5b | vägrad | vägrad | `numeric_grounding_failed` | `insufficient_data` | ja (C s2) | — → — |
| R7b | vägrad | verifierat | `insufficient_data` | — | ja (G s3) | — → **nej (B s3)** |

Handlingarna är bokstäver i namnordning, samma konvention som `eval_real_corpus.py`. Ingen avtalstext, inga filnamn.

## Vad som faktiskt rörde sig

Två fall blev verifierade som varit vägrade (R5, R7b). Två som varit verifierade vägrades (R2, R6). Tre vägrades på båda sidor (R3, R7, R5b). Fyra var verifierade på båda (R1, R4, R8, R3b).

R5 är det enda fall som ser ut som hypotesen: fel handling överst, vägran, sedan citat i facithandlingen när rankningen är borta.

R7b är det viktigaste motexemplet. Det är det enda distinkta ordförrådsglappet i tillägg 8. Helarkivvägen släppte igenom ett verifierat citat i **fel** handling. Ingen rankning skedde — modellen valde fel stycke ur hela arkivet. Det felet kan inte ha suttit i hämtningen.

R1 visar samma sak från andra hållet: retrieval hade redan facithandlingen överst och citerade ändå D. Helarkivet träffade G. Rankningen var inte orsaken där heller.

R2 och R6 är den gamla felmoden i spegel: retrieval citerade facit trots fel handling överst (det som *ser* verifierat ut), helarkivet vägrade med `insufficient_data`. Att ta bort rankningen tog alltså bort svar som redan var rätt förankrade.

## Vad det här inte är

Baslinjen **2 av 11** i `HANDOFF-brf1.md` är fan-out mot budgetmatchad enkelsökning, mätt som bevisrecall. Den siffran är inte omkörd här och inte omprövad. Det här är produktens verifieringsgrind på samma frågor.

`r01` är förbrukat som färskt bevis och ingick inte. R4 är den verkliga kusinen (*fast pris för sophämtningen*) och var verifierad mot facit på båda vägarna; det räknas inte som `r01`.

Fan-out ligger avstängd. `ask_planned` anropades inte. `BRF_PLANNED_ASK` sattes inte.
