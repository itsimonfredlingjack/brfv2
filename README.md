# BRF Dokument-AI

Grundad dokument-Q&A för bostadsrättsföreningar. Varje godkänd källa kan öppnas
på rätt PDF-sida med den citerade passagen markerad. Frågor som saknar stöd i
föreningens dokument ska avvisas i stället för att gissas.

- [Aktuell MVP-status](docs/MVP-STATUS.md)
- [Demo quickstart](docs/DEMO-QUICKSTART.md)
- [Operatörsrunbook](docs/DEMO-RUNBOOK.md)
- [Pilotdrift med Gemma 4 12B](docs/DEPLOY-SELFHOSTED-LLM.md)

## Ett repo, en produkt

Allt som behövs för att köra produkten ligger i det här repot. En ren klon är
komplett — ingen nästlad utcheckning, ingen submodul, inget att hämta separat.

- roten äger FastAPI-backend, auth, tenant-isolering, ingestion, retrieval,
  generering, citatverifiering, driftverktyg och evidens;
- `brfv2-mockup/` är den **kanoniska produktfrontenden**. Namnet är historiskt;
  dess verifierade pilotslinga använder backendens verkliga HTTP-kontrakt.

Fram till juli 2026 var `brfv2-mockup/` ett separat, gitignorerat repo, vilket
gjorde att en ren klon inte gick att köra. Den historiken finns kvar på
`migration/brfv2-mockup/*`-grenarna; katalogen är nu vanliga spårade filer.

Rotens React-app i `src/` är en äldre backendkopplad prototyp. Den är inte den
avsedda pilotfrontenden och ska inte få nya produktintegrationer. Rotens
frontendtester och bygge behålls som regressionsskydd tills prototypen kan
arkiveras separat.

## Uppsättning

Alla kommandon körs från repo-roten om inget annat anges.

```bash
make setup
```

Det är hela uppsättningen. Den installerar `uv` i `~/.local/bin` om det saknas,
skapar backend-venv:en, hämtar embedder-vikterna, installerar `node_modules`
för båda frontenderna och laddar ner Playwrights chromium. Inget sudo, inga
systempaket, körbar hur många gånger som helst.

Två plattformsdetaljer värda att känna till:

- **Python.** Backenden kräver 3.12. Distributionens egen tolk duger sällan
  (Fedora 44 ligger på 3.14), så `uv` hämtar en egen — därför är `uv` ett krav
  och inte en smaksak.
- **Playwright.** `npx playwright install-deps` fungerar bara på apt-baserade
  distributioner och kraschar på Fedora med `spawn apt-get ENOENT`. Själva
  browsernedladdningen är portabel och Ubuntu-fallbackbygget kör felfritt på
  Fedora 44. Använd distributionens paket om ett systembibliotek saknas.

Omrankning är avstängd som standard och kräver inget av detta. Den valfria
`rerank`-extran drar in torch och ~3,8 GB CUDA-hjul — installera den bara om du
faktiskt utvärderar omrankning:

```bash
cd backend && uv sync --extra rerank
```

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
cd brfv2-mockup
npm run test:e2e
```

Övriga lokala kontroller:

```bash
make test
make test-isolation
make eval-fast

cd brfv2-mockup
npm test
npm run lint
npm run build
```

Senast sammanhållna verifiering, på Fedora 44 från ren checkout: backend
**528 passed, 5 skipped**, isolerings/auth/livscykel **48 passed**, kanonisk
frontend **14 passed**, Playwright **11 passed**, lint och produktionsbygge
gröna. Exakta körningar och bevisgränser finns i
[MVP-statusen](docs/MVP-STATUS.md).

## Pilot med Gemma 4 12B

Pilotgeneration körs med `gemma4:e12b` på den självhostade Ubuntu-tjänsten
`agenntserver` (RTX 4070). Ingen mindre lokal modell är fallback. Tjänsten är
en llama.cpp-container som lyssnar på `127.0.0.1:8000`; utvecklingsmaskinen når
den genom en SSH-tunnel:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver

make demo
```

`make demo` verifierar att den tunnlade tjänsten annonserar Gemma 4 12B och
startar backend med `BRF_MODE=pilot`, `BRF_LLM=selfhosted` och kanonisk
frontend. Det finns ingen tyst fallback.

Runtimen är ett **externt beroende** som inte kan reproduceras på
utvecklingsmaskinen: den kräver att containern `llama-server` kör på
`agenntserver` med fungerande NVIDIA-drivrutin. Startas med
`docker compose up -d` i `/home/simon/llama-cpp` på den värden. Om en
drivrutinsuppgradering har gjort kernelmodulen och userspace osynkroniserade
måste CDI-specen genereras om (`nvidia-ctk cdi generate
--output=/var/run/cdi/nvidia.yaml`) innan containern kan starta.

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
