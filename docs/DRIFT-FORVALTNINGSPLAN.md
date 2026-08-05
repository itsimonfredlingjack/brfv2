# Drift- och förvaltningsplan — BRF Dokument-AI

**Gäller från commit:** `37653d7` (accepterad BP5-pilot, `main`).
**Syfte:** göra fortsatt drift av piloten begriplig utan att förlita sig på
byggarens minne. Kompletterar — dupliterar inte — de befintliga
driftdokumenten:

- [Operatörsrunbook](DEMO-RUNBOOK.md) — start, browsersmoke, formell livegate
- [Pilotdrift med Gemma 4 12B](DEPLOY-SELFHOSTED-LLM.md) — agenntserver-tjänsten, felsökning
- [Demo quickstart](DEMO-QUICKSTART.md) — kort körschema
- [MVP-status](MVP-STATUS.md) — bevisnivåer och kända begränsningar

Den här planen länkar till de kommandona i stället för att upprepa dem, och
lägger till det som saknades: topologi i ett stycke, backup/recovery,
konfigurations-/hemlighetsinventering, uppdateringsprocedurer, ägarskap och en
felsökningstabell.

## 1. Topologi

Två värdar, en riktning för trafiken:

```
Fedora (produkt-/utvecklingsvärd)              Ubuntu "agenntserver" (modellruntime, RTX 4070)
─────────────────────────────────              ────────────────────────────────────────────
FastAPI-backend  :8787  (BRF_MODE=pilot)   ──▶  SSH-tunnel :8000 ──▶ llama.cpp-container :8000
Kanonisk frontend :5173 (vite/brfv2-mockup)     (ghcr.io/ggml-org/llama.cpp:server-cuda,
Lokal SQLite (data/auth.db) + JSON-korpus         GGUF-vikter i HF-cache, restart: unless-stopped,
  per tenant (data/tenants/<brf-id>/)             compose-fil /home/simon/llama-cpp/docker-compose.yml)
```

- **Fedora är produkt-/utvecklingsvärd**: kör backend, frontend, all lagring
  och alla tester. Ingen del av produktens data lämnar den här värden i
  normal drift.
- **Ubuntu-servern `agenntserver` är enbart modellruntime**: en llama.cpp-
  container som exponerar en OpenAI-kompatibel `/v1`-yta på loopback-port
  8000. Den äger ingen produktdata, ingen tenant-lagring och inget auth.
- **Nätverksvägen är en explicit SSH-forward**, inte en öppen tjänst:
  `ssh -N -L 8000:127.0.0.1:8000 agenntserver`. Modellporten ska aldrig
  exponeras oskyddad mot internet (se [DEPLOY-SELFHOSTED-LLM.md](DEPLOY-SELFHOSTED-LLM.md)).
  Nätverksrevisorn (`--network-audit`) verifierar vid varje formell gate att
  endast loopback/den valda selfhosted-endpointen förekommer.
  **Utan människa vid terminalen: `agenntserver-lan`.** Tailnet-aliaset går
  genom Tailscale SSH, som kräver en interaktiv webbinloggning och därför
  hänger i en acceptanskörning eller ett skript. LAN-aliaset är samma värd och
  samma modelltjänst, med nyckelautentisering.
- **Portgränser**: 8787 (backend), 5173 (frontend), 8000 (tunnlad
  modellport, endast loopback på Fedora-sidan).

**Status:** Verifierat via [DEPLOY-SELFHOSTED-LLM.md](DEPLOY-SELFHOSTED-LLM.md),
`Makefile` och `ops/demo.sh` på `main`. Detaljer om `agenntserver`s egen
konfiguration (OS-version, andra tjänster på boxen) är **Antagande** — ingen
inventering av den värden ingår i det här repot.

## 2. Start, stopp, reset

Alla kommandon körs från repo-roten på Fedora om inget annat anges.

