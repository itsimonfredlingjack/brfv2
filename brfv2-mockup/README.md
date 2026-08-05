# brfv2-mockup — kanonisk produktfrontend

Det historiska namnet beskriver ursprunget, inte dagens roll. Detta är den
avsedda produktfrontenden för BRF Dokument-AI. FastAPI-backend, driftverktyg
och evidens ligger i samma repo, en nivå upp.

Katalogen var tidigare ett eget, gitignorerat Git-repo. Den är nu vanliga
spårade filer i huvudrepot, så en ren klon innehåller hela produkten. Den gamla
historiken finns kvar på `migration/brfv2-mockup/*`-grenarna.

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

Kör `make setup` i repo-roten en gång först — den installerar `node_modules`
här med rätt plattformsbinärer. En `node_modules` kopierad från ett annat OS
går sönder vid bygge, inte vid installation.

Starta backend från repo-roten:

```bash
make demo-reset   # endast första gången eller vid avsiktlig återställning
make backend
```

Starta därefter frontenden:

```bash
cd brfv2-mockup
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
den självhostade tjänsten `agenntserver`, normalt via SSH-forward från
utvecklingsmaskinen:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver

make demo
```

Headern ska då visa `Gemma 4 12B` och `Self-hosted · agenntserver` från
backendens `/api/health`. Svar visar provider/modell från just `/ask`-svaret;
inga hårdkodade frontendetiketter får överstyra detta.

Den senaste oförändrade skyddade realkorpusgaten gav `VERDICT: READY`: den
tidigare blockerande fragmentfrågan fick två verifierade citat och den
obesvarbara kontrollen vägrades fortfarande säkert. Frontenden ändrades inte
för fixen; den fortsätter att rendera backendens verkliga svar och citat.

Se `docs/MVP-STATUS.md` och
`docs/evidence/pilot-live-gemma4-12b-2026-07-22.md`.
XS-32-fixens evidens finns i
`docs/evidence/xs32-q03-linked-context-2026-07-22.md`.
