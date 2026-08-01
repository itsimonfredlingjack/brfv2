# MVP-status — BRF Dokument-AI

**Senast avstämd mot kod och körd evidens:** 2026-07-27 (realkorpusgaten omkörd på
commit `a1960b7` efter XS-33:s embedder-livscykeländring; se
[evidence/pilot-live-gemma4-12b-2026-07-27.md](evidence/pilot-live-gemma4-12b-2026-07-27.md)).

## Sammanfattning

MVP-implementationen och den deterministiska lokala acceptansen är klara.
Den kanoniska frontenden och verkliga backenden har en automatiserad
Playwright-svit för hela den definierade produktslingan.

Den avsedda livepiloten med självhostad Gemma 4 12B är nu **READY enligt den
oförändrade realkorpusgaten**. En instrumenterad diagnos visade att q03:s
kodade uppgiftsrad nådde prompten men att kodförklaringen på en annan sida i
samma dokument saknades. Efter en strikt samma-dokument-koppling besvaras q03
med två verifierade citat samtidigt som q11 fortsätter att vägras säkert.

## Produkt och repogräns

- `brfv2-mockup/` är den **kanoniska produktfrontenden** och ligger som
  vanliga spårade filer i det här repot — ingen nästlad utcheckning och ingen
  submodul. Den verifierade pilotvyn använder riktiga backenddata. Fram till
  juli 2026 låg katalogen i ett separat, gitignorerat repo; den historiken
  finns kvar på `migration/brfv2-mockup/*`-grenarna.
- Rotens `src/` är en äldre backendkopplad prototyp. Den underhålls inte som
  den visuella produkten och ska inte få nya integrationer.
- FastAPI-backend, driftverktyg och evidens ligger i huvudrepot.
- Global sök, dokumentbunden chatt, kvalitetskontroll, bevakningar och
  inställningsflöden ligger utanför MVP. I pilotvyn är de dolda, spärrade eller
  uttryckligen märkta som otillgängliga; de visar inte fiktiva backendresultat.

## Skrivbordsleverans (XS-47, 2026-07-28)

Samma produkt finns nu som en installerbar Fedora-applikation. Skalet i
`src-tauri/` startar en paketerad Python-körmiljö som serverar det byggda
React-gränssnittet och `/api/*` från samma slumpmässiga loopback-origin; ingen
produktlogik dupliceras i skalet.

- Artefakt: `dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` (547 MiB, sha256 `b0b1a90a…`), byggd med
  Fedoras `rpmbuild`, med `webkit2gtk4.1`, `gtk3`, `tesseract` och
  `tesseract-langpack-swe` som enda beroenden.
- Hela resan — förstagångskonfiguration, uppladdning, ingestion, grundat svar
  från riktig Gemma 4 12B, citation, PDF-markering, vägran, omstart, bevarat
  tillstånd, säkerhetskopiering och återställning — är körd mot det
  **installerade** paketet, inte mot en checkout.
- Produkten levereras utan konton: `--seed-demo` och `backend/scripts/` finns
  inte i bundlen, och `max@demo.se` fungerar inte.
- Generering kan bara ske mot den självhostade modelltjänst användaren anger.
  `BRF_LLM` är fastnaglat till `selfhosted` och `anthropic` är borttaget ur
  bundlen.

Evidens: [evidence/xs47-desktop-delivery.md](evidence/xs47-desktop-delivery.md),
[maskinläsbar acceptans](evidence/xs47-desktop-acceptance-installed.json).
Byggbeslut: [adr/0001-desktop-python-runtime.md](adr/0001-desktop-python-runtime.md).

## Verifierat MVP-kontrakt

Den automatiserade browser-acceptansen använder Chromium, kanonisk frontend
och verkliga backend-endpoints utan browsermockar. Endast generationen är
scriptad för determinism; svar och citat går fortfarande genom backendens
retrieval-, grounding- och citatkod.

Följande är täckt och grönt:

- login och rätt aktiv förening;
- tenant-scopad dokumentlista;
- adminupload med synkron ingestion/indexering och efterföljande fråga;
- grundat svar med verifierbar citatmetadata;
- rätt dokument, sida, PDF-endpoint och synlig highlight-overlay med positiv
  bredd och höjd;
