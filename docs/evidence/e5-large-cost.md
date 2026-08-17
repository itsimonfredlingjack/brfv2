# Kostnad för byte till multilingual-e5-large — inte byggt — 2026-08-17

**Host:** agenntserver. Ingen produktändring. Embeddern är fortfarande `minishlab/potion-multilingual-128M` (statisk model2vec, 256 dimensioner). Siffrorna nedan är vad ett byte till `intfloat/multilingual-e5-large` skulle kosta. Modellen laddades inte. Inget index byggdes om.

Alla slutsatser om att embeddings inte hjälper vilar på potion. Nästa riktiga mätning är retrieval-effekten på niarkivsinstrumentet (9 arkiv, 105 frågor, 863 rader), inte på de elva BRF-1-fallen. Den här filen är bara kostnaden.

## Installationsstorlek

| | potion-multilingual-128M (nu) | multilingual-e5-large |
| --- | ---: | ---: |
| vikter `model.safetensors` | 512 361 560 B (488,6 MiB) | 2 239 611 368 B (2,09 GiB) |
| tokenizer | 18 616 131 B (`tokenizer.json` i desktoppinnen) | 17 082 660 + 5 069 051 B (`tokenizer.json` + `sentencepiece.bpe.model`) |
| arkitektur | statisk model2vec, inget torch | 24 lager, 1024 dim, ~560 M parametrar (XLM-R large) |
| Python-runtime i default-payload | `model2vec` | `sentence-transformers` → `torch` + `transformers` |

`torch` 2.13.0 i `backend/uv.lock` (extra `rerank` / `entailment`, inte default): linux x86_64-hjulet är 526 605 292 B. På Linux drar samma extra CUDA-stack, bland annat `nvidia-cudnn-cu13` 366 173 588 B. Desktop-RPM:en skeppar ingen av dem.

Nuvarande Fedora-RPM: **574 860 579 B**, varav potionvikterna är merparten. Att baka in e5-vikterna ensamma skulle lägga ~1,7 GiB. Torch ovanpå det — CPU-hjul eller CUDA-stack — är ytterligare hundratals MiB till flera GiB. Det är inte ett drop-in-byte i samma paket.

## Minne

| | potion | e5-large |
| --- | ---: | ---: |
| vikter i RAM | ~0,5 GiB | ~2,2 GiB fp32; artikeln anger ~2,2 GiB fp16 |
| indexvektorer, BRF-1 (130 chunks) | 130 × 256 × 4 B ≈ 0,13 MiB | 130 × 1024 × 4 B ≈ 0,51 MiB |
| indexvektorer, Eken (234 chunks) | ≈ 0,23 MiB | ≈ 0,91 MiB |

Indexet är försumbart. Processminnet är modellvikterna. Desktopappen kör embeddern i samma process som API:t; den självhostade LLM:en ligger utanför. e5-large tar ungefär fyra potionvikter i RAM innan någon chunk kodats.

## Indexeringstid

Inte mätt med e5-large (modellen finns inte i cachen, `HF_HUB_OFFLINE=1`).

Potion på den här hosten, 130 texter à ~400 tecken: **0,01 s** (~13 000 chunks/s). `HybridIndex.build` kodar alla chunks vid ingest.

e5-large är en 24-lagers transformer. Publicerad genomströmning: ~30 queries/s på V100, batch 1. CPU-laptop är långsammare, typiskt sekunder till någon minut för 130–234 chunks mot potionens millisekunder. Exakt tal kräver att modellen laddas; det är nästa mätning, inte den här.

## Paketerad skrivbordsapp utan nätverk

Ja, **om** vikterna bakas in och sökvägen pinnas, samma mönster som `BRF_MODEL2VEC_PATH` + `HF_HUB_OFFLINE=1`. Desktopappen når inte huggingface.co i dag.

Nej som drop-in:

- Det finns ingen e5-pin i `ops/pins.json`. Bara potion, en exakt revision och en fillista.
- Default-beroendena har inte torch. `sentence-transformers` är extra `rerank`.
- `sentence-transformers` laddar från Hugging Face vid första anropet om ingen lokal sökväg sätts. Det bryter offlinekontraktet.
- RPM-storleken och minnet ovan.

Slutsatsen att embeddings inte hjälper är alltså bunden till en statisk 256-dimensionell modell utan transformer. Ett byte är möjligt offline, men det är ett nytt paket, inte en miljövariabel.

Källor: Hugging Face `intfloat/multilingual-e5-large` (HEAD Content-Length 2026-08-17), `ops/pins.json`, `docs/evidence/uppgifter-installed-desktop-acceptance.json` (RPM 574 860 579 B), `backend/uv.lock` torch 2.13.0, lokal potion-encode på agenntserver. Chunkantal från `/tmp/brf1-store` (9 handlingar, 130 chunks) och `/tmp/brf1-store-eken` (14 handlingar, 234 chunks).
