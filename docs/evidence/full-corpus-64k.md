# Helarkivväg mot retrieval vid n_ctx=65536 — 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Modell:** Gemma 4 12B IT · tillfällig `-c 65536` · restore `/props` **16384** · embedder `model2vec:potion-multilingual-128M`

Gate A eldade på föreningens 10 PDF:er för första gången. `chunk_tokens=48923`, `prefix_tokens=54539`, `bound=fits` vid `threshold=100000` (produktens default 32000 skulle fortfarande bundit på tröskeln; den knoppen ändrades inte i git). Retrieval-före: `threshold=0`.

Headline per fall: **`verified_to_refused=0`**, `refused_to_verified=0`. Alla tre efter-vägarna `full_corpus`.

| qid | retrieval refused | full_corpus refused | cites r/f | retrieval s | full_corpus s | retrieval prompt_n | full_corpus prompt_n | full_corpus cache_n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q_name | no | no | 1/1 | 3.184 | 33.272 | 3126 | 54016 | 550 |
| q_seat | no | no | 1/1 | 2.734 | 2.032 | 2421 | 17 | 54552 |
| q_notice | no | no | 1/1 | 5.314 | 4.275 | 2480 | 25 | 54552 |

Kall prefill ~30.7 s (`prompt_ms=30676`). Fråga två och tre: `prompt_n` 17 och 25, `prompt_ms` ~70 ms, `cache_n=54552`. Prefix-KV är poängen med vägen och den höll.

Frågorna är stadgar-formade (namn, säte, kallelsetid). Retrieval verifierade dem också — det här är inte ett retrieval-miss-experiment. Det är evidens att arkivet **rymmer**, att vägen **eldar**, och att den andra frågan är billig. Ränte- och soliditetsfrågor väntar på en årsredovisning som inte finns i de 10 PDF:erna.