- säker vägran utan citat för en fråga utan stöd;
- medlem saknar upload/radering i både UI och backend;
- föreningsbyte rensar dokument, färdiga citat och väntande svar;
- readinessvisning för `ready`, `fake`, `none` och otillgänglig backend;
- pilotvyn exponerar inga fiktiva sökresultat eller framtida
  administrationsåtgärder.

Senast körda sammanhållna lokala resultat, från ren checkout på Fedora 44
efter enbart `make setup`:

| Kontroll | Resultat |
|---|---:|
| Backend `pytest -q` | 530 passed, 6 skipped |
| Auth/isolation/livscykel | 48 passed |
| Kanonisk frontend Vitest | 14 passed |
| Kanonisk frontend lint | exit 0 |
| Kanonisk frontend produktionsbygge | exit 0 |
| Playwright acceptance | 11 passed |

Skippen är alla avsiktliga och miljöberoende, inga fel:

| Skip | Villkor |
|---|---|
| `test_llm.py` (1) | kör bara med `RUN_LLM_TESTS=1` — anropar en verklig LLM |
| `test_ocr_ingestion.py`, `test_ocr_spike.py` (3) | kräver tesseract med svenskt språkpaket |
| `test_rerank.py` (1) | kräver den valfria `rerank`-extran och nedladdade vikter |
| `test_corpus_tripwire.py` (1) | kräver seedad data; kör efter `make demo-reset` |

Efter `make demo-reset` finns dataroten och tripwiren kör, vilket ger
**531 passed, 5 skipped**.

OCR behövs bara för skannade PDF:er och ingår inte i pilotslingan. Installera
det på Fedora med `sudo dnf install tesseract tesseract-langpack-swe` om du
vill köra de testerna.

Tidigare status angav 532 passed, 1 skipped. Den siffran mättes på den gamla
macOS-maskinen, där tesseract och reranker-vikterna råkade finnas installerade.
Antalet testfall är oförändrat; skillnaden är vilka valfria beroenden som fanns
på maskinen.

Deterministisk acceptans bevisar lokal reproducerbarhet. Den bevisar inte i
sig att en extern modellserver är nåbar eller att en viss modell klarar den
skyddade BRF-korpusen.

## Livebevis den 22 juli 2026

Den manuellt orkestrerade liveverifieringen använde `BRF_MODE=pilot`,
`selfhosted`, `gemma4:e12b`, produktionens `model2vec`, det lokalt tillgängliga
BRF-materialet och nätverksrevision.

### Godkänt i livekörningen

- SSH-forward och modellens `/models`-svar matchade avsedd Gemma 4 12B-tjänst.
- `/api/health` rapporterade `pilot`, `selfhosted`, `gemma4:e12b`, runtimeetikett
  och `ready=true` utan fallback till `fake`, `none` eller 4B.
- Korpusscope dokumenterades utan filnamn eller innehåll: 9 PDF:er, varav 2
  digitala och 7 skannade.
- Det fulla syntetiska golden setet passerade: recall@6 1.000,
  citatverifiering 1.000, highlight 0.978, dokumentprecision 1.000 och
  false-answer rate 0.000.
- Livebrowsern klarade login, upload/ingestion, ett grundat svar, ett
  resolverbart citat till rätt sida, två synliga highlight-overlays, säker
  vägran och rensning vid föreningsbyte.
- Nätverksrevisionen registrerade endast loopbacktrafik till SSH-forwarden och
  0 externa anslutningar.

### Ursprunglig underkänd livegate och verifierad korrigering

- Baslinjen avvisade `q03` som `insufficient_data`. Instrumenteringen visade
  att uppgiftsraderna låg på rank 1 och 4 medan samma dokuments
  ansvarsförklaring låg på diagnostisk rank 8, utanför `topK=6`.
- `q01` gav ett icke-ordagrant citat som verifieraren korrekt underkände som
  `quote_not_found`.
- Backenden kompletterar nu endast en hämtad kodad tabellrad med dess
  strukturellt identifierade ansvarsförklaring från samma dokument. Inga
  retrievalvikter, trösklar, verifierare eller vägransregler ändrades.
