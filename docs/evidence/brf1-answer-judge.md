# BRF-1: lokal modell som svarsdomare — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · **commit (svaren):** `4ee12d7` · loopback

R1:s fel är att svaret inte besvarar frågan, inte att det saknar förankring. LettuceDetect missade det (tokenöverlapp). Den här mätningen ger den lokala modellen frågan, de accepterade citaten och svaret, och frågar en sak: besvarar svaret frågan, givet citaten?

Tre utfall: `besvarar` / `besvarar_inte` / `motsager_citatet`. Ett `complete()` per svar. Ingen ny svarsväg. Inget som fäller. Prompten skrevs en gång, rakt, och rördes inte mot de 22 — de är den enda ärliga etikettmängden.

Samma 22 handklassade svar som i `docs/evidence/brf1-doc-path-desc.md`. Ingen ny `ask()`.

## Utfallet mot entailment

Entailment (EuroBERT-210M, tyskt huvud) på dokumentvägens åtta korrekta: **2/8 falsklarm**, R1 missad.

| | entailment | domare |
| --- | ---: | ---: |
| R1 (dokumentväg) fångad | nej | **ja** (`motsager_citatet`) |
| falsklarm på de 8 som besvarar (dokumentväg) | 2/8 (R4, R8) | **1/8 (R8)** |
| falsklarm på de 4 som besvarar (retrieval) | — | **1/4 (R8)** |
| grind | nej | **nej** |

Falsklarmen på samma åtta ligger under entailment, och R1 fångas. Det är en kandidat till en riktig grind. Den är **inte** en grind i den här körningen.

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

## Inte en grind

Kandidat: ja, mot den uttalade tröskeln (R1 fångas och falsklarm på de åtta under 2/8). Inte inkopplad. Prompten rörs inte. `ask()` importerar inte `app.answer_judge`. Körningen är `scripts/eval_answer_judge.py`.
