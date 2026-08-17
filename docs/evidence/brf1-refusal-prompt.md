# BRF-1: R5, R7, R7b — fanns facit i prompten? — 2026-08-16

**Host:** agenntserver · produktens dokumentväg · `scripts/eval_brf1_refusal_prompt.py` · ingen defaultändring

De tre vägrade med `insufficient_data` i femkörningen (`docs/evidence/brf1-variance.md`). De besvarades i enkörningen utan grind. Frågan är om facithandlingen valdes och om facittexten låg bland de packade chunkarna. Ingen åtgärd.

Bokstäver är namnordning (facit E = sophantering). En `ask()` per fall, live beskrivningar, `ensure_descriptions` skrev inte om något (`n_describe_calls=0`).

## Svaret

Facittexten fanns **inte** i prompten i något av de tre fallen. Det är inte klassen «utdragen räckte, modellen avstod».

| fall | valt (namnordning) | facit E i paketet | E s2-chunkar i utdragen | `insufficient_data` den här körningen |
| --- | --- | --- | --- | --- |
| R5 | C, D, F | nej | 0 / 2 | nej (citat ur C) |
| R7 | B | nej | 0 / 2 | ja |
| R7b | H | nej | 0 / 2 | ja |

Samma pack som urvalet i tjugo processer (`docs/evidence/brf1-selection-stability.md`): R5 C+D+F, R7 B, R7b H, 20/20.

## R7 och R7b

Urvalet namngav inte sophanteringen. Packade handlingar är teknisk förvaltning (B) respektive kommunikationsoperatörsavtalet (H). Markörerna *varsko* / *prisjustering* fanns inte i utdragen. Modellen satte `insufficient_data`. Givet paketet är det korrekt: svaret sitter i E, och E fanns inte där.

Felklass: **urval missade facithandlingen.** Inte svarssteg.

Livebeskrivningen av E nämner inte längre prisjustering eller varsko (evalcachen gjorde det). Det räcker för att valet ska sluta peka på E.

## R5

Modellen svarade `{"documents": ["C", "D", "E", "F"]}` i katalogbokstäver. Taket är tre. Parsern behåller C, D, E. Katalog-E är delägarförvaltning (namn F). Katalog-F är sophantering (namn E) — den **fjärde**, borttagen.

Facit valdes alltså av modellen och släpptes av 1–3-taket. E s2 fanns inte i utdragen. *494* och *administrationskostnad* fanns ändå, ur C. Den här körningen svarade ur C. Femkörningen vägrade. Samma pack, olika svarssteg — men facittexten saknades i båda.

Felklass: **urval kapade facit som fjärde handling.** Inte «facit i prompten, modellen avstod».

Katalogordningen (`casefold`) gör att namn-E och katalog-E inte är samma handling. Det är fotnot till taket, inte en andra felklass.

Analysen bekräftades när taket togs bort: R5 packade de fyra, citerade E, facit i fem körningar (`docs/evidence/brf1-locked-pack.md`).

## Inte den klassen

Om E hade packats och E s2 legat i utdragen hade `insufficient_data` varit svarsstegs-avstående. Det var inte fallet. De tre tidigare träffarna (enkörning utan grind) hade E i paketet.
