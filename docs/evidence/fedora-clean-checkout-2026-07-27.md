# Ren checkout på Fedora — XS-33

**Värd:** Fedora release 44 (Forty Four), kernel `7.1.5-200.fc44.x86_64`, x86_64,
14 GB RAM, AMD Barcelo-grafik (ingen CUDA).
**Datum:** 2026-07-27.
**Commit:** `b939d50` på `feat/pilot-e2e-acceptance`.
**Modelltjänst:** Gemma 4 12B via llama.cpp-container på `agenntserver`
(RTX 4070, drivrutin 580.173.02), nådd genom SSH-tunnel till `127.0.0.1:8000`.

## Vad som ändrades för att det skulle gå

Fyra saker gjorde att en ren klon inte gick att köra, och en fjärde gjorde att
maskinen inte överlevde försöket.

**Frontenden fanns inte i klonen.** `brfv2-mockup/` var ett nästlat,
gitignorerat repo. `git clone` gav ett träd där `make frontend` och `make build`
avbröt på en saknad katalog. Katalogen är nu vanliga spårade filer i samma repo;
den gamla historiken finns kvar på `migration/brfv2-mockup/*`.

**Uppsättningen fungerade inte som den var skriven.** `make test` gav
`uv: command not found`. `make setup` är nu hela vägen: installerar `uv` i
`~/.local/bin` om det saknas, synkar backend, förhämtar embedder-vikterna,
installerar `node_modules` för båda frontenderna och hämtar Playwrights
chromium. Inget sudo, inga systempaket, idempotent.

**Två rerank-tester föll på varje maskin som inte råkade ha vikterna cachade.**
Båda testade lokal cachestatus i stället för beteende. Det ena påstod att
`reranker_available()` är `True`; det testar nu det kontrakt namnet utlovar
(returnerar en bool, laddar aldrig modellen). Det andra injicerade en fejkad
scorer men lämnade `ask()`:s riktiga tillgänglighetsgrind stängd, så det krävde
3,8 GB torch- och CUDA-hjul för att testa ren ordningslogik. Omrankning är
avstängd som standard; inget av detta var bärande.

**Embeddern laddades om vid varje anrop.** `get_embedder()` byggde en ny
provider varje gång, och `Model2VecEmbedder` läser in ~1,5 GB vikter i sin
konstruktor. Den anropas per Store — alltså per förening — och dessutom inuti
`/api/health`, enbart för att läsa `.name`. Varje hälsokontroll läckte 1,5 GB.
En demo-backend samlade på sig nio laddningar och dödades av OOM-killern vid
**7,9 GB RSS**, vilket tog hela skrivbordssessionen med sig:

```
Jul 27 21:19:50 linuxtop kernel: Out of memory: Killed process 32409 (uvicorn)
  total-vm:15943116kB, anon-rss:7898276kB
```

Providern delas nu. Cachen är nycklad på `BRF_EMBEDDER` i stället för
`maxsize=1`, så byte av provider fortfarande slår igenom.

| Mätning på Fedora 44 | Före | Efter |
|---|---:|---:|
| 1 × `get_embedder()` | 1597 MB | 1597 MB |
| 10 × `get_embedder()` | ~15,6 GB | 1597 MB |
| Pilotbackend efter 10 `/api/health` | växande | 37 MB, platt |

## Körningar

Från en orörd `git clone`, med enbart `make setup` före:

| Kommando | Resultat |
|---|---|
| `make setup` | exit 0 |
| `make test` | 530 passed, 6 skipped |
| `make test-isolation` | 48 passed |
| `npm test` (brfv2-mockup) | 14 passed |
| `npm run lint` | exit 0 |
| `npm run build` | exit 0 |
| `npm run test:e2e` | 11 passed |
| `make demo` | exit 0, `mode=pilot`, `llm_provider=selfhosted`, `gemma4:e12b` |

Efter `make demo-reset` finns dataroten och korpus-tripwiren kör i stället för
att självskippa: **531 passed, 5 skipped**. Övriga fem skip är miljöberoende och
avsiktliga — `RUN_LLM_TESTS`, tesseract med svenskt språkpaket (3), och den
valfria rerank-extran.

## Live-verifiering mot Gemma 4 12B

Frågan *"Var har styrelsen sitt säte?"* gav ett grundat svar, "Styrelsen har
sitt säte i Göteborgs kommun.", med ett verifierat citat till
`Stadgar Brf Gjutformen 12.pdf` sida 1. Citatet öppnade rätt PDF på "Sida 1 av
3" med passagen markerad. Gränssnittet visade `Gemma 4 12B` och
`Self-hosted · agenntserver` från backendens `/api/health`, och svaret bar
`Gemma 4 12B · Self-hosted` från `/ask` — ingen hårdkodad etikett.
Kvalitetskontroll och dokumentchatt var spärrade med "Utanför pilotens
omfattning".

## Fedoraspecifika beroenden

- **Python 3.12.** Fedora 44 levererar 3.14 och backenden kräver `>=3.12,<3.13`.
  `uv` hämtar sin egen tolk; systempaketet `python3.12` behövs inte.
- **Playwright.** `npx playwright install-deps` kraschar på Fedora med
  `spawn apt-get ENOENT` och kan inte användas. Browsernedladdningen är portabel
  och Ubuntu-fallbackbygget (Chromium 149) kör felfritt.
- **tesseract.** OCR-testerna skippar utan `tesseract` och svenskt språkpaket.
  OCR ingår inte i pilotslingan.
- **git-identitet.** Var inte konfigurerad på maskinen; `user.name` och
  `user.email` sattes lokalt i repot.

## Externt beroende som inte kan reproduceras lokalt

Gemma 4 12B-tjänsten på `agenntserver`. Vid den här verifieringen låg den nere:
containern hade avslutats med kod 127 sedan NVIDIA-drivrutinen uppgraderats utan
omstart, så kernelmodulen (580.159.03) och userspace (580.173.02) inte matchade,
och den cachade CDI-specen pekade fortfarande på de gamla biblioteken.
Återställningen finns dokumenterad i
[../DEPLOY-SELFHOSTED-LLM.md](../DEPLOY-SELFHOSTED-LLM.md) under
"Felsökning: tjänsten svarar inte på 8000". Vikterna låg kvar orörda på värden.

## Kvarstående

`justify-content: safe center` i PDF-vyn kräver Chrome 93+, Firefox 63+ eller
Safari 15.4+. Äldre browsers faller tillbaka på vanlig centrering och får kvar
det klippta vänsterfältet vid smal bredd.