- Den oförändrade livegaten gav därefter `VERDICT: READY`: q09 och q08 fick
  vardera ett verifierat citat, q03 fick två, q02 fick ett och q11 vägrades
  utan citat. Nätverksrevisionen visade en loopbackanslutning och 0 externa.

q01:s icke-ordagranna citat underkänns fortfarande korrekt som
`quote_not_found`; det är en känd icke-gatande begränsning, inte en fabricerad
framgång.

Fullt, icke-känsligt underlag:
[evidence/pilot-live-gemma4-12b-2026-07-22.md](evidence/pilot-live-gemma4-12b-2026-07-22.md).
Korrigering och omkörning:
[evidence/xs32-q03-linked-context-2026-07-22.md](evidence/xs32-q03-linked-context-2026-07-22.md).

## Omkörning efter XS-33 (2026-07-27)

Den oförändrade realkorpusgaten kördes på nytt på commit `a1960b7`, efter XS-33:s
delade embedder-instans (`b939d50`), för att bekräfta att gaten inte tystnat på grund
av livscykeländringen. Samma kommando, samma frågor, ingen ändrad tröskel: `VERDICT:
READY`, q09/q08/q03 vardera med verifierade citat, q11 säkert vägrad, q01:s kända
icke-ordagranna citat fortfarande korrekt underkänt. Nätverksrevisionen visade 1
loopbackanslutning och 0 externa. Fullt underlag:
[evidence/pilot-live-gemma4-12b-2026-07-27.md](evidence/pilot-live-gemma4-12b-2026-07-27.md).

Gaten kördes om igen på XS-36:s hygiencommit `710cf1c` med samma resultat och samma
sex frågeutfall. Den körningen är den första där artefakten själv bär commit-SHA,
modell, runtimeetikett och UTC-tidsstämpel i stället för att pinnas via kringtext:
[evidence/pilot-live-gemma4-12b-2026-07-27-xs36.md](evidence/pilot-live-gemma4-12b-2026-07-27-xs36.md).

## Bevisnivåer

| Nivå | Vad den bevisar | Status |
|---|---|---|
| Automatiserad lokal acceptans | Verkliga frontend-/backendkontrakt med deterministisk generation | Godkänd |
| Live manuell browser smoke | Kritisk UI-resa mot avsedd 12B-tjänst | Godkänd för den körda resan |
| Live syntetisk eval | Golden retrieval, grounding, citat och nätverksgräns | Godkänd |
| Live skyddad korpusgate | Modellens obligatoriska realkorpusfrågor och vägran | **READY** |
| Extern drift | SSH, tjänst, modellvikter och GPU utanför repot | Krävs vid varje livekörning |

### Reproducerbarhetsgräns för realkorpusgaten

Den skyddade realkorpusgaten och `model-readiness-selftest*` kan **inte** köras
från en ren checkout. De läser föreningens verkliga PDF:er från den
gitignorerade katalogen `DONT_PUSH_brf_stuff/` och kräver dessutom en nåbar
`gemma4:e12b`-runtime på `agenntserver`. Det är en accepterad och avsiktlig
gräns, inte dolt lokalt tillstånd: materialet är kundens dokument med möjliga
personuppgifter och ska inte ligga i repot.

