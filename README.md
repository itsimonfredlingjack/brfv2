# BRF Dokument-AI

Grundad dokument-Q&A för bostadsrättsföreningar. Varje godkänd källa kan öppnas
på rätt PDF-sida med den citerade passagen markerad. Frågor som saknar stöd i
föreningens dokument ska avvisas i stället för att gissas.

- [Aktuell MVP-status](docs/MVP-STATUS.md)
- [Skrivbordsapplikationen för Fedora](docs/DESKTOP-FEDORA.md)
- [Integrationsdomänen: mejlintag och fakturagranskning](docs/INTEGRATIONSDOMAN.md)
- [Post-BP6-produktbasen och porteringen](docs/POST-BP6-PRODUKTBAS.md)
- [Demo quickstart](docs/DEMO-QUICKSTART.md)
- [Operatörsrunbook](docs/DEMO-RUNBOOK.md)
- [Pilotdrift med Gemma 4 12B](docs/DEPLOY-SELFHOSTED-LLM.md)
- [Drift- och förvaltningsplan](docs/DRIFT-FORVALTNINGSPLAN.md)
- [Erfarenhetsåterföring](docs/ERFARENHETSATERFORING.md)
- [Slutrapport](docs/SLUTRAPPORT.md)
- [Integrationsdomänen](docs/INTEGRATIONSDOMAN.md) — inkommande underlag och
  read-only fakturagranskning
- [Ansluta en brevlåda](docs/INTEGRATION-OUTLOOK.md) ·
  [Ansluta Fortnox](docs/INTEGRATION-FORTNOX.md)
- [Källstyrda bevakningar och årshjul](docs/BEVAKNINGAR.md)
- [Uppgifter och ansvar](docs/UPPGIFTER.md)
- [Hemsidan](docs/HEMSIDA.md) — föreningens egen webbplats, byggd i produkten

## Ett repo, en produkt

Allt som behövs för att köra produkten ligger i det här repot. En ren klon är
komplett — ingen nästlad utcheckning, ingen submodul, inget att hämta separat.

- roten äger FastAPI-backend, auth, tenant-isolering, ingestion, retrieval,
  generering, citatverifiering, driftverktyg och evidens;
- `brfv2-mockup/` är den **kanoniska produktfrontenden**. Namnet är historiskt;
  dess verifierade pilotslinga använder backendens verkliga HTTP-kontrakt.
- `xs_mobilapp/` är **mobilklienten Källa** — samma backend, samma auth, samma
  citatverifiering, men bara den slingan som är värd att ha i fickan: fråga →
  grundat svar → källa med markerad passage. Se
  [xs_mobilapp/README.md](xs_mobilapp/README.md).
- `kalla-native/` är **Träff, den nativa Android-appen** (Expo Router + React
  Native) över samma backendkontrakt som PWA:n. Byggd under namnet Källa,
  släppt som Träff — se [kalla-native/README.md](kalla-native/README.md).
- `src-tauri/` är skrivbordsskalet som paketerar frontend + backend till en
  installerbar Fedora-RPM. Det äger fönstret och sidecar-livscykeln, ingen
  produktlogik.

De tre klienterna är **inte** i paritet, och gapen är avsiktliga — en telefon är
inte där en förening granskar sin post eller sina fakturor:

| | webb/desktop | PWA | Android |
| -- | -- | -- | -- |
| Fråga → grundat svar → citat | ✅ | ✅ | ✅ |
| Dokument | ✅ | ✅ | ✅ |
| Granskning · Bevakningar · Uppgifter | ✅ | ✅ | — |
| Inkommande post · Fakturor · Anslutningar | ✅ | — | — |
| Hemsidan (webbplatsbyggaren) | ✅ | — | — |

Backendkontraktet delas oavsett: en ruttändring prövas mot alla tre, inte bara
mot den klient som råkar ha skärmen.

Fram till juli 2026 var `brfv2-mockup/` ett separat, gitignorerat repo, vilket
gjorde att en ren klon inte gick att köra. Den historiken finns kvar på
`migration/brfv2-mockup/*`-grenarna; katalogen är nu vanliga spårade filer.

Rotens React-app i `src/` är en äldre backendkopplad prototyp. Den är inte den
avsedda pilotfrontenden och ska inte få nya produktintegrationer. Rotens
frontendtester och bygge behålls som regressionsskydd tills prototypen kan
arkiveras separat.

## Grenar — läs det här om en fil verkar saknas

Produktlinjerna har inte alltid slagits ihop i takt med att de utvecklats, så
**vilken gren utcheckningen står på avgör vilka funktioner som finns.** Det är
nästan alltid förklaringen när en katalog som dokumentationen beskriver inte
går att hitta.

| Gren | Roll |
| -- | -- |
| `feat/produktbas` | **Här pågår arbetet.** Ligger före `main` med fakturaärendena som ärenden, samtidighets- och tillståndsreparationen, och acceptansresorna genom den riktiga desktopappen. |
| `main` | Produktbas: backend, kanonisk frontend, mobil-PWA, Android-app, Tauri-skal, Fortnox, Microsoft Graph, Bevakningar, Uppgifter. |
| `bp6/fedora-pilot-closeout` (taggen `v0.2.0-fedora-pilot`) | Frusen pilotevidens. Ingen fortsatt utveckling sker på den linjen. |

Konkret: `backend/app/invoices/`, `backend/app/history.py`,
`backend/tests/test_concurrency_integrity.py` och
`backend/scripts/intake_acceptance.py` finns **bara** på `feat/produktbas`. En
utcheckning utan dem står på `main` — det är inte en trasig klon.