| Åtgärd | Kommando | Kommentar |
|---|---|---|
| Engångsuppsättning | `make setup` | Idempotent, inget sudo (`ops/setup.sh`) |
| Starta hela pilotstacken | `ssh -N -L 8000:127.0.0.1:8000 agenntserver` (egen terminal) + `make demo` | Kräver att tunneln redan är öppen |
| Endast backend, dev-läge | `make backend` | Standardleverantör (`claude` CLI eller `ANTHROPIC_API_KEY`), ingen pilot-gate |
| Endast backend, pilot-läge | `BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=gemma4:e12b make backend-pilot` | Kräver explicit `BRF_LLM_BASE_URL`, ingen fallback |
| Endast frontend | `make frontend` | Port 5173 |
| Status | `make demo-status` | Skiljer på "startad av make demo" och "körs men okänd ägare" |
| Stopp | `make demo-stop` | Stoppar **bara** PID-spårade processer från `make demo`; rör aldrig en okänd processägare på 8787/5173 |
| Destruktiv reset av demodata | `make demo-stop && make demo-reset` | Nollställer och återseedar **båda** de syntetiska demoföreningarna + golden set. Rör aldrig `DONT_PUSH_brf_stuff/` eller riktiga kundtenanter |
| Tunnelkontroll fristående | `ops/demo.sh check-tunnel` | Verifierar att port 8000 annonserar Gemma 4 12B, inte bara att något svarar |

**Verifierat i den här uppgiften:** `make test-isolation` (48 passed) och en
manuell dev-lägessmoke — start av `uvicorn app.main:create_app` på :8787,
`curl /api/health` gav `status=ok, mode=dev, tenants=2`, därefter stopp — allt
kördes lokalt på Fedora utan pilot-runtime.

**Ej körd i den här uppgiften, med skäl:** fullständig `make demo` mot
`agenntserver` (kräver aktiv SSH-tunnel och den externa GPU-tjänsten, som
inte är åtkomlig från den här sessionen) och `make demo-reset` (destruktivt
mot lokala demoföreningar; körs bara av en operatör som avsiktligt vill
återställa dem).

## 3. Backup och recovery

Det finns **ingen extern databas eller molnlagring**. All tillståndsdata är
filbaserad under `backend/data/`:

| Data | Plats | Karaktär |
|---|---|---|
| Auth (users, tenants, memberships, sessions) | `backend/data/auth.db` (SQLite) | Skrivs vid inloggning/tenant-CRUD |
| Dokument + extraherad text per tenant | `backend/data/tenants/<brf-id>/{docs,extract}/`, `documents.json`, `tenant_meta.json` | Skrivs vid upload/radering |
| Riktig kundkorpus (om sådan används) | `DONT_PUSH_brf_stuff/` (gitignorerad, utanför repot) | Aldrig i git; kundens dokument, ev. personuppgifter |
| Golden set / evalresultat | `backend/eval/`, `backend/out/` | Regenereras av `scripts.seed`/`scripts.eval`, inte primärdata |

**Backup-procedur (Härlett — ingen automatiserad backup finns i repot idag):**
en filsystemskopia av `backend/data/` (och, om relevant, `DONT_PUSH_brf_stuff/`)
tagen medan backend är stoppad täcker hela tillståndet. Det finns inget
inbyggt schema-migreringsverktyg — `documents.json`/`tenant_meta.json` har
inget versionsfält, så en återställning måste ske mot samma kodversion som
skrev filerna eller verifieras om med `make test-isolation` +
`scripts.model_readiness --selftest` efter återställning.

**Recovery-procedur:**

1. Stoppa allt: `make demo-stop`.
2. Återställ `backend/data/` från senaste kopian (manuellt filsystemsteg —
   inget `make`-mål gör detta).
3. Starta om dev-läge (`make backend`) och kör `make test-isolation` samt
   `curl /api/health` för att bekräfta att auth och tenant-antal ser rimliga
   ut innan pilotläge startas igen.
