# BRF-1: låsta beskrivningar, inget räknetak — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **embedder:** `model2vec:potion-multilingual-128M` · loopback · `scripts/eval_brf1_locked.py`

Två produktändringar mot femkörningen i `docs/evidence/brf1-variance.md`:

1. Beskrivningarna är låsta. Version `97b4e7bfc71f` (sha256-12 av namn + beskrivningstext). Ingen omskrivning under mätningen (`n_describe_calls=0`). Låset: `backend/eval/brf1-descriptions.lock.json`.
2. Räknegränsen tre är borta. Parsern behåller modellens lista. Packaren tar handlingar i den ordningen tills `n_ctx`. Urvalsprompten säger fortfarande «1–3»; den kapar inte.

Samma elva fall, samma nio handlingar, svarsdomaren i `ask()`. 55 `ask()`, dokumentväg. Noll externa anslutningar. `fullCorpusTokenThreshold` återställd.

Bokstäver i tabellerna är namnordning (facit E = sophantering). Katalogordningen är en annan; R5:s modelllista `C,D,E,F` är katalogbokstäver.

## Spannet

| väg | facit av 11, fem körningar | fel handling | vägrad |
| --- | --- | --- | --- |
| dokumentväg, låst + utan räknetak | **8–8** (8, 8, 8, 8, 8) | 0–0 | 3–3 |

Före ändringen, samma mått, räknetak tre: dokumentväg **6–6**, retrieval **5–5** (`docs/evidence/brf1-variance.md`). Retrieval kördes inte om.

Gällande dokumentväg: **8 facit** över fem körningar. Spannet är 8–8.

## R5 — analysen stämde

Modellen svarade `{"documents": ["C", "D", "E", "F"]}` i katalogbokstäver. Katalog-F är namn-E (sophantering). Med taket tre släpptes den fjärde; facittexten fanns inte i prompten.

Utan taket packades C, D, E, F (namnordning). Prefix 17 883 token. Citat ur E. **Facit i alla fem.**

## R6 — samma mekanism, inte en ny åtgärd

R6 valde samma fyra. Tidigare fel handling (C) när E kapades. Nu E i paketet, citat ur E, **facit i alla fem.** R7 och R7b rördes inte.

## R7 och R7b

Oförändrade urvalsmissar. R7 packade B (teknisk förvaltning), R7b packade H (kommunikationsoperatör). `insufficient_data`. Facit E namngavs inte. Ingen åtgärd här.

## Packstorlek

| fall | valt / packat (namnordning) | n | prefix |
| --- | --- | ---: | ---: |
| R1 | G | 1 | 2132 |
| R2 | G | 1 | 2132 |
| R3 | G | 1 | 2132 |
| R4 | E | 1 | 2389 |
| R5 | C, D, E, F | 4 | 17883 |
| R6 | C, D, E, F | 4 | 17883 |
| R7 | B | 1 | 6337 |
| R8 | E | 1 | 2389 |
| R3b | G | 1 | 2132 |
| R5b | E | 1 | 2389 |
| R7b | H | 1 | 3777 |

`n_packed` **1–4** av 9. Största prefix 17 883 mot helarkivets ~47 k och tak ~63 k. Vald mängd och packad mängd var lika i varje fall — tokentaket kapade inget. De två vägarna konvergerar **inte**. Dokumentvägen är fortfarande ett urval, inte helarkivet i omgångar.

## Per fall (av fem)

| fall | facit | fel handling | vägran | utfall | grind (körning 1) |
| --- | ---: | ---: | ---: | --- | --- |
| R1 | 0 | 0 | 5 | vägrad ×5 | `citation_contradicted` |
| R2 | 5 | 0 | 0 | facit ×5 | — |
| R3 | 5 | 0 | 0 | facit ×5 | — |
| R4 | 5 | 0 | 0 | facit ×5 | numerisk reparation `2024` |
| R5 | 5 | 0 | 0 | facit ×5 | — |
| R6 | 5 | 0 | 0 | facit ×5 | — |
| R7 | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |
| R8 | 5 | 0 | 0 | facit ×5, alltid markerat | `besvarar_inte` |
| R3b | 5 | 0 | 0 | facit ×5 | — |
| R5b | 5 | 0 | 0 | facit ×5 | — |
| R7b | 0 | 0 | 5 | vägrad ×5 | `insufficient_data` |

R8 visades med *Svaret kan vara ofullständigt.* i alla fem, som i femkörningen med tak.

## Vad som är låst

Beskrivningarna genereras en gång per extraherad textversion, sparas på dokumentet, skrivs om bara när fingerprinten av sidtexten ändras, och den gamla texten ligger kvar i `description_previous`. Eval sätter `_descriptions_frozen` och spelar upp låset, så en omkörning av den här mätningen använder `97b4e7bfc71f` så länge låsfilen är densamma.
