# KBLab SBERT mot potion och e5-large — niarkivsinstrumentet — 2026-08-18

**Host:** agenntserver · **inte paketerat** · ingen ändring i `backend/app/embeddings.py`, `ops/pins.json` eller RPM · hybridvikt 50 · `BRF_LLM=fake` · KBLab på CPU.

Tredje armen på samma instrument som `e5-large-retrieval.md`. Potion- och e5-armarna kördes inte om. Nivå B redovisas inte.

`KBLab/sentence-bert-swedish-cased` (v2.0, Apache-2.0): 768 dim, `model.safetensors` **498 790 336 B (0,50 GB)**. Potionvikterna i produkten är 512 361 560 B. En vinst här kostar ingenting i paketering. Ingen torch i default-payloaden; den här körningen använde `sentence-transformers` i mätmiljön, inte i produkten.

## Beslut

**Nej. Embeddern byts inte.** Produkten stannar på `minishlab/potion-multilingual-128M`. Varken KBLab eller e5-large skeppas. `ops/pins.json` orörd.

Det som avgör är protokollcellen, 13 % mot slump 34 %. KBLab tar den till 17 %. Nollprovet landar protokoll på nonsens i 14 %. Lyftningen är magnet, inte relevans. e5 tar den till 22 % med mer signal än magneten och når inte heller slump — och kostar fyra potionvikter plus torch.

Årsredovisning och underhållsplan lyfter med båda transformrarna. Det räcker inte. Stadgar sjunker en poäng. Härjedalen föll. Paketeringspriset för KBLab är noll; cellen som skulle motivera bytet rör sig inte.

## Prefix

**e5-armen använde `query:` och `passage:`.** `E5LargeEmbedder.embed` sätter prefixet. `HybridIndex.build` kodar med `_as_query=False` → `passage:`. `HybridIndex.search` wrappas så att `_as_query=True` runt frågevektorerna → `query:`. +7 pp är inte en underskattning av saknade prefix. e5 kördes inte om.

KBLab är en vanlig SBERT. Den fick inga e5-prefix.

## Publicerad cell (inte B)

Samma 863 rader, 116 frågor, nio arkiv. Slump identisk mellan armarna (samma handlingar). Δ mot den reproducerade potion-armen.

| | potion | e5-large | KBLab | slump | Δ e5 | Δ KBLab | rader |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| alla (inte B) | 46 % (394/863) | 52 % (452/863) | 51 % (438/863) | 24 % | **+7 pp** | **+5 pp** | 863 |
| stadgar | 68 % (264/387) | 67 % (261/387) | 67 % (261/387) | 15 % | **−1 pp** | **−1 pp** | 387 |
| protokoll | 13 % (33/252) | 22 % (56/252) | 17 % (42/252) | 34 % | **+9 pp** | **+4 pp** | 252 |
| årsredovisning | 46 % (73/160) | 62 % (100/160) | 63 % (101/160) | 30 % | **+17 pp** | **+18 pp** | 160 |
| underhållsplan | 38 % (15/40) | 52 % (21/40) | 52 % (21/40) | 17 % | **+15 pp** | **+15 pp** | 40 |
| avtal | 7 % (1/14) | 43 % (6/14) | 36 % (5/14) | 19 % | **+36 pp** | **+29 pp** | 14 |
| ordningsregler | 80 % (8/10) | 80 % (8/10) | 80 % (8/10) | 18 % | **—** | **—** | 10 |

KBLab tar i princip hela e5:s lyft på årsredovisning och underhållsplan, till en fjärdedel av e5:s vikter och lite under potion i storlek. Protokollcellen är den som avgör: 13 % → 17 %, fortfarande 17 procentenheter under slump 34 %. e5 kom längre (22 %) och nådde inte heller.

Stadgar sjunker lika för båda transformerarmarna (264 → 261). Avtal är 14 rader.

Publicerade byten mot potion: e5 168 rader (107 blev träff, 49 slutade); KBLab 142 (89 / 45).

## `diff.py` — lång A+M, KBLab mot den reproducerade potion-armen

Ingestionen identisk (0 handlingar ändrade, 195 357 ord). En tunn handling: Faran/`protokoll-3.pdf`.

| | potion | KBLab | skillnad | rader |
| --- | ---: | ---: | ---: | ---: |
| alla lång | 47 % | 51 % | **+3 pp** | 754 |
| protokoll | 13 % | 16 % | **+3 pp** | 231 |
| årsredovisning | 50 % | 67 % | **+17 pp** | 112 |
| stadgar | 68 % | 67 % | **−1 pp** | 387 |

120 av 754 långa rader bytte utfall: 69 blev träff, 43 slutade vara träff.

Härjedalen föll 70 % → 63 % på lång form, samma arkiv som föll mot e5. Inget annat arkiv föll.

## Nollprov

Tolv neutrala frågor × nio arkiv = 108.

| handlingstyp | potion | e5-large | KBLab |
| --- | ---: | ---: | ---: |
| årsredovisning | 34/108 (31 %) | 29/108 (27 %) | 29/108 (27 %) |
| stadgar | 23/108 (21 %) | 16/108 (15 %) | 22/108 (20 %) |
| underhållsplan | 18/108 (17 %) | 16/108 (15 %) | 17/108 (16 %) |
| protokoll | 6/108 (6 %) | 11/108 (10 %) | 15/108 (14 %) |
| ordningsregler | 18/108 (17 %) | 21/108 (19 %) | 15/108 (14 %) |
| informationsbrev | 6/108 (6 %) | 9/108 (8 %) | 6/108 (6 %) |
| energideklaration | 3/108 (3 %) | 5/108 (5 %) | 4/108 (4 %) |
| avtal | 0/108 (0 %) | 1/108 (1 %) | 0/108 (0 %) |

KBLabs protokoll på nonsens är 14 %. På riktiga protokollfrågor 17 %. Lyftningen 13 → 17 ligger inom magneten. e5: 10 % nonsens mot 22 % riktiga — mer signal, fortfarande under slump.

Under konfidenströskeln 0,18: potion 37/108, e5 0/108, KBLab 48/108. Medelkonfidens 0,21 / 0,50 / 0,20. Tröskeln är kalibrerad mot potion.

## Armar

| | potion | e5-large | KBLab |
| --- | --- | --- | --- |
| modell | `minishlab/potion-multilingual-128M` (produkt) | `intfloat/multilingual-e5-large` | `KBLab/sentence-bert-swedish-cased` |
| prefix | inga | `query:` / `passage:` | inga |
| vikter | 512 361 560 B | ~2,09 GiB | 498 790 336 B |
| väggklocka | 13 min | 123 min | 42 min |
| utdata | `resultat-potion.json` | `resultat-e5.json` | `resultat-kblab.json` |

Elva frågor mot ett arkiv kördes inte. De är riktningsgivande mot det här instrumentet, aldrig avgörande.
