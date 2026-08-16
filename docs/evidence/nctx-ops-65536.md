# Drift: helarkivvägen — 2026-08-16

Vad som faktiskt körs efter merge till `main`. Läs det här, inte de tillfälliga override-körningarna, om du undrar varför arkivet plötsligt ryms.

**Host:** agenntserver · **Modell:** Gemma 4 12B IT (llama.cpp) · **Embedder:** `model2vec:potion-multilingual-128M`

## n_ctx = 65536

Trackad fil: `/home/simon/llama-cpp/docker-compose.yml`, `-c 65536` (inte en gitignorerad override).

`GET http://127.0.0.1:8000/props` → `default_generation_settings.n_ctx = 65536`.

Det är inte en kvalitetsgräns. Occupancy-nålen vid 65536 hade samma mönster som 16384 (10/90 träff, 50 miss). VRAM ~8266 MiB med ~4 GiB ledigt. 10-PDF-arkivet ryms: `prefix_tokens=54539` under fönstret `65536 − 512 − 1800 = 63224`.

Tidigare 16384 gav effektivt tak 14072. Därför eldade helarkivvägen aldrig på föreningsarkivet förrän den här ändringen.

## Tröskeln är inte längre en andra gräns

`fullCorpusTokenThreshold` default är `None`. Den enda gränsen som alltid finns är `n_ctx − 512 − (maxResponseLength + 600)`.

| Värde | Betydelse |
| --- | --- |
| `None` | Bara fönstertaket. |
| `0` | Tvinga retrieval (före/efter på samma commit). |
| `N > 0` | Valfritt extra tak på **prefix_tokens**, bara om det är tajtare än fönstret. |

`chunk_token_sum` är en metrik, inte en grind. Den gamla defaulten 32000 band arkivet (`chunk_token_sum=48923`) även när 65536 hade plats. En befintlig `settings.json` med exakt `32000` migreras till `None` vid inläsning (INFO-logg). Andra tal, inklusive `0`, lämnas orörda.

## Förvärmning

Kall prefill på det här arkivet är ~30,7 s. Den kostnaden hör till ingestion, inte fråga ett. Efter `_rebuild` (uppladdning, radering, om-OCR, omchunkning) kör en bakgrundstråd samma cachebara prefix mot modellen (`max_tokens=1`, svaret slängs). `BRF_PREFIX_WARMUP=0` stänger av den.

Citatkedjan och grinden är orörda. Bara *när* prefillen sker.

## Live-kontroll före merge

10 PDF, sidordning, `threshold=None`, `n_ctx=65536`.

| Steg | path | bound | prompt_n | prompt_ms | cache_n | elapsed_s |
| --- | --- | --- | --- | --- | --- | --- |
| förvärmning | — | fits | 517 | 454 | 54045 | 1.65 |
| q_name (första frågan) | full_corpus | fits | 14 | 69 | 54552 | 2.332 |

`prefix_tokens=54539`, `chunk_token_sum=48923`, `order=page`, 1 citat, inte vägrad. Första frågan efter värmning är varm (`prompt_n` är frågetokens, `cache_n` är prefixet). Kall prefill hade varit `prompt_n≈54016` och `cache_n=550`.

Förvärmningen själv var också varm på den här hosten (`cache_n=54045`): llama.cpp höll fortfarande prefix-KV från tidigare sidordningskörningar samma dag. Det är inte en 30 s kall mätning; det är belägg att fråga ett träffar cachen när prefixet redan är inne.

Offlinesvit: **1400 passed**, 62 skipped.

## Utdragsordning

Produkt: dokumentnamn, sedan sida. U-form bakom `store._full_corpus_order` (`probe`/`query`) för `scripts/live_edge_order.py` — av i drift. Tre stadgarfrågor visade ingen kvalitetsvinst mot sidordning; frågeberoende ordning dödade cachen. Prövad mot R2, R6 och R7b med `verifierat_i_facit`: återställde R2, inte R6, R7b nådde inte facit. Stannar bakom flaggan. Se `docs/evidence/edge-order.md` och `docs/evidence/brf1-full-corpus.md`.

## Överflödigt på helarkivvägen, kvar på retrieval

När arkivet ryms hoppar `ask` och `ask_planned` förbi retrievalkedjan. Det här körs alltså inte på den vägen, men **tas inte bort** — det behövs så fort prefixet inte ryms:

- **Planeraren** (`plan_query` / `ask_planned` fan-out). Kortsluts när `decide_fit` säger `fits`.
- **Omrankning** (`rerank_chunks`). Körs bara på retrievalträffen efter att helarkiv- och dokumentvägen har missat.
- **Tabell-legender** (`append_linked_table_legends`). Samma sak: retrieval och den planerade evidensvägen, inte helarkivets `_synthesize`.

Dokumentvägen (gate B) är också en genväg förbi de tre, så länge toppdokumentet ryms.
