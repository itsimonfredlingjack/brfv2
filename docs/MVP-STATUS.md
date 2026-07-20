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
- Frontend: **63 passed**.
- Lint: **0 errors**, fyra sedan tidigare kända varningar i dev-only demo-komponenter.
- Produktionsbygge: grönt.

### Genomfört på denna branch

Dokumentvyn har konsoliderats till den visuella riktningen från mockupen men använder enbart riktig tenant-scopad API-data:

- verkliga dokumentnamn, datum, sidantal och chunks;
- riktig öppna-, ladda upp- och raderafunktion;
- fungerande sökning på dokumentnamn;
- riktiga tomlägen för admin/member;
- responsiv kortvy;
- döda filter-, sorterings- och vyknappar har tagits bort i stället för att låtsas fungera.

### Faktisk blockerare

Den server som körde vid verifieringen rapporterade `llm_provider: fake`. Retrieval fungerade och hittade korrekt avsnitt, men `/ask` slutade med `provider_error` eftersom `FakeLLM` inte har några svar.

Detta är inte ett retrievalfel och inte ett frontendfel. MVP-blockeraren är att starta backend med en riktig generation-provider:

- utveckling/demo: lokalt autentiserad Claude CLI eller uttryckligen konfigurerad provider;
- pilot med verkliga dokument: `BRF_MODE=pilot` och självhostad OpenAI-kompatibel LLM-endpoint.

En server som rapporterar `fake` eller `none` är inte MVP-redo.

## Vägen till MVP

### A. Visuell konsolidering — pågår

- [x] Dokumentbiblioteket portat till verklig API-data.
- [ ] Harmoniera Hem/Sök och AI-chatten med samma visuella system utan att ändra deras datakontrakt.
- [ ] Lägg in tydliga loading-, provider- och felstatusar i appskalet.

### B. End-to-end generation — nästa hårda gate

- [ ] Starta backend med en verklig provider.
- [ ] Verifiera frågan `När startar snöröjningsjouren?` genom UI:t.
- [ ] Klicka källan och bekräfta rätt PDF-sida och markering.
- [ ] Verifiera en säker vägran för en fråga som saknar underlag.

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
