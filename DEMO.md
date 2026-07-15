# Demo — BRF Dokument-AI (körbar utan Simon i rummet)

Grundad dokument-Q&A för BRF-styrelser: varje svar citerar ordagranna passager som
verifieras mot källtexten och markeras på exakt rätt plats i PDF:en. Kan systemet inte
svara utifrån dokumenten, säger det det — i stället för att gissa.

## Förutsättningar (redan uppfyllda på denna maskin)

- `uv` (Python-miljön sköts automatiskt), Node 22+
- LLM: `claude` CLI inloggad **eller** `ANTHROPIC_API_KEY` satt
- Första starten laddar ner embeddingmodellen (~1 min, cachas)

## Starta (två terminaler)

```bash
make backend     # terminal 1 — API på :8787
make frontend    # terminal 2 — UI på  http://localhost:5173/brfv2/
```

## Nollställ till demoskick

```bash
make demo-reset  # rensar och seedar om de fem syntetiska BRF-dokumenten
```

Korpusen är **fiktiv** (Brf Gjutformen 12): stadgar, årsredovisning 2025,
styrelseprotokoll, snöröjningsavtal och underhållsplan. Inga kunddokument ingår.

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
make test        # 110 enhets-/API-tester (offline, deterministiska)
make eval        # full eval med riktig LLM: recall, citatverifiering,
                 # markeringsprecision, falska-svar-frekvens — med kravgränser
make eval-fast   # samma utan LLM (retrieval-delen, ~sekunder)
```

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

## Felsökning

- **"Ingen LLM-leverantör"** i `/api/health` → logga in i `claude` CLI eller sätt `ANTHROPIC_API_KEY`.
- **Svar dröjer ~10 s** → normalt med CLI-leverantören; API-nyckel är snabbare.
- **Port upptagen** → `lsof -ti :8787 | xargs kill`.