4. Om `agenntserver`-tjänsten själv behöver återställas: se
   felsökningskedjan i [DEPLOY-SELFHOSTED-LLM.md](DEPLOY-SELFHOSTED-LLM.md#felsökning-tjänsten-svarar-inte-på-8000)
   (NVML-mismatch → `modprobe`-ombladdning → CDI-regenerering →
   `docker compose up -d --force-recreate`).
5. Total katastrofåterställning på ny maskin: klona repot, `make setup`,
   återställ `backend/data/` från backup, `make test`, sedan pilotstart.

**Status:** backup-mekanismen ovan är **Antagande/Härlett** — det finns
ingen schemalagd backup-tjänst eller verifierad restore-övning i det här
repot. Se ägarskapstabellen (§8) för `TBD`.

## 4. Ingestion, admin och tenant-verifiering

- **Tenant- och användarhantering sker via CLI, inte publik signup:**
  `uv run python -m scripts.tenant {create-tenant|add-user|add-membership|delete-tenant|list}`
  (`backend/scripts/tenant.py`). `create-tenant` kräver `--corpus-origin`
  (`customer|public_scraped|synthetic`) — ingen standard, ett medvetet
  skyddsräcke mot att blanda korpustyper.
- **Admin vs medlem** avgörs av `--role` i `add-membership`. Endast admin kan
  ladda upp/radera dokument (`POST`/`DELETE /api/brf/{brf_id}/documents...`);
  detta är verifierat av `test_isolation.py`/Playwright-sviten, inte bara
  dokumenterat.
- **Uppladdning:** admin loggar in, väljer aktiv förening, laddar upp PDF via
  UI eller `POST /api/brf/{brf_id}/documents`. Ingestion (extraktion, chunking,
  indexering) körs synkront i samma anrop.
- **Verifiera att ett uppladdat dokument blev sökbart och citerbart:**
  1. Ställ en fråga i AI-chatten vars svar rimligen finns i dokumentet.
  2. Kontrollera att svaret har minst ett citat.
  3. Klicka citatet och verifiera rätt dokument, rätt sida
     (`GET /api/brf/{brf_id}/documents/{doc_id}/pdf`) och en synlig
     highlight-overlay med positiv bredd/höjd.
  4. Om svaret saknar citat: kontrollera `GET .../documents` att dokumentet
     verkligen listades och att extraktionen (`extract/<id>.json`) inte är
     tom — det senare pekar på ett OCR-behov (se §7).
  Denna kedja är exakt vad `npm run test:e2e` automatiserar deterministiskt
  och vad den formella livegaten (§6) kräver mot verklig modell.

## 5. Konfiguration och hemligheter

Namn och syfte, inga värden. Inget härifrån ska loggas eller skrivas till
spårade filer i klartext.

| Variabel | Syfte |
|---|---|
| `BRF_MODE` | `dev` (standardleverantör) eller `pilot` (kräver `selfhosted`, ingen fallback) |
| `BRF_DATA_ROOT` | Override av `backend/data/` — används av tester/e2e för isolerade dataset |
| `BRF_LLM` | Tvingar leverantör: `selfhosted\|api\|cli\|fake` |
| `BRF_LLM_BASE_URL` | Adress till den självhostade OpenAI-kompatibla modelltjänsten (normalt den tunnlade `http://127.0.0.1:8000/v1`) |
| `BRF_LLM_MODEL` | Modellalias skickat i requests, t.ex. `gemma4:e12b` |
| `BRF_LLM_API_KEY` | Bearer-token om modellservern kräver auth (t.ex. vLLM `--api-key`) — tomt för dagens llama.cpp-tjänst |
| `BRF_LLM_TIMEOUT_S` | Timeout för modellanrop i sekunder (default 300) |
| `BRF_LLM_RUNTIME_LABEL` | Etikett som visas i UI/health för vilken runtime som svarade (t.ex. `agenntserver`) |
| `BRF_EMBEDDER` | `hashed\|model2vec` — tvingar embedding-leverantör |
| `BRF_RERANK_MODEL` | Override av cross-encoder-modell (default `jinaai/jina-reranker-v2-base-multilingual`), endast relevant om `rerank`-extran är installerad |
| `BRF_SESSION_TTL_HOURS` | Sessionslängd i timmar (default 336) |
| `BRF_SCRIPTED_LLM_DELAY_MS` | Endast testsyfte — konstgjord fördröjning i den scriptade FakeLLM |
| `ANTHROPIC_API_KEY` | Alternativ standardleverantör i dev/eval om ingen `claude` CLI-session finns |

Inga API-nycklar, lösenord eller tokens ligger i repot. Demokontonas
lösenord i [DEMO-QUICKSTART.md](DEMO-QUICKSTART.md) är avsiktligt publika
testuppgifter för de två syntetiska demoföreningarna — de är inte hemligheter
och ska inte återanvändas för riktiga kundtenanter.

## 6. Uppdateringsprocedurer

| Komponent | Procedur | Verifiering efteråt |
|---|---|---|
| Python-beroenden (backend) | Uppdatera `pyproject.toml`/`uv.lock`, `cd backend && uv sync` | `make test` |
| Node-beroenden (frontend) | Uppdatera `package.json` och kör `npm install` i `brfv2-mockup/` | `npm test && npm run lint && npm run build` i `brfv2-mockup/` |
| Embedding-vikter (`model2vec`) | Bytt `Model2VecEmbedder.MODEL_ID` i `app/embeddings.py`, kör om `ops/setup.sh`-steget för embedder-cache eller låt lazy-fetch ske vid första `ask()` | `make eval-fast` (retrieval utan LLM) för att se att recall inte kollapsar |
| Självhostad modellruntime (`agenntserver`) | Uppdatera `docker-compose.yml`/GGUF-vikter på värden, `sudo docker compose up -d --force-recreate` i `/home/simon/llama-cpp` | `ops/demo.sh check-tunnel` + full livegate (§6.1) — modellbyte kräver **alltid** omkörning |
| Databas/schema | **Ingen migreringsmekanism finns.** `documents.json`/`tenant_meta.json`/`auth.db` har inget versionsfält | Efter en schemaändring i koden: kör om `scripts.seed --reset` mot en testmiljö, `make test`, och verifiera manuellt att befintliga produktionstenanters filer fortfarande läses korrekt innan de rörs. **TBD — ingen formell migreringsprocess är definierad; behöver ägarbeslut innan en verklig schemaändring görs mot en produktionstenant.** |

### 6.1 Rutinverifiering efter varje ändring

Kör i den här ordningen, avbryt vid första röda steget:

1. `make test` (backend, offline, deterministiskt) — obligatoriskt, alltid.
2. `make test-isolation` om ändringen rör auth, tenant eller lagring.
3. `cd brfv2-mockup && npm test && npm run lint && npm run build` om
   frontend rördes.
4. `npm run test:e2e` i `brfv2-mockup/` — obligatoriskt före varje release/
   demo; kräver ingen tunnel eller extern korpus.
5. Live-readiness (`ops/demo.sh check-tunnel` + `make demo` +
   `scripts.model_readiness --network-audit`) **krävs** när ändringen rör
   modell, prompt, retrieval, embedding eller drift — inte bara vid release.
6. Den privata realkorpusgaten (samma `scripts.model_readiness`-kommando
   mot `DONT_PUSH_brf_stuff/`) krävs endast av den/de med korpus- **och**
   runtimeåtkomst, och endast före att ett pilotgodkännande återbekräftas —
   se reproducerbarhetsgränsen i [MVP-STATUS.md](MVP-STATUS.md#reproducerbarhetsgräns-för-realkorpusgaten).

## 7. Kända operativa begränsningar

- **Extern runtime-beroende**: pilotgenerering kräver `agenntserver` och en
  aktiv SSH-tunnel. Ingen del av backend/frontend kan producera ett riktigt
  pilotsvar utan den värden.
- **Privat korpus**: den skyddade realkorpusgaten kräver `DONT_PUSH_brf_stuff/`,
  som inte finns i en ren checkout och inte ska committas (kundens dokument,
  ev. personuppgifter).
- **OCR-gräns**: skannade PDF:er kräver `tesseract` + `tesseract-langpack-swe`
  (`sudo dnf install ...` på Fedora), ingår inte i pilotslingans automatiska
  gate och är verifierad endast som ingestion-smoke, inte i livefrågesviten.
- **Konfigurerad kontra attesterad modellidentitet**: `/api/health`s
  `ready: true` är konfigurationsstatus (rätt env-variabler satta), inte en
  aktiv nätverksprobe. Faktisk nåbarhet och modellbeteende bevisas först av
  `ops/demo.sh check-tunnel` och en verklig fråga/eval.
- **q01 icke-ordagrant citat**: känd, korrekt avvisad begränsning
  (`quote_not_found`), ingår inte i readinessgaten men ska inte "fixas" genom
  att luckra upp citatverifieringen.
- **Parkad post-pilot-scope**: global sök, dokumentbunden chatt,
  kvalitetskontroll, bevakningar och allmän styrelseadministration är
  uttryckligen utanför MVP och ska förbli dolda/spärrade i pilotvyn — den
  här planen ändrar inte det.

## 8. Ägarskap

Reella ägare där kända; annars uttryckligt `TBD` i stället för en gissning.

| Ansvarsområde | Ägare |
|---|---|
| Produktkod (backend, frontend, driftskript) | Simon Fredling Jack (repo-ägare, all commit-historik) |
| Modellruntime (`agenntserver`, GPU, llama.cpp-container) | **TBD — ägarbeslut krävs.** Compose-filen ligger under `/home/simon/llama-cpp`, vilket antyder samma person, men ingen formell driftsöverenskommelse finns dokumenterad |
| Korpus/evidens (kundens dokument i `DONT_PUSH_brf_stuff/`, evidensrapporter) | **TBD — ägarbeslut krävs.** Ingen namngiven dataförvaltare eller GDPR-kontakt finns dokumenterad |
| Backup och restore-övning | **TBD — ägarbeslut krävs.** Ingen backup-tjänst eller ansvarig person finns idag (se §3) |
| Incidenthantering (produktionsstörning, säkerhetsincident) | **TBD — ägarbeslut krävs.** Ingen jourlista eller eskaleringsväg utanför den här planens felsökningstabell finns definierad |
| Godkännande av produktionsändringar (t.ex. modellbyte, schemaändring) | **TBD — ägarbeslut krävs.** Idag är gaten teknisk (readiness-kommandot); ingen mänsklig godkännarroll är utsedd |

## 9. Operatörschecklista (kort form)

Före varje pilotpass:

- [ ] `git status` rent, `main` uppdaterad
- [ ] SSH-tunnel öppen: `ssh -N -L 8000:127.0.0.1:8000 agenntserver`
      (`agenntserver-lan` om ingen kan klara Tailscale-inloggningen — samma värd)
- [ ] `ops/demo.sh check-tunnel` grön (annonserar Gemma 4 12B)
- [ ] `make demo` klar, `Demo igång:` visad
- [ ] `/api/health` visar `mode=pilot, llm_provider=selfhosted, model=gemma4:e12b, ready=true`
- [ ] Kritisk browsersmoke genomförd (se [DEMO-RUNBOOK.md](DEMO-RUNBOOK.md#kritisk-browser-smoke))
- [ ] Vid release/ändring: readinessgaten (§6.1 punkt 5) grön, exitkod 0

Efter varje pilotpass:

- [ ] `make demo-stop`
- [ ] Stäng SSH-tunneln (Ctrl+C)
- [ ] Radera ev. tillfälliga uploadfixturer ur demotenant
- [ ] `make demo-status` bekräftar allt stoppat

## 10. Felsökningstabell

| Symtom | Trolig orsak | Åtgärd |
|---|---|---|
| `make demo` fastnar på tunnelkontroll | SSH-tunneln inte öppen eller port 8000 svarar inte | Öppna tunneln i egen terminal, kör `ops/demo.sh check-tunnel` igen |
| Tunneln svarar men fel modell annonseras | Fel tjänst/modell kör på `agenntserver`, eller tunneln pekar fel | `ssh agenntserver 'sudo docker ps -a --filter name=llama-server'`; kontrollera compose-filen |
| Container `Exited (127)` | CUDA kunde inte initieras | `ssh agenntserver 'nvidia-smi'` |
| `Failed to initialize NVML: Driver/library version mismatch` | Kernelmodul och userspace ur synk efter paketuppgradering | Stoppa GPU-processer, `modprobe -r`/`modprobe` om nvidia-modulerna (se [DEPLOY-SELFHOSTED-LLM.md](DEPLOY-SELFHOSTED-LLM.md#felsökning-tjänsten-svarar-inte-på-8000)) |
| Container startar ej: `libEGL_nvidia.so` saknas | Cachad CDI-spec mot gammal drivrutin | `nvidia-ctk cdi generate --output=/var/run/cdi/nvidia.yaml`, `docker compose up -d --force-recreate` |
| Backend startar inte, port 8787 upptagen av okänd process | Ospårad process äger porten | `make demo-status`; undersök manuellt — skriptet dödar aldrig okänt |
| Backend startar men `mode`/`llm_provider` fel | Miljövariabler saknas/felaktiga vid pilotstart | Kontrollera `BRF_MODE`, `BRF_LLM`, `BRF_LLM_BASE_URL`, `BRF_LLM_MODEL` |
| Frontend svarar inte på 5173 | Byggfel eller okänd processägare på porten | `tail .demo/frontend.log`; `make demo-status` |
| Uppladdat dokument ger inget citat | Extraktionen tom (skannad PDF utan OCR) eller frågan verkligen obesvarbar | Kontrollera `extract/<id>.json`; installera tesseract om skannat; annars är vägran korrekt |
| Fel/annan förenings dokument syns efter föreningsbyte | Regressions i tenant-isolering | Stoppa omedelbart, kör `make test-isolation`, rapportera som säkerhetsincident (§8, TBD-ägare) innan vidare pilotdrift |
| `ready=true` men inget svar kommer | `ready` är konfigurationsstatus, inte reachability | Kör `ops/demo.sh check-tunnel` och en verklig fråga; om tunneln är nere, se raderna ovan |
| Realkorpusgaten ger `VERDICT: NOT READY` | Modell-, prompt-, retrieval- eller driftregression | Se senaste evidensrapport i `docs/evidence/pilot-live-gemma4-12b-*.md` för baslinje; rapportera inte pilotgodkännande förrän gaten är grön igen |

## 11. Verifieringslogg för den här planen

- `make test-isolation` → 48 passed (kört 2026-07-27, commit `37653d7`).
- Dev-lägessmoke: `uvicorn app.main:create_app --factory --port 8787`,
  `curl /api/health` → `status=ok, mode=dev, tenants=2`, process stoppad
  igen. Kört lokalt på Fedora, ingen pilot-runtime inblandad.
- Alla länkade filsökvägar (`docs/evidence/*.md`, `DEMO-RUNBOOK.md`,
  `DEPLOY-SELFHOSTED-LLM.md`, `DEMO-QUICKSTART.md`, `MVP-STATUS.md`,
  `SPEC-PILOT.md`) bekräftade existerande på `main`.
- **Ej körda, med skäl:** `make demo` mot verklig `agenntserver`-tjänst
  (kräver extern SSH-tunnel och GPU-runtime som inte är åtkomlig från den
  här sessionen), `make demo-reset` (destruktivt mot demoföreningar, körs
  bara på operatörens initiativ), realkorpusgaten (kräver privat korpus +
  runtimeåtkomst enligt den accepterade reproducerbarhetsgränsen), samt
  faktiska backup/restore-, GPU-drivrutins- och NVML-felsökningsstegen i §3
  och §10 (kräver skrivåtkomst till `agenntserver` respektive en verklig
  krasch att återhämta från).
