# Ger gränsad fan-out något? (BRF-5, första mätningen)

**Datum:** 2026-08-12 · **Harness:** `backend/scripts/eval_crossdoc.py` ·
**Gren:** `feat/brf-1-cross-document`

> **Det här dokumentet mäter HÄMTNINGSSTRATEGIN**, med fallens handskrivna
> delfrågor och ingen modell alls. Slutsatserna nedan står. Om en riktig
> planerare väljer rätt läge och skriver de delfrågorna mättes senare i
> [`planner-vs-real-model.md`](planner-vs-real-model.md), och grindbeslutet
> togs på de siffrorna: [fan-out skeppas inte i MVP](fan-out-mvp-beslut.md).

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

### Omgång 4 — mätning på den verkliga korpusen (driftbevis)

Alla nio verkliga handlingar kördes genom `Store.add_document`, alltså den
riktiga ingest-vägen med OCR. **9 av 9 lyckades**, 130 chunkar. Sedan
styrelsens egen fråga, "Betalar vi fortfarande fast pris för sophämtningen?",
mot den korpusen vid budget 4:

| Strategi | Bevischunkar funna (av 5) |
|---|---|
| Enkel sökning | **0** — alla fyra träffar i *Avtal Teknisk förvaltning* |
| Planerad fan-out | **3** |

Enkelsökningen hämtade fyra chunkar ur **fel avtal** och noll bevis. Det
lexikala lockbetet — ett dokument som matchar frågans ord bättre än det som
svarar — uppstod alltså av sig självt i en verklig korpus på nio handlingar.
Det behövde inte konstrueras.

Detta är driftbeviset som saknades i omgång 3.

### Två motbevisade hypoteser, värda att spara

**"Nollöverlappning räcker för att fälla sökningen."** Tre fall byggda direkt
på kartläggningens glapp-par (v00 avgiftsbegränsning, v01 indexklausul, v02
förverkande) får alla 1.00 på enkel sökning — även när lexikala lockbeten
läggs till. BM25 hittar dem ändå. Mina konstruerade fall är systematiskt för
lätta, på sätt jag upprepade gånger misslyckats med att förutse. Det enda fall
som verkligen fallerar kommer från en verklig handling. **Slutsats: bygg inte
fler syntetiska glapp-fall — mät på riktiga arkiv.**

**"Den täta vektordelen överbryggar glappet."** Tvärtom. Med `weight=1` (bara
embeddings) sjunker recall till 0.00 på x06, v01 och v02; BM25 ensamt ger 1.00
på samtliga v-fall. Hybridsökningen följer BM25, inte embeddings.

| Fall | BM25 (w=0) | Hybrid (0.5) | Tät (w=1) |
|---|---:|---:|---:|
| x06 | 0.50 | 0.50 | 0.00 |
| r01 | 0.00 | 0.00 | 0.00 |
| v01 | 1.00 | 1.00 | 0.00 |
| v02 | 1.00 | 1.00 | 0.00 |

Jag drog av detta slutsatsen att **embeddingmodellen inte förtjänar sin halva
av `searchWeighting`**, och rekommenderade att mäta det. Det gjordes — och
slutsatsen höll inte.

### Omgång 5 — svep av searchWeighting (motbevisar omgång 4:s rekommendation)

`scripts/eval_crossdoc.py --weights` sveper fusionsvikten för en ENKEL sökning,
en fråga som är oberoende av BRF-1 och gäller varje fråga produkten besvarar.

Golden-korpusen (11 fall, budget 4 och 6) — vikt 0, 25 och 50 är likvärdiga,
och först *över* 50 rasar det:

| searchWeighting | 0 | 25 | 50 | 75 | 100 |
|---|---:|---:|---:|---:|---:|
| medelrecall | 0.86 | 0.86 | 0.86 | 0.73 | 0.50 |

Men på den **verkliga korpusen** (9 handlingar, 130 chunkar) replikerades det
inte. Fyra frågor i styrelsespråk, bevis definierade av distinkta termer:

| Fråga | w0 | w25 | w50 | w75 | w100 |
|---|---:|---:|---:|---:|---:|
| Fast pris för sophämtningen | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Uppsägningstid sophämtning | **1.00** | 0.80 | 0.80 | 0.80 | 0.60 |
| Vad kostar parkeringsplatsen | 0.36 | 0.36 | 0.36 | **0.45** | **0.45** |
| ~~Vad ska vi renovera~~ | — | — | — | — | — |

