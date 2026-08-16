# BRF-1: LettuceDetect som entailment-diagnostik — 2026-08-16

**Host:** agenntserver · **Modell (svar):** Gemma 4 12B IT · **detektor:** `KRLabsOrg/lettucedect-210m-eurobert-de-v1` · CPU · **commit (mätning):** `4ee12d7` · **produktyta:** avstängd

> **Enkörning.** Svaren som detektorn läste är ett fryst `ask()`-ögonblick, samma som i `brf1-doc-path-desc.md`. Spann över fem körningar: `docs/evidence/brf1-variance.md`.

Grinden verifierar att citatet står i handlingen. Ingenting kontrollerade att svaret följer av citatet. R1 är målfallet: citatet är äkta, numeriken släpper, men meningen vänder innebörden.

Steget mättes som varning efter verifierade citat. Det är **inte** produktyta. `ask()` importerar inte `app.entailment`. Diagnostiken körs med `BRF_ENTAILMENT=1` från `scripts/eval_entailment.py`.

## Detektorn

LettuceDetect, MIT. Tokenklassificering på `(kontext, fråga, svar)`. Publicerat exempel-F1 på RAGTruth: **79,22 %** mot **63,4 %** för GPT-4-turbo (Kovács & Recski, [arXiv:2502.17125](https://arxiv.org/abs/2502.17125)).

Publicerade checkpoints: engelska, tyska, franska, spanska, italienska, polska, kinesiska, ungerska. **Inte svenska.** Mätningen använde det tyska EuroBERT-210M-huvudet på en flerspråkig encoder, på CPU.

Tysk kontroll (samma checkpoint, samma API som README):

> Kontext: Paris är huvudstad, befolkning 67 miljoner. Svar: Paris är huvudstad. Befolkning 69 miljoner.

Utfallet: bara 69-miljonersmeningen flaggades (konfidens 0,78). Paris-meningen släpptes. Huvudet fungerar på sitt träningsspråk. **Tysk kontroll på samma vikter är ren.**

## De elva fallen

Samma dokumentvägssvar som klassades för hand i `docs/evidence/brf1-doc-path-desc.md`. Ingen ny `ask()`.

| fall | manuell klass | flaggad | anmärkning |
| --- | --- | --- | --- |
| R1 | rätt handling, svarar fel | **nej** | målfallet missas |
| R2 | besvarar | nej | |
| R3 | besvarar | nej | |
| R4 | besvarar | **ja** | span `1-3 fakturer` (konfidens 0,75) — står i citatet |
| R5 | besvarar | nej | |
| R6 | besvarar | nej | |
| R7 | besvarar | nej | |
| R8 | besvarar | **ja** | span `med 2022-04-01 och gäller` (konfidens 0,88) — står i citatet |
| R3b | fel handling | nej | kopierar fel citat, tokenöverlapp |
| R5b | besvarar | nej | |
| R7b | fel handling | nej | kopierar fel citat, tokenöverlapp |

**Fångas R1?** Nej. Svaret är byggt av citatets egna ord med en predikatvändning. Tokenklassificering ser stöd, inte innebörd.

**Av de åtta som besvarar frågan flaggas 2 (R4, R8).** Båda flaggar spänn som finns i de accepterade citaten. Det är 2/8 falsklarm på svenska, på svar som är korrekta och i praktiken utdragna.

R3b och R7b flaggas inte. Det är samma tokenöverlapp: fel handling, men citatet bär svaret.

## Slutsats

EuroBERT-210M (tyskt huvud) på svenska missar polaritetsfelet och flaggar 2 av 8 korrekta svar; tysk kontroll på samma vikter är ren. **Svenskan saknas i checkpointen.** Tokenförankring kan ändå inte se R1:s felklass: felet är att svaret inte besvarar frågan, inte att citatet saknas.

Steget är avstängt som produktyta. Det ligger kvar som diagnostik i eval (`scripts/eval_entailment.py`, `BRF_ENTAILMENT=1`). Det fäller ingenting.

R1:s felklass är att svaret inte besvarar frågan. Den uppgiften mättes separat med den lokala modellen som domare: `docs/evidence/brf1-answer-judge.md`.
