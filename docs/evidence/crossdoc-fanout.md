# Ger gränsad fan-out något? (BRF-5, första mätningen)

**Datum:** 2026-08-12 · **Harness:** `backend/scripts/eval_crossdoc.py` ·
**Gren:** `feat/brf-1-cross-document`

## Kort svar

**Ja — men bara vid ordförrådsglapp, inte vid flerdokumentsfrågor i allmänhet.**

Det är en skarpare slutsats än den första körningen gav, och den ändrar vad
planeraren borde utlösa på. Mätningen gjordes i två omgångar; omgång ett
saknade det fall som visade skillnaden.

- På frågor som *har flera delar* men bär orden som ska sökas: fan-out är
  neutral eller **sämre** än en sökning vid samma budget.
- På en fråga ställd med **andra ord än dokumenten använder**: fan-out är det
  enda som fungerar, och med färre utdrag. På det verkliga fallet r01 går den
  från **0.00 till 1.00** — enkelsökningen hittar ingenting alls.

`PER_QUERY_TOP_K` och `MAX_EVIDENCE_CHUNKS` får fortfarande inte trimmas här —
rekonstruerad dokumenttext är för tunt underlag för att kalibrera rattar på.

## Vad som mäts

Bevisrecall, utan LLM: för varje golden-fall är de chunkar kända som ett
korrekt svar måste citera ur (golden-citaten pekar ut dem). Frågan är om de
chunkarna **når prompten över huvud taget**. En chunk som inte når prompten kan
inte citeras, så det är ett hårt tak på svarskvalitet som ingen modell kan
klättra över.

Ingen modell körs. Siffran ska inte röra sig när modellen byts.

## Resultat

Korpus: 4 golden-dokument + 40 distraktorer = 44 dokument/chunkar. Båda
strategierna får **samma totala promptbudget** — annars "vinner" fan-out bara
genom att få kosta mer.

### Omgång 1 — utan ordförrådsglappsfall

| Budget (utdrag) | Enkel sökning | Planerad fan-out |
|---:|---:|---:|
| 2 | 0.88 | 0.62 |
| 3 | **1.00** | 0.62 |
| 4 | 1.00 | 1.00 |

Enkelsökningen nådde full recall vid budget 3; fan-outen behövde 4. Slutsatsen
då: fan-out ger ingenting. Men korpusen saknade det fall den finns för.

### Omgång 2 — med `x06 vocabulary_gap`

Ett fall där frågan är ställd i styrelsens vardagsspråk — "vinterunderhållet",
"upphandlat", "notan" — medan dokumenten säger "snöröjning", "beslutade att
godkänna" och "ersättning". Inget av frågans nyckelord finns i de dokument som
svarar. Korpusen fick också fyra **lexikala lockbeten** som bär frågans ord
(Upphandlingspolicy, Underhållsbudget, Vinterberedskap, Fakturarutin), så en
enkel sökning aktivt dras dit.

Per fall vid budget 4:

| Fall | Shape | Enkel | Planerad |
|---|---|---:|---:|
| x00 | two_document_answer | 1.00 | 1.00 |
| x01 | multi_part_question | 1.00 | 1.00 |
| x03 | conflicting_documents | 1.00 | 1.00 |
| x05 | time_bound_question | 1.00 | 1.00 |
| **x06** | **vocabulary_gap** | **0.50** | **1.00** |

x06 är det **enda** fallet där fan-out vinner — och den vinner med färre utdrag
(2.8 mot 4.0 i snitt). Enkelsökningen fastnar på 0.50 där ända upp till budget 6.

### Omgång 3 — verkliga fall

Tre fall härledda ur en verklig styrelses loggade händelser (BRF Eken, aug
2026). **Frågorna och ordförrådet är äkta; dokumentens exakta formuleringar är
rekonstruerade** — vi har inte originalhandlingarna. Det fallen står och faller
med är glappet mellan styrelsens ord och handlingens ord, och det är äkta.

