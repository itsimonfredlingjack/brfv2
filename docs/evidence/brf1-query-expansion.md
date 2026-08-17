# BRF-1: doc2query och query2doc, var för sig — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `6a86c5a` · loopback · `scripts/eval_brf1_query_expansion.py`

Enkörning. Ingen `ask()`. Ingen ny svarsväg. Låsta beskrivningar version `97b4e7bfc71f`. `n_describe_calls=0`. Noll externa anslutningar. Genererade frågor och stycken ligger i `backend/out/brf1-query-expansion/` (gitignorerad); den här filen har bara bokstäver, rank och tokenprober mot frågans ord.

Samma elva fall, samma nio handlingar, samma tokenizer som indexet. BM25 är en post per handling (all text), utan embedding och utan query-expansion — samma mätning som gav **0 / 11** i `docs/evidence/brf1-doc-select.md`.

Beskrivningsurvalet är isolerat **en** handling, JSON `{"document": "X"}`, bara låst beskrivning (inte titel). Det är samma protokoll som **7 / 11** i `docs/evidence/brf1-doc-descriptions.md`, men texterna är låset, inte den äldre cachen. Räkningen 7/11 återkom; fallen är inte desamma.

---

## Sammanfattning

| kanal | före | efter |
| --- | ---: | ---: |
| BM25 dokumentträff, doc2query | **0 / 11** | **2 / 11** |
| BM25 dokumentträff, query2doc | **0 / 11** | **0 / 11** |
| beskrivningsurval, query2doc | **7 / 11** | **7 / 11** |

Kombinerad BM25 kördes inte: query2doc gav noll dokumentträffar. Blandning hade inte gått att läsa. Query2doc-grenen är stängd: stycket måste använda handlingens ord, och de orden finns bara i filen. Det gäller varje frågesidesomskrivning.

doc2query: 20 frågor per handling (9×20), index **15019 → 16584** token (**+1565**, +10,4 %).

---

## 1. doc2query — frågelager i indexet

Gemma fick handlingens text och bad om 20 frågor en styrelseledamot skulle kunna ställa, på vardagliga ord. Frågorna skrevs till BM25-posten vid sidan av texten. Referens: Nogueira & Lin, 40 prediktioner per MS MARCO-passage; här 20 per handling, generator bytt till Gemma, ingen träning.

### Per handling

| | frågor | token före | token efter | tillägg |
| --- | ---: | ---: | ---: | ---: |
| A | 20 | 2034 | 2213 | 179 |
| B | 20 | 2116 | 2293 | 177 |
| C | 20 | 624 | 802 | 178 |
| D | 20 | 3200 | 3409 | 209 |
| E | 20 | 543 | 712 | 169 |
| F | 20 | 1292 | 1467 | 175 |
| G | 20 | 596 | 750 | 154 |
| H | 20 | 1144 | 1314 | 170 |
| I | 20 | 3470 | 3624 | 154 |
| **summa** | **180** | **15019** | **16584** | **1565** |

### Per fall, BM25 topp-1

| fall | facit | före topp (rank) | efter topp (rank) |
| --- | --- | --- | --- |
| R1 | G | D (2) | D (3) |
| R2 | G | H (7) | H (4) |
| R3 | G | D (2) | **G (1)** |
| R4 | E | B (5) | B (6) |
| R5 | E | C (5) | C (3) |
| R6 | E | C (9) | **E (1)** |
| R7 | E | H (7) | H (6) |
| R8 | E | H (6) | H (9) |
| R3b | G | D (3) | D (2) |
| R5b | E | B (4) | B (4) |
| R7b | E | D (9) | H (5) |

**0 → 2.** R3 och R6. R3 är parkeringsfrågan med ordet *parkering* i frågan. R6 är ett av de fem hårda fallen.

R8 sjönk (6 → 9). R1 sjönk (2 → 3). Tillägget är inte gratis.

### De fem hårda, tokenprober (frågans ord i E:s respektive G:s *genererade frågor*)

| fall | facit | frågans pekord i facittexten | samma ord i facithandlingens frågelager |
| --- | --- | --- | --- |
| R5 | E | extra nej, avgift nej, stena ja, fakturorna nej | extra nej, avgift nej, stena ja, **fakturorna ja** |
| R6 | E | kostnaderna nej, föreningen nej, betala nej | **kostnaderna ja**, föreningen nej, **betala ja** |
| R7 | E | stena ja, höjer nej, priset nej | stena ja, höjer nej, priset nej |
| R3b | G | kostnaden nej, bil nej, skada ja, gården nej | kostnaden nej, **bil nej**, skada nej, **gården nej** |
| R7b | E | leverantören nej, höja nej, priset nej, meddela nej | alla fyra nej |

R6 stängdes för att frågelagret införde *kostnaderna* och *betala*, som inte finns i E:s brödtext. R5 fick *fakturorna* men inte *avgift*; rank 5 → 3, fortfarande C överst. R7 och R7b fick inga av pekorden *höjer* / *priset* / *leverantören*.

