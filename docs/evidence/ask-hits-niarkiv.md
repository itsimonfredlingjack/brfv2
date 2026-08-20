# Evidence — vad ligger bakom de 32 vägrade niarkiv-frågorna (2026-08-20)

Diagnoserar fem av de 32 `insufficient_data`-vägran från niarkiv-körningen mot verkliga
protokoll/kallelser (`resultat-ask-hits.json`, temperatur 0). Metod: omkörning av modellens
råsvar med samma packade prefix som originalkörningen (som inte sparade JSON:et), plus
manuell läsning av den fulla packade texten mot frågan. **Redaction:** dokumentnamn/motioner
är från verkliga föreningars protokoll — inget PDF-innehåll återges här utöver de citerade
raderna nödvändiga för klassificeringen.

## Varför den här filen finns

Föregående fråga ("citatverifieringsfel eller genereringsfel?") gick inte att svara på från
aggregatet ensam. Den här filen läser fem konkreta fall rad för rad i stället för att lita på
en aggregerad procentsats.

## Arkitekturfaktum, verifierat mot koden — inte bara mot stickprovet

`backend/app/answer.py:355–358`:

```python
insufficient = parsed["insufficient_data"]
if insufficient and s.insufficientDataBehavior == "refuse":
    ...
    return _refusal(...)          # returnerar HÄR

hit_scores = {h.chunk_id: h.score for h in hits}   # citatloopen börjar här, aldrig nådd
```

När modellen själv sätter `insufficient_data: true` returnerar produkten **innan**
citatverifieringsloopen (rad 360+) någonsin körs. Det gör slutsatsen nedan strukturell, inte
stickprovsberoende: **citatverifieringsfel är uteslutet för samtliga 32 fall** — koden kan
inte nå den grenen när modellen själv vägrar. Det som återstår att avgöra per fall är bara
fördelningen mellan genereringsfel och arkivfaktum.

## Bucket-fördelning (fem lästa fall av 32)

| fall | dokument | grind | klass |
|---|---|---|---|
| M03 | Skäpplandsgatan, protokoll-3.pdf | modellen själv, noll citat | ordförrådsglapp fråga↔handling |
| F01 | Slottet, protokoll-2.pdf | modellen själv; ett citat som skulle ha verifierats fanns, men kortslöts av `insufficient_data`-grenen före loopen | arkivfaktum, nästan-träff |
| F03 | Fåran, protokoll-2.pdf | modellen själv, noll citat | arkivfaktum, med antydan |
| A39 | Kajen, protokoll-1.pdf | modellen själv, noll citat | arkivfaktum |
| M02 | Dikten 2, protokoll-1.pdf | modellen själv, noll citat | arkivfaktum |

Noll av fem är citatverifieringsfel (väntat, se arkitekturfaktumet ovan). Fyra av fem är rena
arkivfakta: den efterfrågade saken står helt enkelt inte i den packade handlingen. Ett (M03)
är ett ordförrådsglapp på svarssidan — närbesläktad information finns, men inte frågans exakta
sak.

## Fallen

### M03 · Skäpplandsgatan · protokoll-3.pdf

Nivå M · motion om träd, packad hel · 5 stycken · 2 414 tokens (samma som originalet).

**Frågan:** "Motion om återplantering av träd vid entrén till innergården. I samband med
dräneringsarbetet av fastigheten togs det träd bort, som tidigare stod vid entrén till
innergården. Sedan dess har området förändrats och entrén upplevs idag som mer öppen, tom och
hård i sitt uttryck."

**Packad text:** Hela PDF:en. K1–K2 öppnande, röstlängd, årsredovisning, arvoden, val. K4
underskrifter. K5 Verified-logg. Besluten sitter i K3, sida 3, punkt 18 (motioner):
Motion 1 fiber — besvarad; Motion 2 solpaneler — avslagen; Motion 3 cykelförråd — avslagen;
Motion 4 lönnar vid parkering som «savar» — bifallen; Motion 5 grovtvättmaskin — avslagen;
**Motion 6: plantering av nya träd och buskar på en del av gräsmatta framför uteplatsen och
sandlådan — avslagen**; Motion 7 bänk/nyckelsystem — besvarad/återtagen.

**Modellens JSON (före vägran):**
```json
{
  "answer": "insufficient_data: Det finns ingen motion om återplantering av träd vid entrén till innergården i de tillhandahållna utdragen.",
  "citations": [],
  "insufficient_data": true
}
```

**Grind:** modellen själv, noll citat. Inte verifieringsfel.

