# multilingual-e5-large mot potion — niarkivsinstrumentet — 2026-08-18

**Host:** agenntserver · **inte paketerat** · ingen ändring i `backend/app/embeddings.py` · hybridvikt 50 (BM25 ⊕ dense) · `BRF_LLM=fake` (beskrivningar används inte) · e5 på CPU så Gemma kvar på GPU.

Två fulla armar, samma kod, samma nio arkiv, samma facit. Enda skillnaden är embeddern. Det är XS-78: baslinjen är själv mätt med potion, så ett byte till e5 inte blandas ihop med senare produktändringar.

Nivå B (egna typfrågor) är inte resultat. Den skrevs ut av `diff.py` längst ned; den återges inte här.

Instrument: `~/brf-corpus-public/matning/` (utanför repot). Nio arkiv under `~/brf-corpus-public/arkiv/`. Publicerad cell: A och M på ordagrann text, F på sin enda form. `tabell.py` är den tabellen. `diff.py` mot den reproducerade potion-armen jämför samma rader på lång form (A+M, 754 rader) och tar inte med F.

Linear-kortet nämner 105 frågor / 863 rader. Den återställda facitfilen har 116 publicerade frågor (A 66 + M 30 + F 20) och **exakt 863 rader**. Potion-armen träffar låsets typceller: stadgar 68 % (låst 70 %), årsredovisning 46 % (låst 45 %), protokoll **13 % mot slump 34 %**. 105 är inte unika-id i den här filen. Låset som går att reproducera är radantalet och typcellerna.

Elva frågor mot ett arkiv är riktningsgivande mot det här instrumentet, aldrig avgörande. Den här körningen gick inte mot de elva.

## Det som avgör

Protokollcellen rör sig **13 % → 22 %**, mot slumpens 34 %, och når den inte. Fortfarande 12 procentenheter under slump.

Årsredovisning lyfter **46 % → 62 %** och ligger då över slump 30 %. Underhållsplan **38 % → 52 %**. Stadgar **68 % → 67 %** (264 → 261 av 387): inte en kollaps, men cellen sjunker medan protokoll lyfter. Avtal **7 % → 43 %** på 14 rader — för litet att hänga ett paketbeslut på.

e5 är inte inbakat. Kostnaden står i `e5-large-cost.md`. Den här filen är bara retrieval-effekten.

## Publicerad cell (inte B)

| | potion | slump | e5-large | slump | skillnad | rader |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| alla (inte B) | 46 % (394/863) | 24 % | 52 % (452/863) | 24 % | **+7 pp** | 863 |
| stadgar | 68 % (264/387) | 15 % | 67 % (261/387) | 15 % | **−1 pp** | 387 |
| protokoll | 13 % (33/252) | 34 % | 22 % (56/252) | 34 % | **+9 pp** | 252 |
| årsredovisning | 46 % (73/160) | 30 % | 62 % (100/160) | 30 % | **+17 pp** | 160 |
| underhållsplan | 38 % (15/40) | 17 % | 52 % (21/40) | 17 % | **+15 pp** | 40 |
| avtal | 7 % (1/14) | 19 % | 43 % (6/14) | 19 % | **+36 pp** | 14 |
| ordningsregler | 80 % (8/10) | 18 % | 80 % (8/10) | 18 % | **—** | 10 |

Slump är `antal(primär typ i arkivet) / antal handlingar i arkivet`, medel över raderna. Samma definition som `rapport.py`.

168 publicerade rader bytte utfall: 107 blev träff, 49 slutade vara träff. Protokoll: +28 / −5. Stadgar: +35 / −38 (netto −3, stor churn).

## `diff.py` — lång A+M mot den reproducerade potion-armen

Ingestionen är identisk (0 handlingar ändrade, 195 357 ord båda sidor). En tunn handling kvar: Faran/`protokoll-3.pdf`.

| | potion | e5-large | skillnad | rader |
| --- | ---: | ---: | ---: | ---: |
| alla lång | 47 % | 53 % | **+5 pp** | 754 |
| protokoll | 13 % | 21 % | **+8 pp** | 231 |
| årsredovisning | 50 % | 68 % | **+18 pp** | 112 |
| stadgar | 68 % | 67 % | **−1 pp** | 387 |

144 av 754 långa rader bytte utfall: 86 blev träff, 46 slutade vara träff.

Per arkiv på lång form föll **Härjedalen 70 % → 63 %** och Dikten 2 46 % → 44 %. Slottshörnet 41 % → 62 % är den största lyftningen. Spridningen mellan arkiv 40–70 % → 43–71 %.

## Nollprov

Tolv neutrala frågor × nio arkiv = 108. Samma ingestionsväg, ingen föreningstext i frågan.

| handlingstyp | potion | e5-large |
| --- | ---: | ---: |
| årsredovisning | 34/108 (31 %) | 29/108 (27 %) |
| ordningsregler | 18/108 (17 %) | 21/108 (19 %) |
| stadgar | 23/108 (21 %) | 16/108 (15 %) |
| underhållsplan | 18/108 (17 %) | 16/108 (15 %) |
| protokoll | 6/108 (6 %) | 11/108 (10 %) |
| informationsbrev | 6/108 (6 %) | 9/108 (8 %) |
| energideklaration | 3/108 (3 %) | 5/108 (5 %) |
| avtal | 0/108 (0 %) | 1/108 (1 %) |

Under konfidenströskeln 0,18: potion 37/108, e5 0/108. Medelkonfidens 0,21 mot 0,50. Tröskeln är kalibrerad mot potion; den jämför inte kvalitet mellan armarna.

Protokoll på nonsens 6 % → 10 %. Protokoll på riktiga frågor 13 % → 22 %. Lyftningen är större än magnetskiftet, men cellen ligger fortfarande under slump.

## Armar

| | potion | e5-large |
| --- | --- | --- |
| embedder | `model2vec:potion-multilingual-128M` (produkt) | `intfloat/multilingual-e5-large`, injicerad i processen, prefix `query:` / `passage:` |
| enhet | CPU (statisk) | CPU (`BRF_E5_DEVICE=cpu`) |
| väggklocka | 13 min (23:48–00:01 UTC) | 123 min (00:01–02:04 UTC) |
| rader / hoppade | 1687 / 246 | 1687 / 246 |
| utdata | `resultat-potion.json`, `nollprov-potion.json` | `resultat-e5.json`, `nollprov-e5.json` |

e5-vikterna laddades från cache. Produktpinnen, `ops/pins.json` och desktop-RPM:en är orörda.

## Elva fallen

Inte kört. 8 → 7 på BRF-1 är inte en regression av numerikgrinden och inte ett e5-resultat; se `brf1-numeric-normalize.md`. Elva frågor mot ett arkiv säger ingenting om protokollcellen 13 % mot 34 %.
