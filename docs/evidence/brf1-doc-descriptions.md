# BRF-1: innehållsbeskrivningar och helarkivkatalog — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `f82f753` · **embedder:** `model2vec:potion-multilingual-128M`

> **Enkörning.** 7/11, 5/1/5 och 7/1/3 är en körning per fall. Spann över fem körningar av `ask()`: `docs/evidence/brf1-variance.md`.

Samma elva fall och samma nio handlingar som `docs/evidence/brf1-doc-select.md` och `docs/evidence/brf1-full-corpus.md`. Ingen produktändring — mätning via skript som patchar prompten i minnet. Ingen ny svarsväg, ingen grind, fan-out rördes inte, `r01` kördes inte. Trafik bara loopback.

Två mätningar på samma genererade beskrivningar:

1. **Handlingsval med beskrivning** — samma modellanrop som katalogmätningen, men listan visar bara maskinellt genererad beskrivning av vad handlingen reglerar (inte titel, inte struktur).
2. **Helarkiv med katalog** — en rad per handling (`namn: beskrivning`) före `UTDRAG:`, frågan sist. Jämförs mot helarkivbaslinjen **5 / 1 / 5** (`verifierat_i_facit` / `verifierat_i_fel_handling` / `vägrad`).

Beskrivningarna genererades en gång per handling ur fulltext (samma modell), cachade i `backend/out/brf1-doc-descriptions/descriptions.json`. Katalogen lade till **1380** prefixtokens (47402 → 48782).

---

## 1. Handlingsval: beskrivning i stället för titel + struktur

Baslinje från `docs/evidence/brf1-doc-select.md`: modellen med titel + strukturbeskrivning träffade **6 / 11**.

| metod | träff |
| --- | ---: |
| titel + struktur (baslinje) | **6 / 11** |
| innehållsbeskrivning | **7 / 11** |

### Per fall

| fall | facit | titel+struktur | beskrivning |
| --- | --- | --- | --- |
| R1 | G | **G** | **G** |
| R2 | G | **G** | **G** |
| R3 | G | **G** | H |
| R4 | E | **E** | **E** |
| R5 | E | C | **E** |
| R6 | E | I | C |
| R7 | E | D | **E** |
| R8 | E | **E** | **E** |
| R3b | G | D | B |
| R5b | E | **E** | **E** |
| R7b | E | D | A |

### De fem där alla tre metoder missade (fokus)

| fall | titel+struktur | beskrivning | utfall |
| --- | --- | --- | --- |
| R5 | C | **E** | stängt — beskrivningen nämner administrativ avgift 494 kr |
| R6 | I | C | kvar — C (medialeverans) vinner över E trots driftskostnader i beskrivningen |
| R7 | D | **E** | stängt — beskrivningen nämner prisjusteringar |
| R3b | D | B | kvar — B (teknisk förvaltning) slår G; *bil* finns inte i G:s beskrivning |
| R7b | D | A | kvar — *leverantören* pekar mot A (ekonomisk förvaltning), inte E |

Beskrivningen räddade **R5** och **R7** som titeln inte kunde. Den tappade **R3** (parkering → H, kommunikationsavtal). Netto **+1**.

### Slutsats handlingsval

**7 av 11 är inte tydligt över 6.** En träff till räcker inte för att säga att glappet är maskinellt stängt. Beskrivningarna hjälper när frågans begrepp saknas i titeln men finns i innehållet (administrativ avgift, prisjustering). De hjälper inte när frågan använder ord som pekar fel (leverantör → A, bil → B) eller när flera handlingar delar samma tema (driftskostnader: C mot E).

**Vägen framåt:** beskrivningarna är värda att ha, men fyra fall — R3b, R6, R7b och den nya missen R3 — kräver fortfarande kunskap som inte finns i handlingarna eller pekar fel även med beskrivning. Där måste någon skriva kopplingen för hand, eller så behövs en annan mekanism än ren beskrivning.

---

## 2. Helarkiv med katalog överst

Prompt: `KATALOG:` (9 rader) → `UTDRAG:` → `FRÅGA:` sist. Prefix cachas med katalog inkluderad (`cache_n≈48789` vid frågeanrop).

| | `verifierat_i_facit` | `verifierat_i_fel_handling` | `vägrad` |
| --- | ---: | ---: | ---: |
| helarkiv utan katalog (baslinje) | **5** | **1** | **5** |
| helarkiv med katalog | **6** | **1** | **4** |

`verifierat_i_fel_handling` gick **inte** till noll. R7b citerar fortfarande B s3, inte E.

### Per fall

| fall | facit | utan katalog | med katalog |
| --- | --- | --- | --- |
| R1 | G | verifierat_i_facit | verifierat_i_facit |
| R2 | G | vägrad | **verifierat_i_facit** |
| R3 | G | vägrad | **verifierat_i_facit** |
| R4 | E | verifierat_i_facit | verifierat_i_facit |
| R5 | E | verifierat_i_facit | vägrad (`numeric_grounding_failed`) |
| R6 | E | vägrad | vägrad |
| R7 | E | vägrad | vägrad |
| R8 | E | verifierat_i_facit | verifierat_i_facit |
| R3b | G | verifierat_i_facit | verifierat_i_facit |
| R5b | E | vägrad | vägrad |
| R7b | E | verifierat_i_fel_handling (B s3) | verifierat_i_fel_handling (B s3) |

Katalogen återställde **R2** och **R3** — de fall där facit låg i mitten av prefixet utan översikt. Den tappade **R5** (numerisk grind). R7b är oförändrad: modellen har hela arkivet och katalogen men citerar ändå fel handling om prishöjning utan förvarning.

### Slutsats helarkivkatalog

Katalogen är billig (+1380 tokens) och gav **+1 facit** netto, men den löser inte det allvarligaste felet. Ett förankrat citat ur fel handling kvarstår i R7b. Katalogen ger översikt nog för att hitta parkeringsavtalet (R2, R3) men räcker inte för att modellen ska välja sophanteringsavtalet när frågan säger *leverantören*.

**Vägen framåt:** katalog + beskrivning är värt att prova i produkten som komplement till helarkivvägen — särskilt mot lost-in-the-middle — men det räcker inte som enda åtgärd mot fel-handling-citat. R7b behöver något som binder frågans vokabulär till rätt handling, inte bara en översikt över innehållet.

---

## Beskrivningar per handling (bokstav)

Kortform; fulltext i cachefilen.

| | vad handlingen styr (genererat) |
| --- | --- |
| A | Ekonomisk förvaltning, bokföring, budget, 3 967 kr/mån |
| B | Teknisk förvaltning, felanmälan, jourtjänst, 21 825 kr/mån |
| C | Medialeverans värme/VV mellan förening och Stena, submätare, adminavgift |
| D | Mobilitet (bil-/cykelpool, kollektivtrafikkort), schablon 2 527 kr/mån, admin 494 kr |
| E | Gårdsskötsel, snöröjning, sophantering, kostnadsfördelning BOA, prisjusteringar, admin 494 kr |
| F | Delägarförvaltning gemensamhetsanläggningar, fem parter |
| G | Hyresavtal 25 parkeringsplatser, 60 000 kr/kvartal |
| H | Kommunikationsoperatör iTUX, fastighetsnät, 56 lägenheter |
| I | Underhållsplan 2024–2053, ~15,7 Mkr totalt |
