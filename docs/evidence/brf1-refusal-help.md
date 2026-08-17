# BRF-1: vägran som svar — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · arbetskopia mot `1644577` · loopback · `scripts/eval_brf1_refusal_help.py`

En `ask()` per fall, dokumentväg, låset `97b4e7bfc71f`. Urval, citatkedja och svarsdomare orörda. `insufficient_data` får tre satser i stället för modellens «otillräckligt underlag»: vilka handlingar som lästes, att svaret inte står i dem, och allmänt vilken sorts handling som brukar reglera frågan — plus om någon sådan finns bland beskrivningarna. Ingen lista över vad en förening «ska» ha. Noll externa anslutningar. `n_describe_calls=0`.

Måttet: för varje `insufficient_data` är facithandlingen känd. Namnger vägran den sorten?

---

## Slutsats

**0 av 2.** De två `insufficient_data`-vägran (R7, R7b) namngav inte facitsorten. Första ledet var sant i båda: de läste fel handling. Tredje ledet gissade «allmänna villkor» respektive «ett leveransavtal». Facit är sophanteringsavtalet.

Vägran är inte längre en återvändsgränd om vad som lästes. Den är fortfarande inte en pekare mot rätt sorts handling i de fall som faktiskt vägras.

---

## Talet

| | |
| --- | ---: |
| fall | 11 |
| vägrade totalt | 4 |
| `insufficient_data` (ny text) | **2** (R7, R7b) |
| namngav facitsort | **0 / 2** |

Övriga vägran skrevs inte om: R1 `citation_contradicted`, R6 `grounding_failed`. Där vore «svaret står inte i dem» osant — G respektive E låg i paketet.

---

## De två `insufficient_data`

Bokstäver är namnordning. Facit E = sophantering.

| fall | packat | facit | sortsmening | match i arkivet | namngav facitsort |
| --- | --- | --- | --- | --- | --- |
| R7 | B (teknisk förvaltning) | E | allmänna villkor | ingen | **nej** |
| R7b | H (kommunikationsoperatör) | E | ett leveransavtal | medialeverans + H | **nej** |

R7, fråga om Stena måste säga till innan prishöjning. Läste teknisk förvaltning. Sade att svaret inte står där. Allmänt: allmänna villkor. Ingen sådan handling bland beskrivningarna. Sophanteringsavtalet nämndes inte.

R7b, fråga om leverantören får höja priset utan att meddela. Läste kommunikationsoperatörsavtalet. Allmänt: ett leveransavtal. Matchade förskolans medialeverans och samma kommunikationsavtal. Inte E.

Båda är de dokumenterade fallen som kräver en handskriven koppling mellan frågespråk och handling. Den allmänna sortsmeningen löste inte kopplingen.

---

## Vad som inte räknas in

R1 och R6 vägrades av andra grindar. De behöll grindens egen mening. Numerisk grind och domare anropades inte om på `insufficient_data`.

En körning, inte fem. R7/R7b har varit `insufficient_data` i varje femkörning på låset; sortsmeningen är det som kunde ha rört sig.

---

## Invarianter

- Urval, citatverifiering och svarsdomare oförändrade.
- Låset `97b4e7bfc71f` skrevs inte om.
- Trafik bara loopback.
- Inget ur handlingarna committat. Svarstexterna i `backend/out/brf1-refusal-help/` (gitignorerad).

Körbar mätning: `uv run python -m scripts.eval_brf1_refusal_help` från `backend/`. Tester: `uv run pytest -q tests/test_refusal_help.py`.
