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
