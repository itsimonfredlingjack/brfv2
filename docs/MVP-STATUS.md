# MVP-status — BRF Dokument-AI

**Senast verifierad:** 2026-07-20  
**Kanoniskt repo:** `/Users/coffeedev/Projects/brfv2`  
**Aktiv integrationsbranch:** `feat/mvp-visual-integration`

## Beslut: en produkt, ett frontend

Huvudrepots React-app i `src/` är den kanoniska produkten. Den är redan kopplad till FastAPI-backendens riktiga auth-, dokument-, fråge-, käll- och PDF-endpoints.

Det fristående lokala repot `brfv2-mockup/` är endast en visuell referens. Det innehåller fiktiva dokument, statusar, svar och arbetsflöden och ska inte kopplas in som en parallell produkt. Visuella mönster får porteras därifrån, men data och handlingar måste komma från huvudappens riktiga API.

## MVP-kontrakt

MVP är denna obrutna, verkliga kedja:

> Logga in → se föreningens riktiga dokument → ställ en fråga → få ett grundat svar med verifierad källa → öppna källan på rätt sida med markering.

En administratör ska dessutom kunna ladda upp en digital PDF, få den indexerad och därefter fråga om innehållet.

MVP kräver inte Granskning, Bevakningar, automatisk datumextraktion, OCR-produktionsstöd, GraphRAG eller perfekt årsredovisningsretrieval.

## Var vi är nu

### Färdigt och verifierat

- FastAPI-backend med hård tenant-isolering, auth och admin/member-roller.
- Verklig dokumentlista, PDF-upload, hård dokumentradering och beständig lagring.
- Hybrid retrieval, vägranströsklar, grundad generering och verifierade citat.
- Klickbara källor som öppnar PDF på rätt sida med bounding-box-markering.
- Verklig Home/Sök-yta, global AI-chatt och källpanel i huvudfrontenden.
- Dev-only demo-ytor är spärrade från produktionsbygget.
- Backend: **415 passed, 4 skipped**.
- Frontend: **68 passed**.
- Lint: **0 errors**, fyra sedan tidigare kända varningar i dev-only demo-komponenter.
- Produktionsbygge: grönt.
- Pilotläge verifierat mot lokal, självhostad `gemma4:e4b`: `/api/health` rapporterade `mode: pilot` och `llm_provider: selfhosted`.
- Grundat pilotsvar verifierat via API: korrekt svar om snöröjningsjouren, verifierat citat på sida 1 och exakt bounding-box.
- Säker relevansvägran verifierad via API för frågan `Hur fungerar kvantdatorer?`.

### Genomfört på denna branch

Dokumentvyn har konsoliderats till den visuella riktningen från mockupen men använder enbart riktig tenant-scopad API-data:

- verkliga dokumentnamn, datum, sidantal och chunks;
- riktig öppna-, ladda upp- och raderafunktion;
- fungerande sökning på dokumentnamn;
- riktiga tomlägen för admin/member;
- responsiv kortvy;
- döda filter-, sorterings- och vyknappar har tagits bort i stället för att låtsas fungera.
- appskalet hämtar backendens health-status och varnar innan användaren ställer en fråga om generationen är felkonfigurerad.

### Faktisk blockerare

Den gamla utvecklingsprocessen på port 8787 rapporterade `llm_provider: fake` och kunde därför inte generera svar. Det var en start-/konfigurationsfråga, inte ett retrieval- eller frontendfel.

Den riktiga pilotvägen är nu separat verifierad på en testport med `BRF_MODE=pilot`, lokal Ollama och `gemma4:e4b`. Den gav ett korrekt grundat svar, en verifierad källa på sida 1 och en korrekt säker vägran. Generationstekniken är alltså inte längre en okänd blockerare.

Det som återstår är den synliga E2E-gaten: starta den kanoniska backendprocessen i pilotläge, köra huvudfrontenden mot den, ställa frågan i UI:t och klicka igenom källan till PDF-markeringen. En server som rapporterar `fake` eller `none` är fortfarande inte MVP-redo.

## Vägen till MVP

### A. Visuell konsolidering — pågår

- [x] Dokumentbiblioteket portat till verklig API-data.
- [ ] Harmoniera Hem/Sök och AI-chatten med samma visuella system utan att ändra deras datakontrakt.
- [x] Visa ett tydligt blockerande driftmeddelande när backend kör med `fake`, `none` eller fel provider i pilotläge.

### B. End-to-end generation — nästa hårda gate

- [x] Starta backend i pilotläge med självhostad provider.
- [x] Verifiera frågan `När startar snöröjningsjouren?` genom det riktiga API-kontraktet.
- [ ] Verifiera samma fråga genom huvudfrontenden.
- [ ] Klicka källan och bekräfta rätt PDF-sida och markering.
- [x] Verifiera en säker vägran för en fråga som saknar underlag.

### C. Upload-slingan

- [ ] Ladda upp en digital test-PDF via UI:t.
- [ ] Bekräfta att dokumentet syns i det visuella biblioteket.
- [ ] Ställ en fråga om den nya PDF:en och öppna det verifierade citatet.

### D. MVP-smoke och leverans

- [ ] Lägg ett Playwright-smoke-test för login → fråga → källa → PDF.
- [ ] Lägg ett smoke-test för upload → dokumentlista → fråga.
- [ ] Kör backend, frontend, lint och build grönt i samma verifiering.
- [ ] Dokumentera en enda startmetod för demo respektive pilot.

## Utanför MVP

Följande ska inte dra fokus innan den obrutna kedjan ovan fungerar med riktig generation:

- Granskning/QA och Bevakningar;
- nya rerankerexperiment eller ytterligare årsredovisningsresearch;
- automatiska arbetsflöden och notifieringar;
- OCR som produktionspipeline;
- fler inställningsrattar;
- redesign av PDF-visaren;
- skalning bortom en liten pilot.

## Styrprincip

Ingen visuell komponent får visa dokumentdata, svar, citat, sidnummer, statusar eller analys som inte kommer från backendens verkliga kontrakt. När backend saknar ett fält ska frontenden visa mindre — inte hitta på det.
