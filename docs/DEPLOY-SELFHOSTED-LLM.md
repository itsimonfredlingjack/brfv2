# Pilotdrift — Gemma 4 12B på agenntserver

## Driftkontrakt

Pilotens enda generationstjänst är den OpenAI-kompatibla Gemma 4 12B-tjänsten
på Ubuntu-värden `agenntserver` med RTX 4070. Utvecklingsmaskinen är klient och
når tjänsten genom SSH-forward.

Ingen mindre lokal modell (t.ex. `gemma4:e4b`) är pilotmodell eller fallback.
Backend i `BRF_MODE=pilot` vägrar starta om aktiv provider inte är
`selfhosted`.

Tjänsten är en llama.cpp-container. Compose-filen ligger i
`/home/simon/llama-cpp/docker-compose.yml` på `agenntserver` och kör
`ghcr.io/ggml-org/llama.cpp:server-cuda` mot GGUF-vikterna i värdens
HuggingFace-cache, med `restart: unless-stopped`.

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
eller, på utvecklingsmaskinen, att porten är SSH-forwardad. Exponera inte
modellporten oskyddad mot internet och skriv inte privata adresser i spårade
auditfiler.

## Start från utvecklingsmaskinen

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

**Icke-interaktiva körningar använder LAN-aliaset.** `agenntserver` går över
tailnet, där Tailscale SSH tar över anslutningen och kräver en interaktiv
webbinloggning (`https://login.tailscale.com/a/...`). En människa vid en
terminal klarar det; en acceptanskörning, ett skript eller en agent gör det
inte — anslutningen hänger tills den timear ut, och skälet syns bara i
`ssh -vv`. Öppna tunneln över LAN i de fallen:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan
```

**Samma värd, samma modelltjänst** — `agenntserver-lan` är bara
`~/.ssh/config`-aliaset för LAN-adressen med nyckelautentisering. Vilket alias
som användes ändrar ingenting i vad som testas.

I en annan terminal:

```bash
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

För det syntetiska golden setet:

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make eval-selfhosted
```

Nätverksauditorn tillåter loopback-forwarden och den uttryckligt valda
selfhosted-endpointen och ska stoppa annan TCP-trafik. En tunnel syns därför
som loopback i auditfilen även om inferensen sker på serverns GPU.

## Aktuell liveverifiering

Körningen den 22 juli 2026 bekräftade rätt tunnel, provider, modell,
runtimeetikett, svarprovenance och 0 externa anslutningar. Efter XS-32-fixen
gav den oförändrade skyddade realkorpusgaten exitkod 0 och `VERDICT: READY`:
q03 besvarades med två verifierade citat och q11 vägrades säkert.

q01:s icke-ordagranna citat avvisas fortfarande korrekt. Ändra inte grounding-
eller citatkrav för att maskera den begränsningen. Samma readinesskommando ska
köras om efter varje modell-, prompt-, retrieval- eller driftändring.

Icke-känslig evidens:
[evidence/pilot-live-gemma4-12b-2026-07-22.md](evidence/pilot-live-gemma4-12b-2026-07-22.md).
Fix och omkörning:
[evidence/xs32-q03-linked-context-2026-07-22.md](evidence/xs32-q03-linked-context-2026-07-22.md).

## Felsökning: tjänsten svarar inte på 8000

Kontrollera i den här ordningen, från utvecklingsmaskinen och sedan på värden.

```bash
ops/demo.sh check-tunnel                      # tunnel + rätt modellidentitet
ssh agenntserver 'sudo docker ps -a --filter name=llama-server'
```

**Containern har status `Exited (127)`.** Det betyder normalt att CUDA inte
gick att initiera. Kontrollera drivrutinen:

```bash
ssh agenntserver 'nvidia-smi'
```

**`Failed to initialize NVML: Driver/library version mismatch`.** Kernelmodulen
och userspace-biblioteken kommer från olika drivrutinsversioner — typiskt efter
en paketuppgradering utan omstart. Ladda om modulerna; det kräver att alla
GPU-processer stoppas först:

```bash
ssh agenntserver
cd ~/discord-transcriber && ./stop-all.sh      # eller vad som håller GPU:n
sudo modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo modprobe nvidia nvidia_uvm
nvidia-smi                                     # ska nu visa rätt version
```

**Containern startar fortfarande inte, med
`open /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.<gammal version>: no such
file`.** CDI-specen genererades mot den gamla drivrutinen och är cachad.
Generera om den:

```bash
sudo nvidia-ctk cdi generate --output=/var/run/cdi/nvidia.yaml
cd /home/simon/llama-cpp && sudo docker compose up -d --force-recreate
```

Starta sedan de tjänster du stoppade. Modellen tar omkring tio sekunder att
läsa in och lägger beslag på cirka 8 GB VRAM.
