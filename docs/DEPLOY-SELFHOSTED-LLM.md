# Pilotdrift — Gemma 4 12B på agenntserver

## Driftkontrakt

Pilotens enda generationstjänst är den OpenAI-kompatibla Gemma 4 12B-tjänsten
på Ubuntu-värden `agenntserver` med RTX 4070. Macen är klient och kan nå
tjänsten genom SSH-forward.

Macens lokala `gemma4:e4b` är inte pilotmodell och är aldrig fallback. Backend
i `BRF_MODE=pilot` vägrar starta om aktiv provider inte är `selfhosted`.

## Backendmiljö

```bash
BRF_MODE=pilot
BRF_LLM=selfhosted
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1
BRF_LLM_MODEL=gemma4:e12b
BRF_LLM_RUNTIME_LABEL=agenntserver
BRF_LLM_TIMEOUT_S=300
```

Loopback-URL:en betyder antingen att backend kör bredvid tjänsten på servern
eller, på Macen, att porten är SSH-forwardad. Exponera inte modellporten
oskyddad mot internet och skriv inte privata adresser i spårade auditfiler.

## Start från Mac

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

I en annan terminal:

```bash
cd /Users/coffeedev/Projects/brfv2
make demo
```

`make demo` anropar tunnelkontrollen, startar pilotbackend på 8787 och
kanonisk frontend på 5173. För enbart backend:

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make backend-pilot
```

`make backend-pilot` kräver explicit `BRF_LLM_BASE_URL`; det finns ingen
automatisk provider- eller modellfallback.

## Identitetskontroll

```bash
ops/demo.sh check-tunnel
curl -s http://127.0.0.1:8787/api/health | jq '{status,mode,llm_provider,llm}'
```

En korrekt process rapporterar minst:

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

Frontend visar dessa fält från backend; den har ingen hårdkodad etikett som
ersätter runtimeidentiteten. `ready` är konfigurationsstatus, inte en aktiv
nätverksprobe. Tunnelkontrollen och en verklig modellförfrågan krävs också.

## Reproducerbar readiness och nätverksrevision

För skyddad lokal korpus:

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

För det syntetiska golden setet:

```bash
cd /Users/coffeedev/Projects/brfv2
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make eval-selfhosted
```

Nätverksauditorn tillåter loopback-forwarden och den uttryckligt valda
selfhosted-endpointen och ska stoppa annan TCP-trafik. En tunnel syns därför
som loopback i auditfilen även om inferensen sker på serverns GPU.

## Aktuell livebegränsning

Körningen den 22 juli 2026 bekräftade rätt tunnel, provider, modell,
runtimeetikett, svarprovenance och 0 externa anslutningar. Den skyddade
realkorpusgaten gav ändå exitkod 1 och `VERDICT: NOT READY`: `q03` vägrades
trots att relevanta chunkar fanns i retrievalresultatet. En annan kontroll
gav ett icke-ordagrant citat som verifieraren korrekt avvisade.

Konfigurationen är alltså bevisad, men livepiloten är inte godkänd. Ändra inte
grounding- eller citatkrav för att få en grön signal. Efter en server-/modellfix
ska samma readinesskommando köras om och måste ge exitkod 0.

Icke-känslig evidens:
[evidence/pilot-live-gemma4-12b-2026-07-22.md](evidence/pilot-live-gemma4-12b-2026-07-22.md).
