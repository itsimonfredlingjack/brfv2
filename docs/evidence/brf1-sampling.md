# BRF-1: sampling i `ask()` mot llama.cpp — 2026-08-16

Innan någon default ändrades. Ingen produktändring.

## Vad `ask()` skickar

`OpenAICompatProvider.complete()` (`backend/app/llm.py`) lägger i varje request:

| fält | värde |
| --- | --- |
| `temperature` | **0** |
| `top_p` | skickas inte |
| `seed` | skickas inte |
| `max_tokens` | ja |
| `response_format` | `json_object` |
| `reasoning_effort` | `none` |
| `cache_prompt` | `true` |

Temperatur noll är explicit i payloaden. Den är inte beroende av serverns default.

## Vad servern har som default

`llama-server` i `/home/simon/llama-cpp/docker-compose.yml`: `--temp 1.0 --top-p 0.95 --top-k 64`.

`GET /props` `default_generation_settings.params`:

| fält | värde |
| --- | --- |
| `temperature` | 1.0 |
| `top_p` | ≈ 0,95 |
| `top_k` | 64 |
| `min_p` | ≈ 0,05 |
| `seed` | 4294967295 (unset / slump) |

Utelämnat fält = serverdefault. Skickat fält vinner.

## Vad som faktiskt låg i sloten efter ett `ask()`-format anrop

Ett kort `/v1/chat/completions` med samma fält som `complete()` (temperature 0, ingen top_p, ingen seed). Därefter `GET /slots`:

| fält | i sloten |
| --- | --- |
| `temperature` | **0,0** — requesten vann över `--temp 1.0` |
| `top_p` | ≈ 0,95 — serverdefault, inte skickad |
| `top_k` | 64 — serverdefault |
| `seed` | 4294967295 — fortfarande unset |

Temperaturen mot llama.cpp i `ask()` är alltså redan noll. Femkörningen i `docs/evidence/brf1-variance.md` *är* mätningen vid temperature 0: dokumentvägen 6–6 av 11, retrieval 5–5. Det finns ingen andra matris att köra för punkt 3 i mätuppdraget.

Vid temperature 0 är avkodningen girig. Kvarvarande `top_p` ska inte byta argmax. Om femkörningen ändå rör sig är det inte temperaturen.

## Produktfrågan

Ska ett citatbundet svar vara deterministiskt? Requesten är redan greedy. Defaulten rörs inte i den här körningen. Om svaret ändå driver är det GPU, KV eller Gemma — inte `--temp 1.0`.
