# BRF-1: årsredovisning i arkivet — 2026-08-16

**Host:** agenntserver · PDF gitignorerad under `DONT_PUSH_brf_stuff/` · store `/tmp/brf1-store-with-ars`

Eken-arkivet som BRF-1 mättes mot hade nio handlingar och ingen årsredovisning. Ränta, soliditet och tvådokumentsfrågorna väntade på en riktig rapport, inte på en felklassad fil (`docs/evidence/document-ask.md`).

En born-digital årsredovisning från den offentliga korpusen (annan förening) kopierades in som `Årsredovisning.pdf`. 48 sidor, digitalt textlager, 9 498 ord, 74 chunkar. Flerårsöversikt, resultaträkning och balansräkning finns i textlagret. Inga belopp eller organisationsuppgifter i den här filen. Ekens egen rapport ingestades senare, separat (`docs/evidence/brf1-eken-egen.md`). OCR mot digitalt textlager på samma dokument är fortfarande inte isolerat.

Namnet sorterar efter de nio befintliga, så bokstäverna A–I är orörda. Årsredovisningen är **J**.

## Var den ligger

| plats | innehåll |
| --- | --- |
| `/tmp/brf1-store` | nio handlingar, oförändrat — BRF-1-bokstäver och elva-fallseval |
| `/tmp/brf1-store-with-ars` | samma nio plus J, ingestion via `Store.add_document` |
| `DONT_PUSH_brf_stuff/` | de nio PDF:erna under originalnamn plus `Årsredovisning.pdf` |

Beskrivning genererades vid ingestion (samma modell, loopback). Defaulten i `ask()` rördes inte.

## Helarkiv ryms inte

Efter tillägget: `prefix_tokens=77888`, tak `65536 − 512 − 1800 = 63224`, `bound=n_ctx`, `use_full_corpus=False`. De nio ensamma rymdes (~47k). Dokumentvägen är produktens huvudväg och packar valda handlingar tills tokentaket nås (mätt 1–4 av 9 på BRF-1, `docs/evidence/brf1-locked-pack.md`); ränta/soliditet kan köras där utan att helarkivet ryms.

## Inte kört än mot J — kört mot Ekens egen

Ränte-, soliditets- och tvådokumentsfrågorna kördes inte om mot J. De kördes 2026-08-17 mot Ekens *egen* årsredovisning och stadgar (`docs/evidence/brf1-eken-finance.md`, `docs/evidence/brf1-eken-egen.md`). J är kvar som digital baslinje från en annan förening: ränta och soliditet mot J gav 0–0 facit (numerisk grind), mot Ekens OCR-rapport 3–3 av 4.

Ekens egen årsredovisning ligger i `DONT_PUSH_brf_stuff/eken-egen/`. Den är Print-to-PDF utan textlager och ingestas som `scanned`. Stadgarna från sajten är samma skanning som laptopens — identisk SHA-256, ingen digital tvilling. OCR mot digitalt född text på samma handling är en öppen fråga, inte ett resultat.

Stadgarna från laptopens tiofilersarkiv ingår inte i tian med J. I `/tmp/brf1-store-eken` (nio plus fem egna) är de handling K och flyttar bokstäverna. BRF-1:s elva fall är orörda mot den nio handlingars store:n.
