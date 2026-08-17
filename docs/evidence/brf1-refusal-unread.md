# BRF-1: vägran som svar — olästa handlingar — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · arbetskopia efter numeriknormalisering · loopback · `scripts/eval_brf1_refusal_help.py`

En `ask()` per fall, dokumentväg, låset `97b4e7bfc71f`. Urval, citatkedja och svarsdomare orörda. Tredje ledet i `insufficient_data` är inte längre en gissning om handlingssort. Det är namnen på de beskrivna handlingar i arkivet som inte packades. Första ledet är fortfarande de lästa. Andra ledet är fortfarande att svaret inte står i dem. Ingen lista över vad en förening «ska» ha. Ingen extra modellomgång. Noll externa anslutningar. `n_describe_calls=0`.

Måttet: för varje `insufficient_data` är facithandlingen känd. Står den med bland de olästa som räknas upp?

---

## Slutsats

**2 av 2.** De två `insufficient_data`-vägran (R7, R7b) räknade upp facithandlingen bland de olästa. Facit E = sophantering. R7 läste B (teknisk förvaltning). R7b läste H (kommunikationsoperatör). Sophanteringsavtalet fanns i båda listorna.

Det är ett tal som går att träffa. Sortsmeningen i `brf1-refusal-help.md` träffade 0 av 2.

---

## Talet

| | |
| --- | ---: |
| fall | 11 |
| vägrade totalt | 4 |
| `insufficient_data` (ny text) | **2** (R7, R7b) |
| namngav oläst facit | **2 / 2** |

Övriga vägran skrevs inte om: R1 `citation_contradicted`, R6 `grounding_failed`. Där vore «svaret står inte i dem» osant — G respektive E låg i paketet.

---

## De två `insufficient_data`

Bokstäver är namnordning. Facit E = sophantering.

| fall | packat | facit | oläst facit i listan |
| --- | --- | --- | --- |
| R7 | B | E | **ja** |
| R7b | H | E | **ja** |

Listan är arkivets beskrivna handlingar minus de packade. Åtta namn vardera. Den gör inte anspråk på att någon oläst handling innehåller svaret.

---

## Invarianter

- Urval, citatverifiering och svarsdomare oförändrade.
- Låset `97b4e7bfc71f` skrevs inte om.
- Trafik bara loopback.
- Inget ur handlingarna committat. Svarstexterna i `backend/out/brf1-refusal-help/` (gitignorerad).

Körbar mätning: `uv run python -m scripts.eval_brf1_refusal_help` från `backend/`. Tester: `uv run pytest -q tests/test_refusal_help.py`.
