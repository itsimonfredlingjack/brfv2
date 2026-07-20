# brfv2 — kanonisk produktfrontend

Detta är den avsedda visuella sidan för BRF Dokument-AI. Repots historiska namn `brfv2-mockup` beskriver dess ursprung, inte dess fortsatta roll.

## Riktning

Frontendens layout, dokumentarbetsyta och responsiva beteende ska bevaras. Den nuvarande fiktiva datan ska ersättas stegvis med de verkliga API-kontrakten från backend-repot i den överordnade arbetsytan:

`/Users/coffeedev/Projects/brfv2/backend`

Det är fel riktning att porta denna design tillbaka till rotens äldre `src/`. Den här appen ska i stället kopplas till FastAPI-backenden.

## Lokal start

Starta backenden från det överordnade repot:

```bash
cd /Users/coffeedev/Projects/brfv2
make demo-reset
make backend
```

Starta sedan denna frontend:

```bash
cd /Users/coffeedev/Projects/brfv2/brfv2-mockup
npm run dev
```

Vite proxar `/api` till `http://127.0.0.1:8787`.

## Pilotmodell

Frontend pratar endast med FastAPI. Modellen ligger bakom backendkontraktet.

Pilotens generation ska köras med `gemma4:e12b` på Ubuntu-servern `agenntserver` med RTX 4070. Macens lokala `gemma4:e4b` ska inte användas av appen.

När backenden kör lokalt på Macen används normalt en SSH-tunnel till Ubuntu-serverns port 8000:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver

cd /Users/coffeedev/Projects/brfv2
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make backend-pilot
```

## Integrationsordning

1. autentisering och aktiv BRF;
2. verklig dokumentlista, uppladdning, radering och PDF-visning;
3. global dokumentchatt med verifierade citat;
4. dokumentbunden chatt;
5. först därefter Granskning och Bevakningar, när riktiga backendkontrakt finns.

Fiktiva dokument, citat, sidnummer, statusar och AI-svar får inte presenteras som verkliga systemresultat. Under övergången ska återstående mockytor vara tydligt märkta och avgränsade.
