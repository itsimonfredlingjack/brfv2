# n_ctx-kostnad och nål — gemma4:e12b, 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT, llama.cpp `b9976`, Q4_K_XL, K/V q8_0, `--parallel 1` · **GPU:** RTX 4070 12282 MiB

Tillfällig `-c`-override; tracked `docker-compose.yml` orörd. `/props` n_ctx efter körning: **16384**.

Haystack: syntetisk `lorem`-fyllnad, kanarier vid token-djup 10/50/90 %. Träff = exakt kanariekod i completion. Inte `ask()`, inte citatgrind. Gemma 3 RULER används inte.

## Kostnad (varje n_ctx startade och höll)

KV reserveras vid last: `vram_full ≈ vram_loaded` inom ett givet `-c`. Kostnaden för större fönster syns som **lastad** VRAM, inte som delta last→prefill.

| n_ctx | started | stable | vram_loaded_mib | vram_full_mib | ram_loaded_mib | ram_full_mib | hay_tokens | Q1 prompt_n | Q1 prompt_ms | Q1 cache_n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16384 | yes | yes | 7756 | 7756 | 2178 | 2653 | 16123 | 16167 | 6862 | 0 |
| 32768 | yes | yes | 7894 | 7906 | 997 | 1241 | 32507 | 32551 | 15743 | 0 |
| 65536 | yes | yes | 8252 | 8264 | 1030 | 1464 | 65275 | 65319 | 39344 | 0 |

VRAM mot 16k: **+138 MiB** vid 32k, **+496 MiB** vid 64k. ~4 GiB ledigt även vid 64k. Prefill ungefär linjär: 6.9 s → 15.7 s → 39.3 s.

Q2/Q3 mot samma haystack (frågan sist): `prompt_n` 11–12, `cache_n` täcker prefixet (16156 / 32540 / 65308). Prefix-KV träffar. `GET /metrics` saknas på den här servern (`--metrics` inte på); `/slots` har ingen KV-bytestorlek. `kv_source=vram_delta` inom ett `-c` är ≈ 0 eftersom cachen redan är allokerad.

## Nål (avgör användbart n_ctx)

| n_ctx | 10% | 50% | 90% |
| --- | --- | --- | --- |
| 16384 | hit | miss | miss |
| 32768 | miss | miss | miss |
| 65536 | miss | miss | miss |

Token-djupen låg inom 0.001 av målet. Miss är inte felplacerad kanariefågel.

## Rekommendation

**`n_ctx=16384`**, regel `deepest_then_smallest`.

Inget fönster träffade 50 % eller 90 %. Bara 16384 träffade 10 %. Större fönster startade och höll, men den djupa nålen blev inte bättre — den försvann även på 10 % vid 32k och 64k. Att höja `-c` på den här värden, med den här modellen, ger extra prefill-tid och några hundra MiB VRAM utan mätbar vinst på fylld kontext.

Driftinställningen lämnas **16384**.
