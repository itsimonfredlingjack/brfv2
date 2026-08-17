# BRF-1: numerikgrind, årtal och enhet i kolumnrubrik — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **embedder:** `model2vec:potion-multilingual-128M` · loopback · `scripts/eval_brf1_locked.py` · `scripts/eval_brf1_eken_finance.py --digital-ars`

Två namngivna normaliseringsfel, båda fällde avskrivna svar. Grinden är oförändrad på substans: transponerade siffror, procent mot ett rent antal, och påhittade årtal utan rubrik fälls fortfarande. Fem körningar. Låset `97b4e7bfc71f` på de elva fallen. Eken-låset `417397b9f07a`. Noll externa anslutningar. `n_describe_calls=0`.

## Vad som ändrades

1. Ett kalenderår i svaret (1900–2100, inte belopp som `2025 kr`) kräver inte eget citatstöd om samma årtal redan står i frågan, eller om det är en kolumnrubrik på den citerade sidan — en rad med minst två årtal.
2. `55 %` i prosa matchar en tabellcell `55` när procenttecknet sitter i citatets kolumnrubrik (`Soliditet¹, % 55`). `8 %` mot `8 st` utan procentmarkör i citatet fälls fortfarande.

## Elva fallen

**8 → 7 är inte en regression av den här grindändringen.** De två talen kommer från körningar som skiljer sig i mer än en sak, och fallet som flyttade hade redan flyttat innan normaliseringen fanns.

| | `brf1-locked-pack` (`df6f7f8`) | `brf1-refusal-help` (`af54cef`, en körning) | den här filen (fem körningar) |
| --- | ---: | ---: | ---: |
| produkt | låsta beskrivningar, inget räknetak | + vägran med sortsmening | + olästa namn + den här normaliseringen |
| numerikgrind | gammal | gammal | ny |
| facit av 11 | **8–8** | (ej femkörning) | **7–7** |
| R6 | facit ×5 | `grounding_failed` | `grounding_failed` ×5 |

R6 är det enda fallet som går från facit till icke-facit mellan `locked-pack` och den här körningen. Utfallet nu: vägrad, `grounding_failed`, i alla fem. Facit E låg i paketet (C, D, E, F; prefix 17 883). Loggen har ingen numerisk reparation. Det är citatverifiering, inte numerikgrinden.

Samma `grounding_failed` syns redan i `brf1-refusal-help.md`, en körning mot `af54cef`, **före** den här normaliseringen. Genereringstemperaturen är 0. Mellan `df6f7f8` och `af54cef` ändrades bara `insufficient_data`-prosan — den grenen nås inte när citatverifieringen faller. De två femkörningarna är alltså inte armar av samma experiment. Att lägga 8 och 7 i samma tabellkolumn blandar tre ändringar.

Elva frågor mot ett arkiv är riktningsgivande mot niarkivsinstrumentet (9 arkiv, 105 frågor, 863 rader). R6 säger ingenting om protokollcellen 13 % mot slumpens 34 %.

R1 är fortfarande `citation_contradicted`. R7/R7b är fortfarande `insufficient_data`. Inget fall gick från vägran till visat svar via den mildare formateringen.

R4 träffar fortfarande grinden på `2024` och repareras — frågan innehåller inget årtal, och sophämtningsavtalet är inte en årkolumn. Svaret visades i alla fem. Det är inte den namngivna Eken-buggen.

Inget `verifierat_i_fel_handling`.

## Ränta och soliditet

| arkiv | före | efter |
| --- | ---: | ---: |
| Eken OCR, 4 frågor | **3–3** (soliditet vägrad ×5) | **4–4** (soliditet facit ×5) |
| digital årsredovisning, 2 frågor | **0–0** (båda vägrade ×5) | **1–1** (soliditet facit ×5, ränta vägrad ×5) |

Soliditet på båda rapporterna var de två namngivna buggarna. De släpps igenom nu. Ränta på Eken var redan facit och är det fortfarande. Ränta på den digitala rapporten vägras fortfarande: `numeric_grounding_failed` på `2024` i körning 1, `grounding_failed` i körning 2–5. Samma mönster som före fixen. Inget svar som borde fällas släpptes igenom där.

Fel handling: 0 på båda arkiven.

## Substans som fortfarande fälls

Enhetstester, inte live-modellen: transponerade siffror; `8 %` mot `8 st`; `2019` när rubriken är `2025 2024 2023 2022`; `2025 kr` även när `2025` står i frågan.

Körbar mätning: `uv run python -m scripts.eval_brf1_locked` och `uv run python -m scripts.eval_brf1_eken_finance --digital-ars` från `backend/`. Tester: `uv run pytest -q tests/test_numeric_grounding.py tests/test_answer.py::TestNumericGroundingGate`.
