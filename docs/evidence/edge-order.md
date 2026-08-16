# Kantordning mot sidordning — helarkiv, 2026-08-16

**Gren:** `feat/full-corpus-ask` · **n_ctx=65536** (drift) · embedder `model2vec` · frågor `q_name` / `q_seat` / `q_notice` · 10 PDF, `prefix_tokens=54539`, `bound=fits`, `threshold=None`

Utdragen är samma chunkar. Skillnaden är dokumentordningen i blocket. Inom ett dokument är sidordningen orörd. Citatkedjan orörd.

`page`: namn/sida (kontroll). `probe`: fryst sond + U-form, en gång per arkiv. `query`: samma U-form per fråga.

`page` och `probe` värmdes före fråga ett. `query` värmdes inte — prefixet byts per fråga.

## Per fall

| mode | qid | refused | cites | prompt_n | prompt_ms | cache_n | elapsed_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| page | q_name | no | 1 | 14 | 72 | 54552 | 2.401 |
| page | q_seat | no | 1 | 17 | 70 | 54552 | 2.050 |
| page | q_notice | no | 1 | 25 | 72 | 54552 | 4.254 |
| probe | q_name | no | 1 | 14 | 71 | 54552 | 2.408 |
| probe | q_seat | no | 1 | 17 | 70 | 54552 | 2.052 |
| probe | q_notice | no | 1 | 25 | 72 | 54552 | 5.776 |
| query | q_name | no | 1 | 54016 | 31225 | 550 | 34.128 |
| query | q_seat | no | 1 | 54019 | 31247 | 550 | 33.861 |
| query | q_notice | no | 1 | 54027 | 31298 | 550 | 37.114 |

`verified_to_refused` mot `page`: **0** för både `probe` och `query`. Ingen kvalitetsvinst på de här tre stadgarfrågorna. `query` betalar kall prefill varje gång (`cache_n=550`). `probe` behåller varm cache på fråga ett (`prompt_n` 14–25, `cache_n=54552`).

## Beslut

Behåll **frågeoberoende U-form (`probe`)** som produktordning. Den försämrar inte verifiering mot sidordning och dödar inte prefix-KV. Frågeberoende ordning skeppas inte.
