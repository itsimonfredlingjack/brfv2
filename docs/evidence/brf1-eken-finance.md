# BRF-1: ränta, soliditet, två dokument — första körningen — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **embedder:** `model2vec:potion-multilingual-128M` · loopback · `scripts/eval_brf1_eken_finance.py`

Första treutfallsmätningen av de fyra frågorna som väntade på en årsredovisning. Låsta beskrivningar, inget räknetak, svarsdomaren i `ask()`. Fem körningar. Noll externa anslutningar. `fullCorpusTokenThreshold` återställd.

Två store:er, hållna isär:

| store | arkiv | årsredovisning | stadgar | frågor |
| --- | ---: | --- | --- | --- |
| `/tmp/brf1-store-eken` | 14 | Ekens egen, `scanned` (Print-to-PDF → OCR) | samma skanning som laptopen, `scanned` | alla fyra |
| `/tmp/brf1-store-with-ars` | 10 | annan förening, `digital` | saknas | bara ränta och soliditet |

Treutfallet är citat ur facithandling(arna), samma som BRF-1: `verifierat_i_facit` om alla krävda slags handlingar citeras, `vägrad` vid vägran eller noll citat, annars fel handling. Det är inte handklassad svarsriktighet.

Beskrivningsversion Eken `417397b9f07a`. Ingen omskrivning (`n_describe_calls=0`).

## Spannet

| arkiv | facit av N, fem körningar | fel handling | vägrad |
| --- | --- | --- | --- |
| Eken, OCR-årsredovisning + OCR-stadgar (4 frågor) | **3–3** (3, 3, 3, 3, 3) | 0–0 | 1–1 |
| digital årsredovisning, annan förening (2 frågor) | **0–0** (0, 0, 0, 0, 0) | 0–0 | 2–2 |

Gällande Eken: **3 facit av 4** över fem körningar. Spannet är 3–3. Den enda vägran är soliditet.

## Per fall, Eken (OCR)

| fall | facit | fel handling | vägran | utfall | grind | packat | prefix |
| --- | ---: | ---: | ---: | --- | --- | --- | ---: |
| ränta | 5 | 0 | 0 | facit ×5 | — | årsredovisning | 9 522 |
| soliditet | 0 | 0 | 5 | vägrad ×5 | `numeric_grounding_failed` | årsredovisning | 9 522 |
| fond mot stadgar + årsredovisning | 5 | 0 | 0 | facit ×5 | — | revision + stadgar + årsredovisning | 20 199 |
| kallelse mot stadgar + stämma | 5 | 0 | 0 | facit ×5 | — | samma tre | 20 199 |

`n_packed` **1–3** av 14. Tokentaket kapade inget. Tvådokumentsfrågorna citerade stadgar **och** årsredovisning i alla fem — båda `source=scanned`. Revisionsberättelsen packades som tredje handling (digital) men citerades inte.

Ränta vilar på OCR-textlagret av Print-to-PDF. Soliditet packade rätt handling och föll i den numeriska grinden (`2025` i reparationsförsöket — årtal, inte nyckeltal). Tvådokumentsfrågorna vilar på OCR på båda facithandlingarna.

I OCR-texten fanns `soliditet` två gånger och `ränte*` sju. Stadgarna hade `kallelsetid` en gång, inte strängen `underhållsfond` / `avsättning`; fondfrågan citerade likväl båda handlingarna. Treutfallet säger inte att beloppet stämde.

## Per fall, digital årsredovisning (annan förening)

| fall | facit | fel handling | vägran | grind (körning 1 / 2–5) | packat | prefix |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| ränta | 0 | 0 | 5 | `numeric_grounding_failed` / `grounding_failed` | årsredovisning | 30 951 |
| soliditet | 0 | 0 | 5 | `numeric_grounding_failed` | årsredovisning | 30 951 |

Urvalet tog rätt handling. Svaret visades inte. Det här är **inte** OCR-isolering av samma dokument: annan förening, annat räkenskapsår, born-digital textlager. Det visar att den numeriska grinden fäller ränta/soliditet även utan OCR.

## Vad som inte är mätt

- Samma årsredovisning som skanning och som digitalt textlager. Ekens rapport *är* Print-to-PDF; den andra föreningens rapport är en annan fil.
- Samma stadgar som skanning och digitalt födda. Identisk SHA-256, båda utan textlager (`docs/evidence/brf1-eken-egen.md`).
- Retrievalvägen. Bara dokumentvägen.
- Handklassad svarsriktighet på de tre facit-fallen.

Elva-fallsmåttet 8–8 är orört.