**Klass:** ordförrådsglapp mellan fråga och handling, inte genereringsmiss av identisk text
och inte citatfel. I K3 står ett träd-beslut, men det är en annan motion: *plantering* (inte
*återplantering*), vid *uteplats och sandlåda* (inte *entré efter dränering*). Modellen krävde
frågans exakta scen. Kontraktet ("hitta aldrig på") gör vägran konsekvent, men en människa som
läser K3 ser ändå ett svar i samma familj.

### F01 · Slottet · protokoll-2.pdf

Nivå F · FAQ-fråga mot fel förenings datum · 9 stycken · 3 960 tokens.

**Frågan:** "Vad har beslutats på föreningsstämman den 27 maj 2024?"

**Packad text:** Hela protokollet från 7 maj 2024 (inte 27). Sidhuvud på varje blad:
"Sammanträdesdag … 2024-05-07." Innehåller bl.a. fastställd årsredovisning, resultatdisposition,
ansvarsfrihet, oförändrade arvoden, val (Höper ordförande, Dymling/Lindblad/Karlsson/Hjortsberg,
Riomar adjungerad), Motion 1 fartdämpare — avslagen, Motion 2 fler laddplatser — "Stämman
diskuterade att det inte finns några lediga laddplatser i garaget nu" — bifallen, samt en
stadgeändringsproposition. "27 maj" förekommer aldrig; "diskuterade" gäller laddplatser den 7
maj.

**Modellens JSON:**
```json
{
  "answer": "Det finns ingen information om vad som beslutats på föreningsstämman den 27 maj 2024, då dokumenten endast innehåller protokoll från stämman den 2024-05-07.",
  "citations": [{"chunk_id": "K1", "quote": "Sammanträdesdag Brf Slottet Organisations nummer 716444-7687 2024-05-07"}],
  "insufficient_data": true
}
```

**Grind:** modellen själv. Citatet i K1 verifieras mot sida 1 om man kör verifieringen ändå —
men `insufficient_data` returnerar före den loopen, så originalraden har `n_citations: 0` av
samma skäl, inte för att citatet föll på verifiering.

**Klass:** arkivfaktum, med nästan-träff. Protokollet är fullt av beslut; frågan låser bara
fel datum. 27 maj är en annan förenings FAQ-datum, ställd mot Slottet.

### F03 · Fåran · protokoll-2.pdf

Nivå F · 5 stycken · 2 276 tokens.

**Frågan:** "Var kan jag hitta information om markförsäljningen?"

**Packad text:** Inte ett stämmoprotokoll — kallelse till stämma 9 juni 2026, fullmakt och en
proposition. Inget beslut fattat. Kallelsepunkt 17, Proposition 1: ändring av användningsområde
från lokal till bostadsrätt. Propositionstexten (K3–K4): "Styrelsen föreslår stämman att
godkänna ändrad användning av hyreslokal 161 på Hagavägen 14 från lokaländamål till
bostadsändamål och att två bostadslägenheter uppförs … Styrelsen föreslår även … genomföra
upplåtelse och försäljning av bostadsrätterna." samt "Styrelsen har under en längre tid utrett
möjligheten att konvertera hyreslokal 161 …" och "Bilagorna hittas på föreningens hemsida,
under Dokument, www.brffaran.se". "Markförsäljning" förekommer inte.

**Modellens JSON:**
```json
{
  "answer": "insufficient_data: Det finns ingen information i utdragen om markförsäljning; dokumenten behandlar istället en proposition om ändring av användningsområde från lokal till bostadsrätt.",
  "citations": [],
  "insufficient_data": true
}
```

**Grind:** modellen själv, noll citat.

**Klass:** arkivfaktum, med antydan. FAQ:n förutsätter en markförsäljning (bestämd form, en
annan förening). Här är en kallelse om lokal→bostad, fortfarande "utrett"/"föreslår", inte
beslut — och en försäljning av *bostadsrätter*, inte av *mark*. Modellen höll isär de två.
Vägran är korrekt.

### A39 · Kajen · protokoll-1.pdf

Nivå A · 19 stycken · 8 003 tokens · längsta protokollet bland de 32.

**Frågan:** "Till vår senaste stämma hade ett par medlemmar lämnat in motioner om att
avgiftsbelägga vår gästparkering. Majoriteten av medlemmarna röstade emot förslaget. Nu vill
några i den nya styrelsen ändå avgiftsbelägga gästparkeringen med motiveringen att detta är en
styrelsefråga och inte en stämmofråga. Men får vi gå emot stämmobeslutet?"

