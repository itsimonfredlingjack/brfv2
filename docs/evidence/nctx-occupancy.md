# Beläggning mot längd — gemma4:e12b, 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT, llama.cpp `b9976`, Q4_K_XL · **GPU:** RTX 4070 12282 MiB

Fylld-fönster-provet (`docs/evidence/nctx-cost.md`) mätte mättnad vid tre storlekar. Det här provet håller `-c 65536` fast och varierar höstacken. Filler: syntetisk årsredovisningsstruktur (`Avsnitt Forvaltning|Resultat|Balans|Noter` + cyklande ordförråd), inte `lorem`, inte förenings-PDF. Träff = exakt kanariekod i completion.

`/props` n_ctx efter körning: **16384**. Tracked compose orörd. 65536 startade och höll. `vram_loaded=8252` MiB, `vram_full=8266` MiB, ~4 GiB ledigt.

## Träff per (höstack, djup) vid n_ctx=65536

| hay_tokens | 10% | 50% | 90% | Q1 prompt_n | Q1 prompt_ms | Q2 cache_n |
| --- | --- | --- | --- | --- | --- | --- |
| 7996 | hit | miss | hit | 8040 | 3269 | 8029 |
| 16003 | hit | miss | hit | 16030 | 6867 | 16036 |
| 31993 | hit | miss | hit | 32020 | 15484 | 32026 |
| 48000 | hit | miss | hit | 48027 | 26219 | 48033 |
| 62000 | hit | miss | hit | 62027 | 37248 | 62033 |

Token-djupen låg på 0.100 / 0.500 / 0.900. Q2/Q3 `prompt_n` 11–12 — prefix-KV träffar inom en höstack. Mellan höstackar ingen kollaps (`cache_n≈17`).

## 16k-kontroll vid n_ctx=16384 (samma strukturerade filler)

| fönster | höstack | 10% | 50% | 90% |
| --- | --- | --- | --- | --- |
| 65536 | 16003 | hit | miss | hit |
| 16384 | 16003 | hit | miss | hit |
| 16384 (gammalt `lorem`, fyllt) | ~16123 | hit | miss | **miss** |

16k i 64k och 16k i 16k är **identiska** med strukturerad filler. Beläggning mot längd, samma filler: occupancy förklarar **inte** 90 %-träffen. Det gamla 90 %-missen vid fyllt 16k-fönster följde `lorem`, inte fönsterstorleken.

`explains_vs_lorem=true` (ogiltiggör den gamla nåltabellen som kvalitetsmått). `explains_vs_structured_control=false` (occupancy är inte orsaken).

50 %-missen (MID) är densamma från 8k till 62k. Det är lost-in-the-middle, inte mättnad och inte längd.

## Helarkiv-grind

48k-höstacken träffade 10 % och 90 %. **`holds_for_archive=true`** (`48k_hit`). Kall prefill vid arkivstorlek är ~26 s (48k) till ~37 s (62k); därefter `prompt_n≈12`. Det är den halvminut som sedan cachas.

Den gamla rekommendationen `n_ctx=16384` från fylld `lorem`-nål är **ogiltig som kvalitetsutslag**. Kostnadssiffrorna i `nctx-cost.md` (VRAM, prefill, restore) står kvar. Driftfilen lämnas 16384 tills helarkivlive är klar; mätningen höjer `-c` tillfälligt.
