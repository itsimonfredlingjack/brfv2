# BRF-1: lokal modell som svarsdomare — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · **commit (svaren):** `4ee12d7` · loopback

R1:s fel är att svaret inte besvarar frågan, inte att det saknar förankring. LettuceDetect missade det (tokenöverlapp). Den här mätningen ger den lokala modellen frågan, de accepterade citaten och svaret, och frågar en sak: besvarar svaret frågan, givet citaten?

Tre utfall: `besvarar` / `besvarar_inte` / `motsager_citatet`. Ett `complete()` per svar. Ingen ny svarsväg. Prompten skrevs en gång, rakt, och rördes inte mot de 22 — de är den enda ärliga etikettmängden. Den körningen fällde ingenting. Utfallet delades senare in i produkten: se slutet.

Samma 22 handklassade svar som i `docs/evidence/brf1-doc-path-desc.md`. Ingen ny `ask()`.

## Utfallet mot entailment

Entailment (EuroBERT-210M, tyskt huvud) på dokumentvägens åtta korrekta: **2/8 falsklarm**, R1 missad.

| | entailment | domare |
| --- | ---: | ---: |
| R1 (dokumentväg) fångad | nej | **ja** (`motsager_citatet`) |
| falsklarm på de 8 som besvarar (dokumentväg) | 2/8 (R4, R8) | **1/8 (R8)** |
| falsklarm på de 4 som besvarar (retrieval) | — | **1/4 (R8)** |
| grind | nej | **nej då; delad inkoppling efteråt** |

Falsklarmen på samma åtta ligger under entailment, och R1 fångas. Det var kandidat till en riktig grind. Utfallet delades: `motsager_citatet` fäller, `besvarar_inte` markerar. Se slutet.

## Per fall

Dokumentväg:

| fall | manuell | domare |
| --- | --- | --- |
| R1 | rätt handling, svarar fel | **motsager_citatet** |
| R2 | besvarar | besvarar |
| R3 | besvarar | besvarar |
| R4 | besvarar | besvarar |
| R5 | besvarar | besvarar |
| R6 | besvarar | besvarar |
| R7 | besvarar | besvarar |
| R8 | besvarar | **besvarar_inte** |
| R3b | fel handling | besvarar |
| R5b | besvarar | besvarar |
| R7b | fel handling | besvarar |

Retrieval:

| fall | manuell | domare |
| --- | --- | --- |
| R1 | fel handling | besvarar |
| R2 | besvarar | besvarar |
| R3 | vägrad | besvarar_inte |
| R4 | besvarar | besvarar |
| R5 | vägrad | besvarar |
| R6 | besvarar | besvarar |
| R7 | vägrad | besvarar |
| R8 | besvarar | **besvarar_inte** |
| R3b | rätt handling, ofullständigt | besvarar |
| R5b | vägrad | besvarar_inte |
| R7b | vägrad | besvarar |

## R1

Dokumentvägens R1 fångades. Utfallet var `motsager_citatet`, inte `besvarar_inte`. Frågan är ja/nej om reserverad plats. Svaret är citatets egna ord med predikatvändning. Domaren vägrade kalla det `besvarar`. Det räcker som fångst mot målfallet.

Retrievals R1 (fel handling D, svarar ja utifrån 10 % / 50 % fasta platser) fick `besvarar`. Givet de citaten *är* det ett svar på frågan. Domaren är inte en handlingskontroll.

Fel handling på dokumentvägen (R3b, R7b) fick också `besvarar`. Samma skäl: uppgiften är given citaten, inte given facithandlingen.

## Falsklarm

Båda vägarna: bara **R8**. Frågan är *När kan vi tidigast säga upp sophämtningsavtalet?* Svaren anger giltighet tom 2047-03-31 och nio månaders uppsägning, utan att räkna ut tidigaste datum. Handklassningen räknar det som att frågan besvaras. Domaren krävde mer.

Inga andra av de tolv som besvarar frågan flaggades. R4, som entailment flaggade, släpptes.

## De fem retrievalvägringarna

Inga citat i någon av dem. Domaren läser vägringstexten som om den vore svaret.

