# BRF-1: urval i tjugo processer — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `scripts/eval_brf1_selection_stability.py` · ingen `ask()`

Frågan: är handlingsvalet stabilt mellan processer? Det är kandidaten till driften mellan sessioner i femkörningen.

Tjugo färska Python-processer, en i taget (`llama.cpp --parallel 1`). Varje process laddar storen, kör bara `select_documents_by_description` på de elva fallen, avslutar. Beskrivningarna är de som ligger på dokumenten (produktsökvägen). Evalcachen injicerades inte.

Bokstäver nedan är namnordning A–I, samma som facit. Katalogbokstäverna i modellprompten är en annan ordning (`described_documents` sorterar på `casefold`; underhållsplanen blir A där, sophanteringen F).

## Utfallet

**11 av 11 fall valde samma handlingar i 20 av 20 processer.**

| fall | facit | valt (20/20) | facit med |
| --- | --- | --- | ---: |
| R1 | G | G | 20 |
| R2 | G | G | 20 |
| R3 | G | G | 20 |
| R4 | E | E | 20 |
| R5 | E | C, D, F | 0 |
| R6 | E | C, D, F | 0 |
| R7 | E | B | 0 |
| R8 | E | E | 20 |
| R3b | G | G | 20 |
| R5b | E | E | 20 |
| R7b | E | H | 0 |

Urvalet varierar inte mellan processer. Det är inte förklaringen till drift mellan sessioner, och det är inte där determinismen saknas.

En kontroll med den frysta evalcachen (`descriptions.json`) var också 20/20 identisk per fall, men med *andra* handlingar (R5 då D+E, R7 E+B, R7b B+H). Samma slutsats: givet en låst katalog är valet girigt och process-stabilt. Skillnaden cache mot live är beskrivningstexten, inte processgränsen.

## Vad det inte är

Femkörningens treutfall var 6–6 mot 5–5 *inom* en process. Urvalet här är 20/20 *mellan* processer. Att sätta seed eller nollställa temperatur i svarssteget rör inte den här mätningen — temperaturen är redan 0, och urvalet rör sig inte.