**Packad text:** Ordinarie stämma 2023-06-13 (Verified-filnamnet säger 2024-06-13, sidhuvudet
2023 — internt inkonsekvent men irrelevant för klassen). Hela handlingen packad, inklusive
signatursida. Faktiska beslut: öppnande, röstlängd, årsredovisning, revisionsanmärkning om
sena protokoll, resultat, ansvarsfrihet, arvoden (1 PBB), val, ombud, samt: gemensamhets-
anläggning/Fyrhusen/"markbiten vid gymmet" och p-platser att hyra ut (blåljusplatser) — inte
gästparkering, inte avgift mot stämmobeslut; gymmets öppettider — ja; våtrum mot HSB Bostad —
ja; laddstationer i garage — avslås; infart undre garage — ja; andra stadgebeslutet — ja.
"Gästparkering", "avgiftsbelägga" och "gå emot stämmobeslutet" förekommer inte.

**Modellens JSON:**
```json
{
  "answer": "Det finns ingen information i utdragen om motioner gällande avgiftsbeläggning av gästparkering eller om styrelsens rätt att gå emot ett stämmobeslut i en sådan fråga. Utdragen innehåller dock beslut om andra ärenden såsom gemensamhetsanläggning, gymmets öppettider, våtrum och laddstationer.",
  "citations": [],
  "insufficient_data": true
}
```

**Grind:** modellen själv, noll citat. Den räknar upp vad som faktiskt finns och vägrar det
som efterfrågas — inte en gissning på närmaste träff.

**Klass:** arkivfaktum. Frågan är ett generellt juridiskt case (typen syns på Flashback-nivå),
Kajens protokoll är en annan stämma. Lexikal överlappning ("parkering", "motion", "stämma")
räcker för att handlingstypen ska ranka högt utan att innehållet matchar. Svaret på "får
styrelsen gå emot stämman?" står inte i den här handlingen.

### M02 · Dikten 2 · protokoll-1.pdf

Nivå M · 9 stycken · 4 003 tokens.

**Frågan:** "Idag kan tydligen en styrelseledamot bo på annan adress som inte tillhör
[namn]. Det kan inte vara lämpligt att styrelseledamot som har arvode inte bor i föreningen."

**Packad text:** Stämma 23 april 2026. K1–K7 protokollet, K8–K9 Verified. Punkt 14 (K2/K3):
"Stämman beslutade att arvoden för styrelseledamöter och styrelsesuppleanter ska vara
oförändrade och fortsatt uppgå till tio (10) prisbasbelopp … Jaana Alenius bad att få noterat
i protokollet att hon anser att arvodet är högt." Ledamöterna väljs med gatuadresser i
föreningen (Virebergsvägen, Brommavägen) — adresslistan är vilka som valdes, inte en regel om
boendekrav. Inget beslut och ingen diskussion om att ledamot måste bo i föreningen. Övriga
motioner (bastu, porttelefon, dörröppnare, portkoder) är alla avslagna och orelaterade.

**Modellens JSON:**
```json
{
  "answer": "Utdragen innehåller ingen information om krav på att styrelseledamöter ska bo i föreningen eller om det är olämpligt att bo på annan adress.",
  "citations": [],
  "insufficient_data": true
}
```
(Råsvaret hade även fältet `insufficient_data_explanation`; parsningen tar bara
`answer`/`citations`/flaggan.)

**Grind:** modellen själv, noll citat.

**Klass:** arkivfaktum. Urvalet träffade för att "arvode" och "styrelseledamot" står i både
fråga och protokoll. Saken frågan vill ha — ett bosättningskrav — står inte där.

## Slutsats

Det som ser ut som "modellen hittar inte det som står där" är i M03 egentligen att det som
står där inte är frågans sak. I F01 står massor av beslut — bara inte för den 27 maj. Resten
(F03, A39, M02) är att niarkiv-frågan helt enkelt inte är skriven mot den packade handlingen
den ställdes mot. Samma slutsats som `refusal-diagnosis.md` drog för de 13 finansiella
vägran-fallen — retrieval/urval, inte generering eller citatverifiering, är den återkommande
felkällan — gäller här i en annan form: rätt handlingstyp hämtas, men fel handlings-*instans*.

Citatverifieringsgrinden (`resolve_citation`, `answer.py:376+`) förblir overifierad av den här
körningen eftersom `insufficient_data` kortsluter innan den nås — det gäller strukturellt för
alla 32, inte bara de fem lästa. Att mäta grindens egen träffsäkerhet kräver ett separat
underlag: fall där modellen *försöker* citera mot verklig text, inte fall där den vägrar
direkt.