Följden är att den här gaten bara kan verifieras om av någon med både
korpusåtkomst och runtimeåtkomst. Allt annat i
[Lokal verifiering](../README.md#lokal-verifiering) — backendtester,
isolering, frontendtester, lint, bygge och Playwright-acceptansen — körs helt
från en ren checkout efter enbart `make setup`.

## Integrationsblocket — liveläge (2026-08-01)

Desktopinstallationen kan nu läsa ur två verkliga system, båda read-only och
båda igångsatta av en namngiven administratör:

* **Brevlåda över Microsoft Graph.** Behörigheterna är en konstant i koden
  (`offline_access`, `User.Read`, `Mail.Read`, plus `Mail.Read.Shared` för en
  delad brevlåda) och kan inte vidgas av någon inställning. Ett valt meddelande
  hämtas som rå MIME och går genom exakt samma importväg som en manuell
  `.eml` — samma formatgränser, samma hash, samma atomiska återställning.
  Ingenting markeras, flyttas eller raderas i brevlådan.
* **Fortnox leverantörsfakturor.** Mappningen är densamma som fixturadaptern
  övade in, och en fältmappningsvy visar vilket Fortnox-fält som blev vilket av
  våra, så att första livekopplingen går att kontrollera i stället för att
  antas. Fortnox erbjuder inget läs-scope; read-only är klientsidigt och vilar
  på att ingen skrivväg finns — se ADR 0004.

Gränsen är byggd som frånvaro av kodväg: `protocols.py` vägrar vid import ett
adapterprotokoll med ett utåtriktat skrivverb, och `egress.py` har ingen metod
som kan skicka annat än GET mot ett API. Det finns ingen polling, ingen
webhook och ingen bakgrundstråd — varje läsning sker för att någon klickade.

Credentials ligger `0600` i föreningens egen katalog och **ingår aldrig i en
säkerhetskopia**; en återställd installation måste anslutas om, vilket
manifestet säger rakt ut.

Granskningen har samtidigt fått läsa det den tidigare bara kunde avstå från:
leverantörsidentitet med styrka (organisationsnummer, exakt namn, bekräftat
alias, bolagsform, svag delträff), svenska datum och löpande avtalstider,
indexreglerade priser som blockerar en självsäker avvikelse, och löptider och
uppsägningstider som citerade fakta. En bilaga som kommit per mejl kan numera
bli föreningens underlag genom att en administratör **arkiverar** den med ett
angivet skäl; en fakturas egna bilagor är fortfarande uteslutna som bevis om
just den fakturan.

Mobilklienten har en **read-only vy av fynden**: samma tre block, samma
citatnavigering till rätt sida med markerad passage, och inget sätt att fatta
ett beslut därifrån. Den gäller den servade backenden — desktopinstallationen
lyssnar med flit bara på en slumpmässig loopback-port och exponeras inte på
nätverket för att en telefon ska nå den. Att ändra på det vore en annan
säkerhetsdiskussion än den här.

**Verifierat mot ett installerat paket.** En RPM byggd från integrationsgrenen
(`f0e8be1`, sha256 `a06233fa…`) är installerad och har klarat både
payload-granskningen (40 tester mot `ops/forbidden_providers.json`) och hela
desktopacceptansen mot verklig Tauri/WebKitGTK och självhostad Gemma 4 12B —
exit 0 på 132 sekunder från ett oprovisionerat utgångsläge. Se
[evidence/integrations-installed-rpm-2026-08-01.md](evidence/integrations-installed-rpm-2026-08-01.md).

Detaljer: [INTEGRATIONSDOMAN.md](INTEGRATIONSDOMAN.md),
[INTEGRATION-OUTLOOK.md](INTEGRATION-OUTLOOK.md),
[INTEGRATION-FORTNOX.md](INTEGRATION-FORTNOX.md),
[adr/0004-utgaende-integrationsgrans.md](adr/0004-utgaende-integrationsgrans.md).

## Källstyrda bevakningar (2026-08-01)

Den tidigare spärrade Bevakningar-fliken är nu en verklig funktion. Motorn läser
föreningens egna dokument och föreslår **daterade åtaganden** — uppsägningsdatum,
avtalsslut, garantitider, besiktningar och återkommande skyldigheter — var och en
med den passage datumet räknades fram ur och räkningen utskriven
(`2026-12-31 minus 3 månader`). En namngiven person godkänner, justerar datumet,
utser ansvarig och väljer påminnelsens framförhållning; inget förslag är ett
åtagande innan dess.

Årshjulet räknas ut på servern — **försenat, snart, senare, återkommande** — så
att desktopvyn och telefonen inte kan vara oense om vad *snart* betyder. Mobilen
visar bevakningarna read-only.

En tidsfrist som inte går att räkna ut blir aldrig en kalenderpost på en gissning.
Den seedade snöröjningsklausulen ("senast tre månader före avtalstidens utgång")
är exakt det fallet och redovisas som odaterbar med skälet utskrivet. Under
utvecklingen daterade en tidigare version av ankarregeln den klausulen från
avtalets *början* och föreslog 2026-08-01 — verifierbart, självsäkert och fel.
Regeln som stänger det, och de tre villkoren den ställer, står i
[BEVAKNINGAR.md](BEVAKNINGAR.md).

Ingen kalenderintegration, inget utskick och ingen bakgrundssynk. `remind_at` är
ett datum vyn sorterar på, inte en påminnelse som skickas någonstans.

## Uppgifter och ansvar (2026-08-02)

Sista ledet i kedjan: ett fynd, en bevakning eller ett inkommande mejl blir
**arbete** med ansvarig, datum, status och en append-only historik — med
ursprungets citat kopierade så att passagen bakom arbetet öppnas även långt
efteråt.

Det är den enda domänen motorn inte kan skapa något i, och asymmetrin är
avsikten: en regelmotor kan läsa ett dokument, men ingens skyldigheter följer av
det förrän en person tar på sig dem. Att skapa en uppgift *är* beslutet.

Blockering och avbrytande kräver ett angivet skäl; att markera klart gör det
inte. En avslutad uppgift är aldrig försenad. Uppgifter raderas aldrig — arbete
som visade sig onödigt avbryts och ligger kvar synligt. Ansvarig är ett namn i
fritext, inte ett användarkonto, så att en entreprenör eller en revisor kan stå
som ansvarig utan att först bli användare i systemet.

Mobilen visar uppgifterna read-only. Detaljer: [UPPGIFTER.md](UPPGIFTER.md).

## Återstående blockerare och begränsningar

1. q01:s prose-control kan fortfarande ge ett icke-ordagrant citat; dagens
   verifierare blockerar det korrekt och frågan ingår inte i readinessgaten.
2. `ready=true` i `/api/health` betyder att en verklig provider är
   konfigurerad; endpointens faktiska nåbarhet bevisas först av tunnelkontroll
   och generation/eval.
3. OCR-ingestion av de skannade filerna är verifierad som ingestion-smoke,
   men livefrågesviten kördes på de två digitala dokumenten.
4. Den kända syntetiska highlightmissen `g14` ligger inom nuvarande gate men
   är en kvarvarande mätbar begränsning.
5. Ingen liveevidens eller automatisk acceptans gör funktioner utanför den
   uttryckliga MVP-gränsen till produktfunktioner.
6. **Liveintegrationerna är verifierade genom en injicerad transport, inte mot
   Microsofts eller Fortnox verkliga servrar.** Varje URL, huvud, formfält,
   vägran och tokenrotation prövas — men den första riktiga inloggningen kräver
   en app-registrering respektive en Fortnox-integration som en människa
   skapar, och den kan ingen testsvit göra åt någon. Fältmappningsvyn finns
   just för att göra den första livekopplingen kontrollerbar.
7. Fortnox leverantörsfaktura saknar periodfält, så periodgranskning görs inte
   för fakturor som läses den vägen. Beloppsgranskningen påverkas inte.
8. Granskningen räknar aldrig upp ett indextal och kan inte härleda ett
   undertecknandedatum som inte står i en citerad passage. Båda fallen ger
   *kan inte verifieras* med klausulen citerad, vilket är rätt svar men inte
   ett svar på frågan.
9. Bevakningsmotorn läser datum, löptider, cykler och de fem åtagandesorterna
   den känner till. Ett åtagande formulerat på ett sätt den inte känner igen
   syns inte alls — den redovisar vad den läste, inte vad den missade, och en
   tom lista betyder därför inte att arkivet saknar frister.
10. Det finns ingen påminnelse som skickas någonstans. `remind_at` styr var en
    bevakning hamnar i vyn; någon måste öppna vyn.

## Omtag av livegaten

```bash
cd backend
BRF_MODE=pilot \
BRF_LLM=selfhosted \
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
BRF_LLM_RUNTIME_LABEL=agenntserver \
BRF_EMBEDDER=model2vec \
uv run python -m scripts.model_readiness \
  --network-audit \
  --out out/pilot-live-rerun
```

Den senaste körningen uppfyllde detta: exitkod 0, `VERDICT: READY`, provider
`selfhosted` och 0 externa nätverksanslutningar. Kravet gäller på nytt efter
varje modell-, prompt-, retrieval- eller driftändring.