Grenen hette `feat/kalla-mobile-pwa` fram till 2026-08-03. Namnet var sant den
vecka mobilklienten byggdes på den och missvisande därefter, eftersom den sedan
bar fakturor, samtidighet och desktopacceptans. Hela resonemanget om varför
linjerna divergerade och hur de fördes ihop:
[docs/POST-BP6-PRODUKTBAS.md](docs/POST-BP6-PRODUKTBAS.md).

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

Desktopinstallationen har utöver det en **granskningsslinga för inkommande
underlag**: ett mejl kommer in — manuellt som `.eml` eller ur en ansluten
brevlåda — bilagorna blir vanliga dokument, en leverantörsfaktura läses
read-only ur fixturunderlag eller ur ett anslutet ekonomisystem, och
jämförelsen mot föreningens egna avtal läggs fram som ett *fynd* med exakta
citat, uttalad osäkerhet och tre möjliga domar. En människa avgör; produkten
skriver aldrig tillbaka någonstans. Se
[docs/INTEGRATIONSDOMAN.md](docs/INTEGRATIONSDOMAN.md).

Samma dokumentläsning driver **bevakningarna**: uppsägningstider, avtalsslut,
garantier och besiktningar blir daterade åtaganden med citatet de räknades fram
ur, sorterade i ett årshjul — försenat, snart, senare, återkommande. En tidsfrist
som inte går att datera blir aldrig en kalenderpost på en gissning, utan säger
vad som saknas. Se [docs/BEVAKNINGAR.md](docs/BEVAKNINGAR.md).

Sist i kedjan står **uppgifterna**: ett fynd, en bevakning eller ett inkommande
mejl blir arbete med ansvarig, datum, status och en historik som bara växer —
med ursprungets citat i behåll, så att passagen bakom arbetet öppnas även ett
halvår senare. Det är den enda domänen motorn inte kan skapa något i: att skapa
en uppgift *är* beslutet. Se [docs/UPPGIFTER.md](docs/UPPGIFTER.md).

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

Mobilklienten har sin egen acceptans, som startar en isolerad backend med
scriptad generering och kör mot verklig auth, tenantskopning, retrieval,
citatverifiering och sidrastrering — på två telefonviewporter, plus en
axe-genomgång av hela resan:

```bash
cd xs_mobilapp && npm install
make mobile-test
```

Senast sammanhållna verifiering, på Fedora 44 från ren checkout efter enbart
`make setup`: backend **530 passed, 6 skipped**, isolerings/auth/livscykel
**48 passed**, kanonisk frontend **14 passed**, Playwright **11 passed**, lint
och produktionsbygge gröna. Alla skip är miljöberoende och avsiktliga; de
räknas upp i [MVP-statusen](docs/MVP-STATUS.md) tillsammans med exakta
körningar och bevisgränser.

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

## Skrivbordsleverans (Fedora)

Samma produkt kan installeras som ett vanligt skrivbordsprogram. Skalet i
`src-tauri/` startar en paketerad Python-körmiljö som serverar det byggda
React-gränssnittet och `/api/*` från samma slumpmässiga loopback-origin; ingen
produktlogik dupliceras i skalet.

```bash
make desktop-package    # -> dist/brf-dokument-ai-<version>.x86_64.rpm
make desktop-install    # dnf install (drar in tesseract + webkit2gtk4.1)
make desktop-acceptance # full journey mot riktig Tauri/WebKitGTK + självhostad modell
```

Tre resor drivs genom det riktiga Tauri/WebKitGTK-fönstret, och två av dem
behöver **ingen modell** — vilket är en egenskap hos funktionerna och inte hos
skripten, eftersom både fakturagranskningen och postköns läsning är
deterministiska hela vägen:

```bash
make invoice-acceptance  # fakturaresan (ingen modell)
make intake-acceptance   # inkommande post: .eml → bevarat citerbart dokument
                         # → uppgift/bevakning → öppna igen → nytt beslut
make desktop-acceptance-full RUN_LABEL=<etikett>   # alla tre, en etikett
```

Evidensen hamnar i `docs/evidence/<etikett>-{invoice,intake,desktop}-*` —
skärmbilder plus ett maskinläsbart kvitto. Evidens som redan är committad
skrivs aldrig över utan att `--overwrite-evidence` begärs uttryckligen; se
[docs/evidence/acceptansresan-2026-08-03.md](docs/evidence/acceptansresan-2026-08-03.md)
för den senaste körningen.

### Inkommande underlag och fakturagranskning

Skrivbordsappen har en granskningskö: en sparad `.eml` importeras manuellt, dess
PDF-bilagor går genom den vanliga dokumentkedjan, och en fixturfaktura kan
jämföras **read-only** mot ett exakt citerat avtalsvillkor. Inga externa
skrivningar, ingen OAuth, ingen brevlådeanslutning.
Se [docs/INTEGRATIONSDOMAN.md](docs/INTEGRATIONSDOMAN.md).

- [Användar- och byggguide](docs/DESKTOP-FEDORA.md)
- [Beslut om Python-körmiljön](docs/adr/0001-desktop-python-runtime.md)
- [Modellgränsen: vem får peka om, och vart](docs/adr/0002-model-endpoint-boundary.md)
- [Reproducerbar RPM](docs/adr/0003-reproducerbar-rpm.md)
- [Arkitekturbeviset som föregick den](docs/evidence/xs46-tauri-fedora.md)

## Arkitektur

```text
PDF → extract.py → chunker.py → indexer.py
    → answer.py → citations.py → FastAPI → brfv2-mockup
```

- [Specifikation](SPEC.md)
- [Pilotkontrakt](SPEC-PILOT.md)
- [Evidens](docs/evidence/) — senast
  [ren checkout på Fedora](docs/evidence/fedora-clean-checkout-2026-07-27.md)