**R3b stängdes inte.** G:s tjugo frågor innehåller varken *bil* eller *gården*. Facittexten har *skada* men inte de två pekorden; frågelagret återinförde inte ens *skada*. Rank 3 → 2, D kvar överst. Det är inte det starkaste beviset mekanismen kan ge. Det är evidens att Gemma, given G, inte hittar kopplingen gården/bil → parkering.

**Öppen fråga, inte åtgärd.** Gemma fick parkeringsavtalet och genererade tjugo frågor som inte innehöll *bil*, *gården* eller ens *skada*. Kopplingen gården och bil → parkering gjorde den inte. Det är en gräns hos en 12B-modell, och en av få platser i projektet där modellstorlek plausibelt spelar roll. Lämna det öppet till en större modell finns att mäta mot — inte att gissa från den här körningen.

---

## 2. Query2doc — frågan skrivs om till handlingsspråk

Gemma skrev ett kort hypotetiskt svarsstycke. BM25: frågan × 5 + stycket (Wang et al. 2023, `n=5`; QueryGym `query_repeat_plus_generated`). Beskrivningsurval: frågan + stycket en gång, så urvalsprompten inte drunknar i upprepning. Ursprungligt index, låsta beskrivningar. Ingen träning.

### BM25, per fall

| fall | facit | före topp (rank) | efter topp (rank) |
| --- | --- | --- | --- |
| R1 | G | D (2) | D (2) |
| R2 | G | H (7) | H (5) |
| R3 | G | D (2) | D (2) |
| R4 | E | B (5) | B (5) |
| R5 | E | C (5) | C (7) |
| R6 | E | C (9) | C (9) |
| R7 | E | H (7) | H (6) |
| R8 | E | H (6) | H (6) |
| R3b | G | D (3) | D (4) |
| R5b | E | B (4) | B (4) |
| R7b | E | D (9) | D (8) |

**0 → 0.** Inget fall vände. R3b och R5 blev sämre.

Stycket för R3b innehöll *gården* och *skada*, inte *bil*. *gården* finns i ingen handling. ×5 på ursprungsfrågan förstärker *bil*, som sitter i D. D vinner fortfarande.

Stycket för R7b innehöll *leverantören*, *höja*, *priset*. De orden finns inte i E. Expansionen pekar mot handlingar som har dem, inte mot facit.

**Grenen är stängd, och skälet går att förklara.** Query2doc — och varje annan omskrivning på frågesidan — kräver att det genererade stycket använder *handlingens* ord. De orden finns bara i filen. Modellen som skriver stycket ser frågan, inte handlingen, och kan därför inte känna till dem. Gemma skrev frågans ord (*gården*, *leverantören*, *höja priset*). Expansionen pekar mot handlingar som redan har de orden, eller mot ingen. Det är inte ett dåligt utfall som skulle vända med en annan prompt. Det är att metoden frågar efter information som inte finns i indata. HyDE, query rewrite och query2doc faller på samma ställe här.

### Beskrivningsurval, per fall

Låsta texter, en handling. Historiska 7/11 (`brf1-doc-descriptions.md`) hade andra texter: R3b missade, R5 och R7 träffade. Den här baslinjen är låset.

| fall | facit | före | query2doc |
| --- | --- | --- | --- |
| R1 | G | **G** | **G** |
| R2 | G | **G** | **G** |
| R3 | G | **G** | **G** |
| R4 | E | **E** | **E** |
| R5 | E | C | B |
| R6 | E | D | I |
| R7 | E | H | H |
| R8 | E | **E** | **E** |
| R3b | G | **G** | **G** |
| R5b | E | **E** | **E** |
| R7b | E | H | H |

**7 → 7.** Samma träffar. R5 och R6 bytte fel handling (C→B, D→I). R3b var redan G i baslinjen — låsets G-text nämner fordon och skador, den äldre cachen gjorde det inte. Query2doc stängde inte R3b; det var redan stängt på den kanalen.

---

## 3. Tillsammans

Inte kört. Query2doc gav noll BM25-träffar. doc2query:s två träffar (R3, R6) kan inte adderas med en nollkanal.

---

## De fem hårda, tre kanaler

| fall | BM25 före | doc2query | query2doc BM25 | desc före | desc query2doc |
| --- | --- | --- | --- | --- | --- |
| R5 | C | C (rank 5→3) | C (5→7) | C | B |
| R6 | C | **E** | C | D | I |
| R7 | H | H | H | H | H |
| R3b | D | D (3→2) | D (3→4) | **G** | **G** |
| R7b | D | H (9→5) | D | H | H |

En ny BM25-träff bland de fem: **R6 via doc2query**. R3b:s BM25-glapp lever. Beskrivningsurvalet på låset hade redan R3b; query2doc ändrade det inte.

---

## Invarianter

- `ask()` anropades inte. `app/answer.py` rördes inte.
- Beskrivningar låsta `97b4e7bfc71f`. Ingen omskrivning.
- Trafik bara loopback (`127.0.0.1`, `::1`, `localhost`).
- Inget ur handlingarna eller de genererade frågorna/styckena committat.

Körbar mätning: `uv run python -m scripts.eval_brf1_query_expansion` från `backend/`. Tester: `uv run pytest -q tests/test_query_expansion.py`.
