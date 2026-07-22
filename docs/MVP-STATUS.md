# MVP-status — BRF Dokument-AI

**Senast avstämd mot kod och körd evidens:** 2026-07-22

## Sammanfattning

MVP-implementationen och den deterministiska lokala acceptansen är klara.
Den kanoniska frontenden och verkliga backenden har en automatiserad
Playwright-svit för hela den definierade produktslingan.

Den avsedda livepiloten med självhostad Gemma 4 12B är däremot **inte
godkänd**. Livekörningen bevisade runtimeidentitet, nätverksgräns och den
kritiska browserresan, men den obligatoriska realkorpusgaten slutade
`VERDICT: NOT READY` när modellen avvisade `q03` trots relevanta chunkar på
rank 1, 2, 4 och 6.

## Produkt och repogräns

- `brfv2-mockup/` är ett separat Git-repo och den **kanoniska
  produktfrontenden**. Den verifierade pilotvyn använder riktiga backenddata.
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

Senast körda sammanhållna lokala resultat:

| Kontroll | Resultat |
|---|---:|
| Backend `pytest -q` | 526 passed, 1 skipped |
| Auth/isolation/livscykel | 48 passed |
| Kanonisk frontend Vitest | 14 passed |
| Kanonisk frontend lint | exit 0 |
| Kanonisk frontend produktionsbygge | exit 0 |
| Playwright acceptance | 11 passed |

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

### Underkänd livegate

- `q03` (`cell_value`) avvisades som `insufficient_data` trots att
  källbärande chunkar låg på rank 1, 2, 4 och 6.
- `q01` gav ett icke-ordagrant citat som verifieraren korrekt underkände som
  `quote_not_found`.
- Samma korpus passerade den scriptade readiness-selftesten. `q03` fortsatte
  att avvisas med `topK` 1, 3 och 6 och efter en begränsad promptdiagnos.

Detta är uppmätt modell-/serverbeteende, inte bevis för att retrieval behöver
byggas om. Citatverifiering eller vägranströsklar får inte försvagas för att
göra gaten grön.

Fullt, icke-känsligt underlag:
[evidence/pilot-live-gemma4-12b-2026-07-22.md](evidence/pilot-live-gemma4-12b-2026-07-22.md).

## Bevisnivåer

| Nivå | Vad den bevisar | Status |
|---|---|---|
| Automatiserad lokal acceptans | Verkliga frontend-/backendkontrakt med deterministisk generation | Godkänd |
| Live manuell browser smoke | Kritisk UI-resa mot avsedd 12B-tjänst | Godkänd för den körda resan |
| Live syntetisk eval | Golden retrieval, grounding, citat och nätverksgräns | Godkänd |
| Live skyddad korpusgate | Modellens obligatoriska realkorpusfrågor och vägran | **Inte godkänd** |
| Extern drift | SSH, tjänst, modellvikter och GPU utanför repot | Krävs vid varje livekörning |

## Återstående blockerare och begränsningar

1. Undersök Gemma-serverns chat template/strukturerade svarsformat så att
   `q03` besvaras med verifierat citat samtidigt som `q11` fortsätter att
   vägras. Kör därefter readinessgaten oförändrad.
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
cd /Users/coffeedev/Projects/brfv2/backend
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

Piloten får beskrivas som livegodkänd först när kommandot avslutas med exitkod
0 och `VERDICT: READY` utan förbjudna nätverksanslutningar eller providerbyte.
