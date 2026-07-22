# brfv2-mockup — kanonisk produktfrontend

Det historiska reponamnet beskriver ursprunget, inte dagens roll. Detta är den
avsedda produktfrontenden för BRF Dokument-AI. FastAPI-backend, driftverktyg
och evidens finns i det överordnade repot:

`/Users/coffeedev/Projects/brfv2`

Rotrepots `src/` är en äldre backendkopplad prototyp och ska inte ta emot nya
produktintegrationer.

## Verifierad MVP

Pilotvyn använder verkliga backendkontrakt för:

- cookie-/sessionbaserad login och medlemskap;
- aktiv förening och tenant-scopad dokumentlista;
- adminupload/radering och medlemsspärrar;
- PDF-rendering;
- global fråga via `/ask`, grounding och svarprovenance;
- resolverbara citat till rätt dokument/sida och highlight-overlay;
- rensning av dokument, väntande svar och citat vid föreningsbyte;
- model/provider-readiness från `/api/health`.

Global sök, dokumentbunden chatt, kvalitetskontroll, bevakningar och
inställningar ingår inte i MVP. De är dolda eller spärrade i pilotvyn och får
inte presentera fiktiva data som backendresultat.

## Lokal utveckling

Starta backend från överordnat repo:

```bash
cd /Users/coffeedev/Projects/brfv2
make demo-reset   # endast första gången eller vid avsiktlig återställning
make backend
```

Starta därefter frontenden:

```bash
cd /Users/coffeedev/Projects/brfv2/brfv2-mockup
npm run dev
```

Vite proxar `/api` till `http://127.0.0.1:8787`. En devbackend kan använda en
annan provider än piloten; frontend visar då backendens verkliga readinessläge.

## Deterministisk acceptans

```bash
npm test
npm run lint
npm run build
npm run test:e2e
```

Playwright startar isolerade verkliga backend- och frontendprocesser. Den
scriptade testprovidern gör endast generationen repeterbar; inga frontend-API-
anrop mockas. De 11 browserfallen verifierar login, tenantdata, upload och
ingestion, fråga, grounding, citat, PDF/highlight, vägran, roller,
föreningsbyte och readinesslägena ready/fake/none/unavailable.

## Livepilot

Frontend pratar bara med FastAPI. Pilotens modell ska vara `gemma4:e12b` på
den självhostade tjänsten, normalt via SSH-forward från Macen:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver

cd /Users/coffeedev/Projects/brfv2
make demo
```

Headern ska då visa `Gemma 4 12B` och `Self-hosted · agenntserver` från
backendens `/api/health`. Svar visar provider/modell från just `/ask`-svaret;
inga hårdkodade frontendetiketter får överstyra detta.

Den senaste skyddade realkorpusgaten är `NOT READY` på en obligatorisk
fragmentfråga. En fungerande livebrowserresa är dokumenterad, men frontenden
eller demon får inte beskriva hela livepiloten som godkänd innan backendens
readinesskommando ger `VERDICT: READY`.

Se `/Users/coffeedev/Projects/brfv2/docs/MVP-STATUS.md` och
`/Users/coffeedev/Projects/brfv2/docs/evidence/pilot-live-gemma4-12b-2026-07-22.md`.
