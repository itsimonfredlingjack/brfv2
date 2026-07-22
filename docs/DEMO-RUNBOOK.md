# Operatörsrunbook — BRF Dokument-AI, Gemma 4 12B

Runbook för den lokala pilotstacken: verklig FastAPI-backend, kanonisk
`brfv2-mockup`-frontend och självhostad Gemma 4 12B via SSH-forward.

## Bevisgräns

Tre kontroller ska hållas isär:

1. `npm run test:e2e` är den reproducerbara automatiska acceptansen. Den
   använder verkliga frontend-/backendkontrakt men scriptad generation.
2. `make demo` är en operatörsstart mot den externa 12B-tjänsten. En lyckad
   start bevisar runtimekonfiguration, inte korpusberedskap.
3. `scripts.model_readiness --network-audit` är den formella livegaten för
   den lokalt tillgängliga BRF-korpusen.

Senaste livegaten den 22 juli 2026 är **NOT READY** på `q03`. En livebrowserresa
och det syntetiska golden setet passerade, men de övertrumfar inte realkorpusgaten.

## Förkrav

- demodata seedad med `make demo-reset` vid första körningen;
- SSH-åtkomst till den avsedda värden;
- OpenAI-kompatibel Gemma 4 12B-tjänst på värdens loopbackport 8000;
- installerade backend- och frontendberoenden.

## Start

### 1. Öppna SSH-forwarden

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Låt processen köra i en egen terminal.

### 2. Starta hela pilotstacken

```bash
cd /Users/coffeedev/Projects/brfv2
make demo
```

Startskriptet:

- kräver att `/v1/models` annonserar modellfamiljen Gemma 4 12B;
- startar backend med `BRF_MODE=pilot`, `BRF_LLM=selfhosted`,
  `BRF_LLM_MODEL=gemma4:e12b` och runtimeetiketten `agenntserver`;
- har ingen fallback till Macens lokala `gemma4:e4b`;
- väntar på backendens health-endpoint;
- startar kanonisk frontend på port 5173;
- återanvänder endast en redan frisk pilot/selfhosted-backend;
- dödar aldrig en okänd process som äger en port.

URL: **http://127.0.0.1:5173/brfv2/**

Loggar: `.demo/backend.log` och `.demo/frontend.log` (gitignorerade).

## Kontrollera runtimeidentiteten

```bash
curl -s http://127.0.0.1:8787/api/health | jq '{status,mode,llm_provider,llm}'
```

Förväntad konfigurationsidentitet:

```json
{
  "status": "ok",
  "mode": "pilot",
  "llm_provider": "selfhosted",
  "llm": {
    "provider": "selfhosted",
    "model": "gemma4:e12b",
    "display_name": "Gemma 4 12B",
    "runtime_label": "agenntserver",
    "ready": true
  }
}
```

`ready=true` betyder att en verklig provider är konfigurerad. Det är inte en
reachabilityprobe. `ops/demo.sh check-tunnel`, en faktisk fråga och den formella
readinesskörningen verifierar nåbarhet och beteende. `fake`, `none`, 4B eller
en annan modell är alltid fel för pilotkörningen.

## Kritisk browser smoke

Använd `max@demo.se` / `max-demo-2026`:

1. verifiera aktiv **Brf Gjutformen 12** och adminroll;
2. öppna ett seedat dokument och kontrollera riktig PDF-rendering;
3. ställ en svarbar fråga i AI-chatten;
4. kontrollera att svaret har ett citat och att svarets provenance är
   `Gemma 4 12B · Self-hosted`;
5. klicka citatet och kontrollera rätt dokument, sida och highlight;
6. ställ en ostödd fråga och kontrollera vägran utan citat;
7. byt till **Brf Sjöutsikten 7** och kontrollera att dokument, pågående svar
   och citat från föregående förening är borta;
8. kontrollera att medlemmen saknar upload och radering.

För upload används endast en uttryckligen säker lokal fixture. Den
versionshanterade testfixturen finns på
`brfv2-mockup/e2e/fixtures/pilot-upload.pdf`. En lyckad livekontroll kräver
upload → positiva ingestionstal → fråga → citat till fixturen → sida 1 →
synlig markering. Radera fixturen ur demotenant efteråt.

Dokumentchatt, kvalitetskontroll, bevakningar och global sök ska inte visas som
färdiga funktioner; de är spärrade eller dolda i pilotvyn.

## Formell livegate

Använd ett skyddat lokalt korpusargument utan att skriva ut privata filnamn:

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

Piloten är inte livegodkänd om kommandot ger annan exitkod än 0, annan provider,
`VERDICT: NOT READY`, otillåtna nätverksanslutningar, osäker vägran eller ett
oresolverbart citat. Se
[evidence/pilot-live-gemma4-12b-2026-07-22.md](evidence/pilot-live-gemma4-12b-2026-07-22.md)
för senaste utfall och exakt korpusscope utan privat innehåll.

## Deterministisk acceptans

Kräver inte tunnel eller externa dokument:

```bash
cd /Users/coffeedev/Projects/brfv2/brfv2-mockup
npm run test:e2e
```

Sviten startar isolerade backend- och frontendprocesser på testportar, seedar
temporära tenants och verifierar 11 browserfall inklusive upload, fråga,
citat, PDF/highlight, vägran, behörighet, tenantbyte och fyra readinesslägen.

## Recovery och stopp

```bash
cd /Users/coffeedev/Projects/brfv2
ops/demo.sh check-tunnel
make demo-status
make demo-stop
```

- Saknad tunnel: starta SSH-forwarden och kör `ops/demo.sh check-tunnel` igen.
- Fel process på 8787/5173: undersök och stoppa den uttryckligen; runbooken
  dödar den inte.
- Utgången session: logga in igen.
- Avsiktlig återställning: `make demo-stop && make demo-reset`; kommandot
  raderar och seedar om båda syntetiska demoföreningarna.
- Extern tjänst nere: återställ modellservern och tunneln. Rapportera inte
  livepass förrän readinessgaten därefter är grön.
