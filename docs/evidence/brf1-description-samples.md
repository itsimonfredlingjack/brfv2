# BRF-1: fem samplingar av samma beskrivningsprompt — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `5310cbf` · loopback · `scripts/eval_brf1_description_samples.py`

Sista mätningen på urvalet. Spåret är stängt.

Samma produktprompt som låset (`description_prompt`), fem oberoende samplingar. Generation vid temperature **1.0** (serverns default) — produktens `complete()` är 0 och skulle inte ge olika stickprov. Isolerat enhandlingsurval mot varje uppsättning vid produktens temperature 0. Ingen `ask()`. Låset `97b4e7bfc71f` oförändrat. Noll externa anslutningar. Texterna i `backend/out/brf1-description-samples/` (gitignorerad).

Alla nio handlingar fick fem **olika** texter. Ingen sampling var identisk med låset.

---

## Slutsats

**Urvalsspåret är stängt.** Unionen planar på **9 redan vid första samplingen**, spridningen mellan samplingar är **6–9**, och **R6 och R7b nås aldrig**. Flera samplingar är inte en mekanism värd att bygga.

Efter första uppsättningen var unionen redan 9. Uppsättning 2–5 lade inte till ett enda fall. Taket är samma 9 som de två historiska stickproven, inte 10.

Träffkvoten per uppsättning är **9, 7, 6, 7, 7**. Spann **6–9**. Det är ett produktproblem om beskrivningar skrivs om: samma arkiv skulle ge olika urval beroende på när texterna råkade genereras. Låset som redan finns är svaret på det, inte fem uppsättningar i drift.

R6 och R7b träffades av **ingen** av de fem. R7 träffades i en sampling och jagas inte.

---

## Träffkvot per uppsättning

| uppsättning | träff |
| ---: | ---: |
| 1 | **9 / 11** |
| 2 | **7 / 11** |
| 3 | **6 / 11** |
| 4 | **7 / 11** |
| 5 | **7 / 11** |

Spann **6–9**, spridning **3**.

---

## Kumulativ union

| efter n uppsättningar | fall någon träffat |
| ---: | ---: |
| 1 | **9** |
| 2 | **9** |
| 3 | **9** |
| 4 | **9** |
| 5 | **9** |

Planar ut på 9. Inte 7. Inte 10.

De nio: R1, R2, R3, R3b, R4, R5, R5b, R7, R8. Aldrig i unionen: **R6, R7b**.

R7 i unionen kommer enbart från uppsättning 1. Utan den samplingen är unionen av de fyra övriga **8 / 11** (R3b kommer in via uppsättning 5; R7 försvinner). Extra samplingar höjer ett oturligt lås mot 8, inte mot 10.

---

## Per fall

| fall | facit | 1 | 2 | 3 | 4 | 5 | någon |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | G | **G** | **G** | **G** | **G** | **G** | ja |
| R2 | G | **G** | **G** | **G** | **G** | **G** | ja |
| R3 | G | **G** | **G** | **G** | **G** | **G** | ja |
| R4 | E | **E** | **E** | **E** | **E** | **E** | ja |
| R5 | E | **E** | **E** | C | **E** | D | ja |
| R6 | E | F | D | D | D | D | **nej** |
| R7 | E | **E** | B | B | B | H | ja (1/5) |
| R8 | E | **E** | **E** | **E** | **E** | **E** | ja |
| R3b | G | **G** | B | B | B | **G** | ja |
| R5b | E | **E** | **E** | **E** | **E** | **E** | ja |
| R7b | E | H | H | A | A | H | **nej** |

R1–R4, R8, R5b är 5/5. R5 och R3b rör sig. R6 rör sig mellan fel handlingar, aldrig E. Den gamla cachen i unionstestet träffade R6; de här fem samplingarna gjorde det inte.

---

## De fem hårda

| fall | någon av fem | jaga |
| --- | --- | --- |
| R5 | ja (4/5) | nej — täcks ofta |
| R6 | nej (0/5) | nej i det här spåret — urvalssteget tog slut på 9 |
| R7 | ja (1/5) | **nej** — handskriven koppling |
| R3b | ja (2/5) | nej — täcks ibland |
| R7b | nej (0/5) | **nej** — handskriven koppling |

R7 och R7b har nu motstått nio mätningar som mekanism att jaga. R7 träffade en gång här och ändrar inte det: de dokumenteras som fallen som kräver en handskriven koppling mellan frågespråk och handling.

---

## Vad det avgör

Frågan var: planar unionen ut runt 7–8 (då var 9 två lyckliga drag) eller fortsätter den mot 9–10 och stannar där (då är flera samplingar värd att bygga)?

Den stannar på **9** och når inte 10. Första samplingen var redan 9; de fyra följande adderade noll. Flera samplingar återupptäcker samma tak som de två historiska stickproven, inte ett högre. Byggs inte. Urvalsspåret är stängt.

Spridningen 6–9 är skälet att beskrivningar är låsta, inte skälet att köra fem generatorer i produkt.

---

## Invarianter

- `ask()` anropades inte. `app/answer.py` rördes inte.
- Låset `97b4e7bfc71f` oförändrat.
- Trafik bara loopback.
- Inget ur handlingarna eller samplingarna committat.

Körbar mätning: `uv run python -m scripts.eval_brf1_description_samples` från `backend/`. Tester: `uv run pytest -q tests/test_query_expansion.py`.
