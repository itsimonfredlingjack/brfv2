# BRF-1: årsredovisning i arkivet — 2026-08-16

**Host:** agenntserver · PDF gitignorerad under `DONT_PUSH_brf_stuff/` · store `/tmp/brf1-store-with-ars`

Eken-arkivet som BRF-1 mättes mot hade nio handlingar och ingen årsredovisning. Ränta, soliditet och tvådokumentsfrågorna väntade på en riktig rapport, inte på en felklassad fil (`docs/evidence/document-ask.md`).

En born-digital årsredovisning från den offentliga korpusen (annan förening; Ekens egen saknas fortfarande) kopierades in som `Årsredovisning.pdf`. 48 sidor, digitalt textlager, 9 498 ord, 74 chunkar. Flerårsöversikt, resultaträkning och balansräkning finns i textlagret. Inga belopp eller organisationsuppgifter i den här filen.

Namnet sorterar efter de nio befintliga, så bokstäverna A–I är orörda. Årsredovisningen är **J**.

## Var den ligger

| plats | innehåll |
| --- | --- |
| `/tmp/brf1-store` | nio handlingar, oförändrat — BRF-1-bokstäver och elva-fallseval |
| `/tmp/brf1-store-with-ars` | samma nio plus J, ingestion via `Store.add_document` |
| `DONT_PUSH_brf_stuff/` | de nio PDF:erna under originalnamn plus `Årsredovisning.pdf` |

Beskrivning genererades vid ingestion (samma modell, loopback). Defaulten i `ask()` rördes inte.

## Helarkiv ryms inte

Efter tillägget: `prefix_tokens=77888`, tak `65536 − 512 − 1800 = 63224`, `bound=n_ctx`, `use_full_corpus=False`. De nio ensamma rymdes (~47k). Dokumentvägen är produktens huvudväg och packar 1–3 handlingar; ränta/soliditet kan köras där utan att helarkivet ryms.

## Inte kört än

Ränte-, soliditets- och tvådokumentsfrågorna är inte omkörda mot J. Arkivet finns. Frågorna väntar på en människa.

Det här är **inte** Ekens egen årsredovisning. En annan förenings offentliga rapport duger för att mäta ränta och soliditet. Den ska inte sättas framför Ekens styrelse. Styrelsesittningen väntar på deras egna handlingar.

Stadgarna från laptopens tiofilersarkiv ingår inte i den här tian. Att lägga till dem under namn som `Stadgar …` skulle hamna mitt i A–I och flytta bokstäverna.
