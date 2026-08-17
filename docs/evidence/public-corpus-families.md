# Offentlig årsredovisningskorpus — mallfamiljer — 2026-08-17

**Plats:** `~/brf-corpus-public/arsredovisningar/` (utanför repot, `public_scraped`) · **Host:** agenntserver, rsync från laptopens befintliga 40 plus åtta nya

Prompt 1 i `docs/research/2026-08-14-grok-insamling-prompter.md`: minst fyra mallfamiljer, minst 25 föreningar, måltal 40 rapporter. Korpusen som redan låg på laptopen täckte målet. Den här svepen fyllde de tunna familjerna och tog in tre unika av de fyra Riksbyggen-seedarna.

Inga PDF:er i git. Manifest med sha256 ligger bredvid filerna. Här bara räknade.

## Efter svepen

| mallfamilj | rapporter |
| --- | ---: |
| HSB | 8 |
| Riksbyggen | 10 |
| Simpleko | 6 |
| Fastum | 6 |
| SBC | 5 |
| Nabo | 5 |
| egen/okänd | 8 |
| **summa** | **48** |

Alla 48 har digitalt textlager. Sidspann 12–36. Minst fyra av de namngivna familjerna (HSB, Riksbyggen, SBC, Simpleko, Fastum) plus Nabo och egna mallar. Före svepen var Fastum 1 och Simpleko 2 på förstasidesklassning; fulltextklassning av de 40 visade att flera redan bar familjenämnet längre in i filen. De nya filerna är ändå tillagda så att Fastum och Simpleko inte vilar på enstaka exemplar.

## Hämtning den här körningen

Öppnade och sparade som PDF:

| källa | försök | PDF | dubblett mot de 40 | ny |
| --- | ---: | ---: | ---: | ---: |
| fyra Riksbyggen-seedar | 4 | 4 | 1 | 3 |
| Simpleko (bostadsratterna.se) | 3 | 3 | 1 | 2 |
| SBC | 2 | 2 | 0 | 2 |
| Fastum | 2 | 2 | 1 | 1 |
| **summa** | **11** | **11** | **3** | **8** |

Noll påhittade URL:er i den här listan: varje rad gav `%PDF`. En seed (Sollentunahus 2) var redan `010.pdf`. Korporalen 9 var redan `027.pdf`. Skidtränaren 1 var redan `021.pdf`.

Inte infört: Fastum AB:s egen koncernrapport (inte en BRF), en samfällighetsrapport med Fastum-mall, en föreningssida där HTML:en inte exponerade en direkt PDF-länk. De räknas som avbrutna spår, inte som poster i de 48.

De 48 är en seed-korpus för senare ingestionsmätning, inte BRF-1-arkivet. BRF-1 mättes mot Ekens handlingar (`docs/evidence/brf1-eken-egen.md`).