| fall | grind | domare | vad texten gör |
| --- | --- | --- | --- |
| R3 | `insufficient_data` | `besvarar_inte` | säger att utdragen saknar svaret |
| R5 | `insufficient_data` | `besvarar` | säger att det inte framgår, sen nämner adminavgift och Stena |
| R7 | `insufficient_data` | `besvarar` | samma mönster: saknas, sen verkliga kostnader från 2024-04-01 |
| R5b | `numeric_grounding_failed` | `besvarar_inte` | grindens vägringsprosa, inget sakpåstående |
| R7b | `insufficient_data` | `besvarar` | saknas, sen fasta priser t.o.m. 2024-03-31 |

Två av fem läses som att de inte besvarar. Tre av fem läses som att de besvarar, för att vägringen fortfarande diskuterar ämnet. Domaren ser inte grinden.

## Inte en handlingskontroll

Domaren får frågan, de accepterade citaten och svaret. Den får inte handlingens identitet och inte facit. R3b och R7b i de 22 fick `besvarar` — citatet bar ett svar, ur fel handling. Handlingsvalsmåttet (`docs/evidence/brf1-doc-select.md`, `brf1-doc-path-desc.md`) står kvar som separat kontroll. Grinden täcker inte det.

## Inkopplad, med delade utfall — 2026-08-16

Mätningen ovan var kandidat, inte grind. Utfallet delades mot de 22:

| utfall | produkt |
| --- | --- |
| `motsager_citatet` | fäll. Svaret visas inte. R1:s klass. Noll falsklarm på 22. |
| `besvarar_inte` | visa med markeringen *Svaret kan vara ofullständigt.* R8:s klass. Fäll inte förrän etikettmängden är större än 22. |
| `besvarar` | oförändrat |

Domaren körs aldrig utan accepterade citat. Tre av fem retrievalvägringar fick `besvarar` när vägringsprosan lästes som svar.

Samma elva dokumentvägsfall kördes om med grinden i `ask()` (`scripts/eval_answer_judge_gate.py`, commit efter `6eeb439`). Ny generering, inte ombedömning av de 22.

Treutfall (`verifierat_i_facit` / `verifierat_i_fel_handling` / `vägrad`): **6 / 1 / 4**

Visat / markerat / vägrat: **6 / 1 / 4**

| fall | tre | display | grind |
| --- | --- | --- | --- |
| R1 | vägrad | vägrad | **`citation_contradicted`** — R1 fångad, svaret visas inte |
| R2 | verifierat_i_facit | visat | besvarar |
| R3 | verifierat_i_facit | visat | besvarar |
| R4 | verifierat_i_facit | visat | besvarar |
| R5 | verifierat_i_fel_handling | visat | besvarar — citat ur C, facit E. Domaren ser inte handlingen |
| R6 | vägrad | vägrad | `numeric_grounding_failed` — domaren anropades inte |
| R7 | vägrad | vägrad | `insufficient_data` — inga citat, domaren anropades inte |
| R8 | verifierat_i_facit | **markerat** | `besvarar_inte` — svaret visas med ofullständig-markering |
| R3b | verifierat_i_facit | visat | besvarar (den här körningen citerade G) |
| R5b | verifierat_i_facit | visat | besvarar |
| R7b | vägrad | vägrad | `insufficient_data` — inga citat, domaren anropades inte |

R1 är den enda nya vägran från domaren. R8 fälldes inte. R6/R7/R7b är befintliga grindar eller modellens `insufficient_data` — inte domaren. Genereringen rörde sig mot den tidigare dokumentvägskörningen (då 9/2/0 citatmått, 0 vägran); det är inte grindens effekt.

R5 är den levande demonstrationen att fel handling passerar: citatet är äkta, svaret följer av det, handlingen är fel. Samma klass som R3b/R7b i de 22.

Latens för det extra anropet, uppmätt på de sju visade svaren (samma modell, loopback): **medel 0,44 s, max 0,55 s**. R1:s anrop satt i `ask()` men loggades inte separat; de sju replay-anropen är samma `complete()`-kontrakt. Medel per fall för hela `ask()`: 12,9 s (första fallet 47 s, kallt prefix).

Prompten rördes inte.
