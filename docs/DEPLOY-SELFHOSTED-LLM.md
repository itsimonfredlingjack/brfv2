# Runbook — Gemma 4 12B på agenntserver

## Kanonisk pilotarkitektur

BRF-appen ska inte generera med en modell på Macen.

Pilotens enda generationstjänst är:

- värd: `agenntserver`
- operativsystem: Ubuntu
- GPU: NVIDIA RTX 4070, 12 GB VRAM
- modell: `gemma4:e12b`
- OpenAI-kompatibel tjänst: port `8000`
- modellfiler och inferens körs på Ubuntu-servern

Macen får användas som utvecklingsklient och kan nå tjänsten genom en SSH-tunnel. En lokal adress som `http://127.0.0.1:8000/v1` betyder i så fall **den tunnlade Ubuntu-tjänsten**, inte en modell som körs på Macen.

Macens lokala Ollama-modell `gemma4:e4b` är inte fallback, pilotmodell eller produktionsmodell för appen.

## Backendmiljö

Sätt följande där FastAPI-backenden startas:

```bash
BRF_MODE=pilot
BRF_LLM=selfhosted
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1
BRF_LLM_MODEL=gemma4:e12b
BRF_LLM_TIMEOUT_S=300
```

`BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1` gäller i två fall:

1. backenden kör på `agenntserver` bredvid modelltjänsten; eller
2. backenden kör på Macen och port 8000 är vidarebefordrad från `agenntserver` med SSH.

Utan tunnel ska `BRF_LLM_BASE_URL` i stället vara den privata, nåbara adressen till den OpenAI-kompatibla tjänsten på Ubuntu-servern. Exponera inte llama.cpp/vLLM-porten oskyddad mot internet.

## Start från Mac med SSH-tunnel

Starta först en lokal portvidarebefordran till Ubuntu-serverns lokala port 8000:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Starta sedan backenden i en annan terminal:

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make backend-pilot
```

`make backend-pilot` vägrar nu starta om `BRF_LLM_BASE_URL` saknas. Det finns avsiktligt ingen automatisk fallback till Macens port 11434.

## Start när backend kör på agenntserver

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make backend-pilot
```

## Verifiering

Kontrollera först backendens hälsa:

```bash
curl http://127.0.0.1:8787/api/health
```

För en giltig pilotprocess ska svaret innehålla:

```json
{
  "mode": "pilot",
  "llm_provider": "selfhosted"
}
```

Kontrollera därefter att modelltjänsten annonserar rätt modell och att en verklig fråga ger ett verifierat citat. Ett svar från `fake`, `none` eller `gemma4:e4b` är inte en godkänd pilotkörning.

## Nätverksprincip

Dokumenttext får endast lämna backendprocessen till den självhostade 12B-tjänsten på `agenntserver`. Självhostade evalkörningar ska därför fortsätta använda nätverksrevisionen:

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make eval-selfhosted
```

En SSH-tunnel kan synas som loopback i revisionsloggen, men den faktiska inferensen sker på Ubuntu-serverns RTX 4070.
