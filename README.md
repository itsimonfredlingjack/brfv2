# BRF Dokument-AI

Grundad dokument-Q&A för bostadsrättsföreningar. Varje källa verifieras mot dokumenttexten och kan öppnas på rätt PDF-sida med markering. Frågor som inte kan besvaras ur dokumenten ska avvisas i stället för att gissas.

- **MVP-status:** [docs/MVP-STATUS.md](docs/MVP-STATUS.md)

## Projektstruktur

Det här arbetsområdet består av två separata Git-repon:

- `backend/` och backendkontrakten i detta repo — FastAPI, auth, tenant-isolering, ingestion, retrieval, generering och verifierade citat.
- `brfv2-mockup/` — **den kanoniska och avsedda produktsidan**. Namnet är historiskt; den ska nu kopplas till backend och ersätta sin fiktiva datakälla successivt.

Rotens äldre React-app i `src/` är en fungerande backendkopplad prototyp, men den är inte den beslutade visuella slutprodukten. Nya UI-integrationer ska göras i `brfv2-mockup/`, inte genom att porta dess design tillbaka till rotens `src/`.

## MVP

Den första verkliga produktslingan är:

> Logga in → se föreningens dokument → ställ en fråga → få ett verifierat svar → öppna källan på rätt PDF-sida med markering.

För administratörer tillkommer uppladdning och radering av PDF-dokument.

Granskning, bevakningar och andra mockup-flöden är inte verkliga förrän de har motsvarande backendkontrakt. De får inte visa fiktiva data som om de kom från systemet.

## Start

Seedning och backend:

```bash
make demo-reset
make backend
```

Kanonisk frontend:

```bash
make frontend
```

Det startar `brfv2-mockup` på `http://localhost:5173/brfv2/`.

## Pilotmodell

Pilot-/produktionsgenerationen körs inte på Macen. Den körs med `gemma4:e12b` på Ubuntu-servern `agenntserver` med RTX 4070.

När backenden kör på Macen nås tjänsten normalt genom en SSH-tunnel:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Starta därefter pilotbackenden:

```bash
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
make backend-pilot
```

`127.0.0.1:8000` avser då den tunnlade tjänsten på Ubuntu-servern. Macens lokala `gemma4:e4b` används inte som fallback.

Se [docs/DEPLOY-SELFHOSTED-LLM.md](docs/DEPLOY-SELFHOSTED-LLM.md) för det fullständiga driftkontraktet.

## Backendarkitektur

```text
PDF → extract.py → chunker.py → indexer.py
    → answer.py → citations.py → API-kontrakt → brfv2-mockup
```

- **Spec:** [SPEC.md](SPEC.md)
- **Pilotkontrakt:** [SPEC-PILOT.md](SPEC-PILOT.md)
- **Demo:** [DEMO.md](DEMO.md)
- **Evidens:** [docs/evidence/](docs/evidence/)

## Kvalitet

```bash
make test
make test-isolation
make eval-fast
```

Backendens tester är offline och deterministiska. Självhostade evalkörningar ska uttryckligen peka på `agenntserver`-tjänsten och använda nätverksrevisionen.
