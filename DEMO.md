# Demo — BRF Dokument-AI (körbar utan Simon i rummet)

Grundad dokument-Q&A för BRF-styrelser: varje svar citerar ordagranna passager som
verifieras mot källtexten och markeras på exakt rätt plats i PDF:en. Kan systemet inte
svara utifrån dokumenten, säger det det — i stället för att gissa.

## Förutsättningar (redan uppfyllda på denna maskin)

- `uv` (Python-miljön sköts automatiskt), Node 22+
- LLM: självhostad Gemma 4 via Ollama (`gemma4:e4b`) för pilotläge — se
  `docs/DEPLOY-SELFHOSTED-LLM.md`. I dev-läge duger även `claude` CLI / `ANTHROPIC_API_KEY`.
- Första starten laddar ner embeddingmodellen (~1 min, cachas)

## Starta (två terminaler)

```bash
make demo-reset      # seedar TVÅ föreningar + demokonton (skriver ut inloggningar)
make backend-pilot   # terminal 1 — API på :8787, kräver självhostad LLM
# (eller `make backend` för dev-läge med valfri LLM)
make frontend        # terminal 2 — UI på  http://localhost:5173/brfv2/
```

Logga in i UI:t med ett demokonto (skrivs ut av `make demo-reset`), t.ex.
**anna@gjutformen12.se / gjutformen-demo-2026** (admin i Gjutformen 12).
Konton med flera föreningar (max@demo.se) får en föreningsväljare i huvudet.

## Nollställ till demoskick

```bash
make demo-reset  # rensar och seedar om båda föreningarna + golden-set + konton
```

Korpusarna är **fiktiva**: **Brf Gjutformen 12** (stadgar, årsredovisning 2025,
styrelseprotokoll, snöröjningsavtal, underhållsplan) och **Brf Sjöutsikten 7**
(stadgar, årsredovisning, protokoll, städ-/trädgårdsavtal). Helt åtskild data —
används för att bevisa tenant-isolering. Inga kunddokument ingår.

## Två föreningar, hård isolering

Logga in som **anna@gjutformen12.se** och ställ frågor — du ser bara Gjutformen 12.
Ingen väg (fråga, källa, URL, dokument-id) når Sjöutsikten 7:s data. Bevis:
`make test-isolation` kör 18 angreppstester + livscykel + auth. En dedikerad
red-team-körning (`docs/evidence/isolation-redteam.md`) försökte aktivt bryta
gränsen och misslyckades.

## Skript för demon (5 minuter)

1. **Översikt** — visa statistiken (5 dokument, 13 sidor indexerade).
2. **Grundat svar.** Klicka förslagsknappen *"När startar snöröjningsjouren?"*
   → svar med källchip. **Klicka chippet** → PDF:en öppnas med passagen
   *"Jourperioden löper från den 15 november till den 15 april."* markerad.
3. **Vägran i två steg.** Fråga: *"Vad kostar en parkeringsplats i garaget per månad?"*
   → systemet avstår och förklarar vad som saknas (LLM-grinden).
   Fråga: *"Hur fungerar kvantdatorer?"* → avstår direkt utan LLM-anrop (relevansgrinden).
4. **Ladda upp något nytt.** *Ladda upp dokument* → valfri digital PDF (t.ex. en
   trivselregel-PDF). Fråga något ur den → svar med markering i det nya dokumentet.
   (Skannade PDF:er avvisas med tydligt besked — OCR är nästa fas, se riggen nedan.)
5. **Visa att inställningarna är på riktigt** (för tekniska åhörare):
   `make eval-sweep` visar hur recall förändras när sökvikt/topK/chunkstorlek ändras.

## Frågor som fungerar bra

| Fråga | Träffar |
|---|---|
| Vad krävs för att hyra ut i andra hand? | Stadgar §6 |
| Hur stor överlåtelseavgift får tas ut? | Stadgar §5 |
| Vad kostade reliningen? | Årsredovisning |
| Vem utför fasadmålningen och vad kostar den? | Protokoll §2 |
| Vad kostar stambytet enligt planen? | Underhållsplan |
| Vilket företag sköter den ekonomiska förvaltningen? | Årsredovisning (avstavat ord!) |

## Mätning & kvalitet

```bash
make test            # backend-tester (offline, deterministiska) — inkl. isolering
make eval            # full eval, förening A, självhostad Gemma + nätverksrevision
make eval-b          # full eval, förening B (Sjöutsikten 7)
make eval-fast       # retrieval-delen utan LLM (~sekunder)
make test-isolation  # isolering + livscykel + auth
```

`make eval` kör med `--network-audit`: varje TCP-anslutning loggas och allt
utanför loopback + den självhostade LLM:en får körningen att faila. Ren körning =
bevis på att dokumenttext bara nådde den egna LLM-servern.

## OCR-spikriggen (för skannade dokument)

De flesta riktiga BRF-PDF:er är skannade. Riggen mäter — den beslutar inte:

```bash
cd backend
uv run python -m scripts.ocr_spike "<skannad>.pdf"              # overlays + metrics
uv run python -m scripts.ocr_spike "<digital>.pdf" --calibrate  # drift mot facit
```

Utdata: `out/ocr_spike/<namn>/page-N-overlay.png` (ordrutor ritade på sidan) +
`metrics.json` (koordinatdrift, quote-match-frekvens). Kalibrering på digital PDF på
denna maskin: 96 % ordmatchning, 0,099 % genomsnittlig drift (kravet i researchen: < 5 %).

## Provisionera en ny förening / styrelseledamot (ingen självregistrering)

```bash
cd backend
uv run python -m scripts.tenant create-tenant --name "Brf Exempel 1"
uv run python -m scripts.tenant add-user --email ny@exempel.se --password '<minst 8 tecken>'
uv run python -m scripts.tenant add-membership --email ny@exempel.se --brf-id <brf_id> --role admin
uv run python -m scripts.tenant delete-tenant --brf-id <brf_id> --yes   # hård radering
```

## Felsökning

- **`BRF_MODE=pilot kräver självhostad LLM`** vid start → starta Ollama och sätt
  `BRF_LLM_BASE_URL` (se `docs/DEPLOY-SELFHOSTED-LLM.md`), eller kör `make backend` (dev).
- **`/api/reset` ger 403** → den finns bara i dev-läge; använd `make demo-reset` från CLI.
- **Inloggning krävs (401)** → logga in med ett demokonto; sessionen ligger i en cookie.
- **Port upptagen** → `lsof -ti :8787 | xargs kill`.