Per fall vid budget 4, korpus 48 chunkar:

| Fall | Ursprung | Enkel | Planerad |
|---|---|---:|---:|
| r00 snöröjning på aprilfaktura | verklig | 1.00 | 1.00 |
| **r01 tyst prisändring** | **verklig** | **0.00** | **1.00** |
| r02 muntligt vs skriftligt | verklig | 1.00 | 1.00 |

**r01 är det starkaste resultatet i hela mätningen.** Enkelsökningen hittar
*ingendera* av de chunkar som krävs — inte 0.50, utan noll. Frågan lyder
"Betalar vi fortfarande fast pris för sophämtningen?"; handlingen säger
"schablonbelopp" och "Sophantering och gårdsskötsel". Inget ord matchar. Värre:
korpusen innehåller en distraktor, `Sophamtning.pdf` ("Hämtning av
hushållsavfall sker på tisdagar"), som matchar frågans ord perfekt utan att
svara på den. Sökningen dras dit.

Det är den realistiska felmoden: **ett dokument som matchar frågans ord men
inte besvarar den.** Och r01 är just det fall styrelsen i verkligheten missade.

En förutsägelse som slog fel, värd att notera: jag trodde snöröjningsfakturan
(r00) skulle vara det svåra fallet, eftersom förklaringen står i en klausul som
varken nämner snö eller april. Enkelsökningen klarar den ändå — ordet
"snöröjning" står på fakturan, och avtalsklausulen ligger nära nog i samma
dokument. Det svåra var i stället den tysta prisändringen.

## Vad det betyder för planeraren

Fan-outens värde ligger i **ordförrådsglappet, inte i flerdokumentsheten**. Det
gör den ursprungliga planerarinstruktionen fel: den sa "välj multi när frågan
har flera delar", och just den utlösaren är mätt som verkningslös — flerdelade
frågor bär redan orden som ska sökas, och en sökning hittar dem.

`PLANNER_CONTRACT` är därför omskriven: `multi` utlöses av att frågan är ställd
med andra ord än dokumenten använder, och delfrågorna ska vara **översättningar
till dokumentens terminologi**, inte frågans egna ord uppdelade i bitar.

Två fällor jag gick i och som är värda att minnas:

1. **Första körningen gav 1.00/1.00 och såg ut som en framgång.** Korpusen var
   4 chunkar och `topK=6` — varje sökning returnerade hela korpusen. Mätningen
   diskriminerade ingenting. Därav distraktorerna, och
   `test_distractors_actually_make_retrieval_choose`.
2. **Att ge fan-outen egen budget döljer resultatet.** Med `topK=6` per delfråga
   mot 6 totalt för enkelsökningen ser fan-out bättre ut, men jämförelsen är
   meningslös. Svepet håller notan lika.

## Vad som borde göras härnäst

- **Riktiga handlingar, inte rekonstruerade.** Fallens ordförråd är äkta men
  dokumenttexten är min. Med originalfakturan och originalavtalet blir samma
  mätning ett faktiskt driftbevis i stället för en indikation.
- **Mät på riktig korpus**, inte fixturer med en chunk per dokument. Verkliga
  årsredovisningar och stadgar har många chunkar per dokument, vilket är där
  budgettrycket faktiskt uppstår.
- **Mät planeraren separat.** Harnesset kör fallens egna delfrågor, inte
  planerarens — avsiktligt, så att retrieval och planering inte blandas ihop.
  Men det betyder att ingenting ännu mäter om en riktig modell *upptäcker*
  ordförrådsglappet. Det är nu den svagaste länken.
- **Först därefter** trimma `PER_QUERY_TOP_K` / `MAX_EVIDENCE_CHUNKS`.

Tills dess: den planerade vägen ligger kvar bakom `BRF_PLANNED_ASK` och är
avstängd som default. Mekanismen är visad på ett fall — det är inte samma sak
som att funktionen är bevisad i drift.
