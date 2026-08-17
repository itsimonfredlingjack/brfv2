# BRF-1: Ekens egna handlingar — 2026-08-17

**Host:** agenntserver · PDF under gitignorerad `DONT_PUSH_brf_stuff/eken-egen/` · store `/tmp/brf1-store-eken`

Fem offentliga handlingar från föreningens sajt. Org.nr och personnamn stannar i PDF:erna. Här bara siffror och källklass.

## Stadgarna är samma skanning två gånger

Laptopens stadgar och sajtens stadgar har **identisk SHA-256**. Båda saknar textlager (11 sidor, 0 tecken, 11 bilder). Det är inte en digitalt född tvilling till en OCR-version. Det är samma skannade fil.

Därför gick OCR-isoleringen inte att köra. De elva fallen (facit E och G, båda skannade avtal) har ingen digital motpart på sajten. Att lägga in stadgarna i det nio handlingars arkivet flyttar dessutom bokstäverna — G är inte längre parkeringsavtalet — så en omkörning av de elva mot «båda» hade inte mätt OCR. Den mätningen är **inte gjord**, och ska inte räknas som nollskillnad. OCR mot digitalt textlager på samma dokument är en öppen fråga, inte ett resultat.

Åtta av de ursprungliga tio på laptopen är skanningar. Stadgarna hör dit. De tre sajthandlingarna som faktiskt har textlager är revisionsberättelsen och bofaktabladet; årsredovisningen är Print-to-PDF utan textlager (se nedan).

## Vad som hämtades

| handling | sidor | textlager före ingest | `source` efter `add_document` | ord efter ingest |
| --- | ---: | --- | --- | ---: |
| årsredovisning 2025 | 16 | nej (Print-to-PDF, vektorspår, 11 tecken totalt) | `scanned` | 2 650 |
| revisionsberättelse 2025 | 4 | ja | `digital` | 1 389 |
| stadgar | 11 | nej | `scanned` | 2 723 |
| ekonomisk plan | 14 | nej | `scanned` | 2 906 |
| bofaktablad | 24 | ja | `digital` | 3 133 |

Årsredovisningen är producerad med «Microsoft: Print To PDF». Ingestionsvägen rasteriserar och OCR:ar. Det är **inte** samma klass som en kamera-skanning, men det är samma kodväg (`source=scanned`). En sida förblev tunn (`thin_pages=1`).

Ekonomisk plan och bofaktablad fanns inte i det nio handlingars arkivet. De ligger nu i store:n som egna dokument.

## Arkivet som mättes

`/tmp/brf1-store` (nio handlingar, BRF-1-bokstäver) kopierades till `/tmp/brf1-store-eken`. De fem lades till via `Store.add_document`. De nio behöll sina beskrivningar. Nya beskrivningar genererades vid ingest och frystes. Version `417397b9f07a`. `n_describe_calls=0` under den efterföljande femkörningen.

Namnordning efter tillägget: 14 handlingar, A–N. Facithandlingarna för ränta/tvådokumentsfrågorna är **N** (årsredovisning, OCR) och **K** (stadgar, OCR). Revisionsberättelsen (J) är digital; tvådokumentsfrågorna packade den som extra handling men citerade K+N.

Den andra föreningens digitala årsredovisning (`Årsredovisning.pdf`, J i `/tmp/brf1-store-with-ars`) är **inte** med i Ekens store.

## Elva fallen

Orörda. Ingen digital tvilling, ingen omkörning mot två stadgeversioner. Gällande dokumentväg för de elva är fortfarande 8–8 (`docs/evidence/brf1-locked-pack.md`). Skillnaden OCR mot digitalt född text på samma handling är inte isolerad.
