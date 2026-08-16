# BRF-1: handlingsval isolerat — 2026-08-16

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `25e40d7` · **embedder:** `model2vec:potion-multilingual-128M`

> **Enkörning.** 1/11, 0/11 och 6/11 är en körning per fall. Spann över fem `ask()`-körningar: `docs/evidence/brf1-variance.md`.

Samma elva fall och samma nio handlingar (130 chunkar) som `docs/evidence/brf1-full-corpus.md`. Ingen ny svarsväg, ingen grind, `ask()` anropades inte, fan-out rördes inte, `r01` kördes inte. Trafik bara loopback.

Frågan är: kan systemet *namnge* facithandlingen, utan att besvara frågan?

Tre oberoende metoder mot samma store:

1. **Hämtning.** `index.search` brett, `score_documents`: dokumentet med högst max fused score. Produktens dokumentrankning.
2. **Lexikalt.** BM25 över nio dokument (all text i handlingen som en post). Ingen embedding, ingen query-expansion.
3. **Modell.** Ett anrop per fall. Lista med titel och kort strukturbeskrivning (sidantal + avsnittsrubriker), inte brödtext. JSON `{"document": "X"}`. Inget citat.

## Träffkvot

| metod | träff |
| --- | ---: |
| hämtning (max fused) | **1 / 11** |
| lexikalt (BM25 dokument) | **0 / 11** |
| modell (katalog) | **6 / 11** |
| minst en av tre | **6 / 11** |

Unionen är modellens sex träffar. Hämtning och BM25 räddade inget fall som katalogen missade. Hämtningens enda träff (R1) hade katalogen också.

Hämtningens 1/11 är samma tal som i helarkivmätningen: toppträffen låg i fel handling i 10 av 11. Det talet är dokumentets max fused, inte en slump i `topK`.

## Per fall

| fall | facit | hämtning | lexikalt | modell | minst en |
| --- | --- | --- | --- | --- | --- |
| R1 | G | **G** | D | **G** | ja |
| R2 | G | H | H | **G** | ja |
| R3 | G | D | D | **G** | ja |
| R4 | E | B | B | **E** | ja |
| R5 | E | C | C | C | **nej** |
| R6 | E | C | C | I | **nej** |
| R7 | E | F | H | D | **nej** |
| R8 | E | H | H | **E** | ja |
| R3b | G | D | D | D | **nej** |
| R5b | E | C | B | **E** | ja |
| R7b | E | G | D | D | **nej** |

Handlingarna är bokstäver i namnordning. Ingen avtalstext, inga filnamn.

Modellens träffar är de fall där frågan delar ett ämnesord med titeln: parkering (R1, R2, R3) och sophämtning/sophantering (R4, R8, R5b). R4 har `bridge_in_filename` i fallfilen; R5b och R8 har samma bro i frågan. När ordet tas bort faller träffen: R3 har *parkering*, R3b har *gården* — samma skadefråga, katalogträff → alla tre miss.

BM25 på dokumentnivå träffade aldrig facit. Distraktorerna C, D och H vann på generella ord. Embedding i fused-rankningen flyttade en enda träff (R1). Resten av hämtningen följer samma felsida som det rena lexikalet.

## Ordglappet, de fem där alla tre missade

Samma tokenizer som indexet. *I facit* = exakt token eller sammansättning i facithandlingen. *I andra* = antal övriga handlingar med samma träff.

### R5 — extra avgift som Stena lägger på fakturorna. Facit E.

| ord i frågan | i facit | i andra |
| --- | --- | ---: |
| extra | nej | 1 |
| avgift | nej | 3 |
| stena | ja | 5 |
| lägger | nej | 0 |
| fakturorna | nej | 1 |

Pekordet är *avgift* / *fakturorna*. Inget av dem finns i E. E säger administrationskostnad. *Stena* finns i E och i fem andra handlingar — det pekar inte ut någon.

### R6 — hur stor del av kostnaderna ska föreningen betala. Facit E.

| ord i frågan | i facit | i andra |
| --- | --- | ---: |
| kostnaderna | ja (`driftskostnaderna`) | 6 |
| föreningen | ja (`bostadsrättsföreningen`) | 7 |
| betala | nej | 4 |

Inget ord pekar ut E. Frågan är underspecificerad på handlingsnivå.

### R7 — måste Stena säga till innan de höjer priset. Facit E.

| ord i frågan | i facit | i andra |
| --- | --- | ---: |
| stena | ja | 5 |
| höjer | nej | 0 |
| priset | nej | 1 |

Pekordet är *höjer* / *priset*. Inget av dem finns i E. E säger varsko / prisjusteringar. *Stena* pekar inte ut E.

### R3b — vem står för kostnaden om en bil får en skada på gården. Facit G.

| ord i frågan | i facit | i andra |
| --- | --- | ---: |
| kostnaden | nej | 3 |
| bil | nej | 1 (D) |
| skada | ja | 2 |
| gården | nej | 0 |

Pekordet en människa skulle använda är *bil*. Det finns inte i G. Det finns i D — och alla tre metoderna valde D. *gården* finns inte i någon handling. *skada* finns i G men räcker inte.

### R7b — får leverantören höja priset utan att meddela oss först. Facit E.

| ord i frågan | i facit | i andra |
| --- | --- | ---: |
| leverantören | nej | 2 |
| höja | nej | 0 |
| priset | nej | 1 |
| meddela | nej | 2 |

Pekordet är *leverantören*. Det finns inte i E. Inget annat innehållsord i frågan finns i E heller. Det är samma glapp som BRF-5 mätte på svarsnivå, nu på handlingsnivå, utan bro i titeln.

## Vad det här säger

De tre felen — fel handling överst i hämtningen, fel handling citerad, sonden som inte lägger rätt handling vid kanten — har samma underskott: **systemet kan inte välja handling**. Signalen sitter inte i fused-rankningen och inte i dokument-BM25. Den sitter i titeln, och bara när frågan redan använder titelns ord.

På fem av elva fall finns signalen ingenstans i de tre metoderna. På tre av de fem (R5, R7, R7b) är styrelsens pekord frånvarande ur facithandlingen. På R3b pekar det distinkta ordet (*bil*) på fel handling och saknas i facit. På R6 pekar frågan inte på någon handling.

Det är inte ett retrieval-`topK`-fel och inte ett lost-in-the-middle-fel. Det är ett ordförrådsglapp på handlingsnivå.
