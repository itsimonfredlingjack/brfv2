# BRF Dokument-AI

Grundad dokument-Q&A för bostadsrättsföreningar. Varje godkänd källa kan öppnas
på rätt PDF-sida med den citerade passagen markerad. Frågor som saknar stöd i
föreningens dokument ska avvisas i stället för att gissas.

- [Aktuell MVP-status](docs/MVP-STATUS.md)
- [Demo quickstart](docs/DEMO-QUICKSTART.md)
- [Operatörsrunbook](docs/DEMO-RUNBOOK.md)
- [Pilotdrift med Gemma 4 12B](docs/DEPLOY-SELFHOSTED-LLM.md)

## Två repon, en produkt

Arbetsområdet består av två separata Git-repon:

- detta repo äger FastAPI-backend, auth, tenant-isolering, ingestion, retrieval,
  generering, citatverifiering, driftverktyg och evidens;
- `brfv2-mockup/` är den **kanoniska produktfrontenden**. Namnet är historiskt;
  dess verifierade pilotslinga använder backendens verkliga HTTP-kontrakt.

Rotens React-app i `src/` är en äldre backendkopplad prototyp. Den är inte den
avsedda pilotfrontenden och ska inte få nya produktintegrationer. Rotens
frontendtester och bygge behålls som regressionsskydd tills prototypen kan
arkiveras separat.

## MVP-gräns

Den verifierade produktslingan är:

> Logga in → välj aktiv förening → se föreningens dokument → ställ en fråga →
> få ett grundat svar → öppna exakt källa och sida med markering.

Administratörer kan också ladda upp och radera PDF-dokument. Medlemmar kan
inte göra det. Global sök, dokumentbunden chatt, kvalitetskontroll,
bevakningar och allmän styrelseadministration ingår inte i MVP:n och är dolda
eller spärrade i pilotvyn.

## Lokal verifiering

Den deterministiska browser-acceptansen startar isolerade, verkliga backend-
och frontendprocesser och använder backendens scriptade LLM endast för
repeterbar generation. Auth, tenantval, lagring, upload, ingestion, retrieval,
svars- och citatformning, PDF-endpoint och markering är verkliga:

```bash
cd /Users/coffeedev/Projects/brfv2/brfv2-mockup
npm run test:e2e
```

Övriga lokala kontroller:

```bash
cd /Users/coffeedev/Projects/brfv2
make test
make test-isolation
make eval-fast

cd brfv2-mockup
npm test
npm run lint
npm run build
```

Senast sammanhållna verifiering: backend **526 passed, 1 skipped**,
isolerings/auth/livscykel **48 passed**, kanonisk frontend **14 passed**,
Playwright **11 passed**, lint och produktionsbygge gröna. Exakta körningar och
bevisgränser finns i [MVP-statusen](docs/MVP-STATUS.md).

## Pilot med Gemma 4 12B

Pilotgeneration körs med `gemma4:e12b` på den självhostade Ubuntu-tjänsten.
Macens lokala `gemma4:e4b` är inte en fallback. Från Mac används normalt en
SSH-tunnel, varefter hela pilotstacken startas så här:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver

cd /Users/coffeedev/Projects/brfv2
make demo
```

`make demo` verifierar att den tunnlade tjänsten annonserar Gemma 4 12B och
startar backend med `BRF_MODE=pilot`, `BRF_LLM=selfhosted` och kanonisk
frontend. Det finns ingen tyst fallback.

Den senaste livekörningen bevisade rätt runtimeidentitet, noll externa
nätverksanslutningar, en komplett browserresa och grönt syntetiskt golden set.
Efter en instrumenterad q03-diagnos länkar backenden nu en kodad tabellrad
deterministiskt till dess ansvarsförklaring i samma dokument. Den oförändrade
realkorpusgaten avslutades därefter med exitkod 0 och **`VERDICT: READY`**:
q03 fick två verifierade citat och q11 fortsatte att vägras säkert.

Se den icke-känsliga rapporten
[docs/evidence/pilot-live-gemma4-12b-2026-07-22.md](docs/evidence/pilot-live-gemma4-12b-2026-07-22.md).
Fix och omkörning:
[docs/evidence/xs32-q03-linked-context-2026-07-22.md](docs/evidence/xs32-q03-linked-context-2026-07-22.md).

## Arkitektur

```text
PDF → extract.py → chunker.py → indexer.py
    → answer.py → citations.py → FastAPI → brfv2-mockup
```

- [Specifikation](SPEC.md)
- [Pilotkontrakt](SPEC-PILOT.md)
- [Evidens](docs/evidence/)