Fjärde proben är **ogiltig och räknas inte**: nyckelordsgrunden fångade 54 av
130 chunkar, alltså halva korpusen. Det är inte bevis, det är brus — samma
sorts slarv som gjorde den första expansionslocken verkningslös.

**Slutsats: ingen grund att ändra `searchWeighting=50`.** De två giltiga
verkliga fallen drar åt var sitt håll — BM25 vinner klart på uppsägningstid,
embeddings vinner klart på parkeringskostnad. Golden-korpusens signal att
embeddings skadar var en artefakt av korta, ämnesrena fixturdokument.

Fallet "fast pris" är 0.00 vid *varje* vikt. Det bekräftar att det är ett äkta
ordförrådsglapp och inte ett fusionsproblem: **ingen inställning på den här
ratten hade räddat det.** Det är precis därför fan-out är rätt svar just där.

### OCR: redan löst, tvärtemot vad jag rekommenderade

Materialet från en verklig styrelse (nio handlingar) karakteriserades innan
fallen skrevs. Resultatet gör om prioriteringen:

| | Sidor | Ord ur textlagret |
|---|---:|---:|
| Avtal Ekonomisk förvaltning | 13 | 2082 |
| Underhållsplan 30 år | 36 | 3553 |
| **Övriga sju avtal** | 3–30 | **0** |

**Sju av nio avtal saknar textlager helt** — de är inskannade. Hela den här
mätningen handlar om *vilken sökstrategi* som hittar rätt stycke, men för 78 %
av den här styrelsens avtal finns inget stycke att hitta förrän OCR körts.
Fan-out ligger nedströms ett steg som inte har körts. **Ordförrådsglappet är
verkligt, men läsbarheten är den bindande begränsningen.**

Det förklarar styrelsens egna loggade händelser bättre än vår hypotes gjorde:
"visste inte var bredbandsavtalet fanns", "slutbesiktningsprotokollet grävdes
fram". Det är inte sökproblem — handlingarna var inte maskinläsbara.

Jag rekommenderade utifrån detta att OCR-täckning skulle gå före allt annat
BRF-1-arbete. **Den rekommendationen var fel — arbetet var redan gjort.**
`Store.add_document` upptäcker att textlagret är tomt och kör `ocr_pdf`
automatiskt, med ett tydligt svenskt fel om tesseract saknas.

Verifierat på hela det verkliga materialet:

| | Resultat |
|---|---|
| Handlingar som gick igenom ingest | **9 av 9** |
| Skannade som OCR-kördes automatiskt | 7 av 7 |
| Chunkar totalt | 130 |
| Tid, skannade | 4–31 s/handling (digitala: 0,1 s) |

Så den bindande begränsningen var aldrig OCR-*täckningen* utan att jag inte
hade kontrollerat om den fanns. Kvar som verklig konsekvens: OCR kostar upp
till en halvminut per handling, vilket är en uppladdnings-UX-fråga, inte en
retrieval-fråga.

### Omgång 3 — verkliga fall

Tre fall härledda ur en verklig styrelses loggade händelser. Frågorna och
ordförrådet är äkta, och **mekanismen är nu avläst ur den faktiska handlingen
efter OCR**. Meningarna, beloppen och parterna i golden-filen är däremot
hittepå: originalavtalet är en verklig förenings handling och dess text får
inte ligga i git.

Det gav en rättelse värd att notera. Både styrelsens sammanfattning och min
rekonstruktion sa "fast pris fram till 2024, därefter rörligt". Avtalet säger
något annat: *kvartal 1–3 faktureras schablonbelopp, avräkning sker efter
kvartal 4 mot årets verkliga kostnader*, och avtalet reglerar verkliga kostnader
med prisjusteringar när de uppkommer. Schablonbeloppet är alltså ett à-conto,
inte ett fast pris — vilket gör styrelsens oro *mer* befogad, inte mindre.

Per fall vid budget 4, korpus 48 chunkar:

| Fall | Ursprung | Enkel | Planerad |
|---|---|---:|---:|
| r00 snöröjning på kvartalsfaktura | verklig | 1.00 | 1.00 |
| **r01 schablon vs verklig kostnad** | **verklig** | **0.00** | **1.00** |
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
