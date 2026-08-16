# BRF-1: LettuceDetect som entailment-varning — 2026-08-16

**Host:** agenntserver · **Modell (svar):** Gemma 4 12B IT · **detektor:** `KRLabsOrg/lettucedect-210m-eurobert-de-v1` · CPU · **commit (huvudväg):** `4ee12d7`

Grinden verifierar att citatet står i handlingen. Ingenting kontrollerade att svaret följer av citatet. R1 är målfallet: citatet är äkta, numeriken släpper, men meningen vänder innebörden.

Kontrollsteget ligger efter att citaten verifierats och ritats, och efter numerisk grundning — aldrig i stället för. Det fäller ingenting. `AskResponse.warning` får texten *Delar av svaret följer inte av de citerade källorna.* när minst en påståendemening överlappar en flaggad span. Kontexten är bara accepterade citat.

## Detektorn

LettuceDetect, MIT. Tokenklassificering på `(kontext, fråga, svar)`. Publicerat exempel-F1 på RAGTruth: **79,22 %** mot **63,4 %** för GPT-4-turbo (Kovács & Recski, [arXiv:2502.17125](https://arxiv.org/abs/2502.17125)).

Publicerade checkpoints: engelska, tyska, franska, spanska, italienska, polska, kinesiska, ungerska. **Inte svenska.** Produkten använder det tyska EuroBERT-210M-huvudet på en flerspråkig encoder, på CPU så den inte tar VRAM från llama-server. Den byts inte ut på känsla.

Tysk kontroll (samma checkpoint, samma API som README):

> Kontext: Paris är huvudstad, befolkning 67 miljoner. Svar: Paris är huvudstad. Befolkning 69 miljoner.

Utfallet: bara 69-miljonersmeningen flaggades (konfidens 0,78). Paris-meningen släpptes. Huvudet fungerar på sitt träningsspråk.

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

## Fälla eller varna

2/8 falsklarm plus miss på målfallet. Steget får inte fälla. Det varnar.

Svenskan är för svag för den här checkpointen, med siffror: tyska kontrollen är ren, samma vikter på BRF-1 flaggar kopierad källtext och missar en innebördsvändning. Det är inte underlag för att byta modell. Det är underlag för att låta varningen ligga.

`BRF_ENTAILMENT=0` stänger av. Default `auto` kör när extra `entailment` är installerad och vikterna redan ligger i cachen — ingen nedladdning i `ask()`.
