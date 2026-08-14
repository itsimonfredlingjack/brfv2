# Planeraren mot en riktig modell (XS-62)

> **Grindbeslutet som togs på de här siffrorna:**
> [fan-out skeppas inte i MVP](fan-out-mvp-beslut.md) — med de fyra villkor som
> måste vara sanna för att slå på den igen.
>
> **Läs [tillägget om sorterad katalog](#tillägg-2026-08-13-sorterad-katalog) först.**
> Allt nedanför mättes med katalogen i **uppladdningsordning**. Sedan dess
> sorteras den (`multihop.catalogue_names`), vilket är en annan prompt — och
> r01, huvudresultatet i det här dokumentet, vänder från 0.00 till 1.00.
> Siffrorna nedan är inte fel; de gäller en kodversion som inte längre finns.

**Datum:** 2026-08-13 · **Harness:** `backend/scripts/eval_planner.py` ·
**Rådata:** `backend/eval/last_planner_run.json` · **Gren:** `feat/brf-1-cross-document`

**Modell:** `gemma-4-12b-it` UD-Q4_K_XL på llama.cpp (agenntserver, SSH-tunnel till
`127.0.0.1:8000/v1`), genom produktionens `OpenAICompatProvider` med
`temperature=0` — alltså exakt den väg en pilot använder.

## Kort svar

**Fan-outens hämtningsstrategi håller. Planeraren gör inte det.**

`crossdoc-fanout.md` visade att gränsad fan-out går från 0.00 till 1.00 på r01,
det enda verkliga fall där en enkel sökning missar allt. Den mätningen kör
fallens **handskrivna** delfrågor. Med en riktig modell i planerarrollen väljer
planeraren `single` på r01 tio gånger av tio och får **0.00**. Det uppmätta
värdet realiseras inte.

Samtidigt utlöser den `multi` på 14 av 46 enkelsökningsfrågor där det inte
tillför något och kostar tre sökningar i stället för en. Och på två frågor som
en enda sökning besvarar perfekt svarar den `clarify` — den vägrar söka alls.

## Vad harnesset mäter, och hur

Tre tal per fall, över 10 körningar:

1. **bevisrecall med planerarens egna delfrågor** — samma bevisdefinition som
   `eval_crossdoc.py`: når de chunkar ett korrekt svar måste citera ur prompten?
2. **andel körningar som valde `multi`**
3. **antal sökningar som utfördes** — räknat där `HybridIndex.search` anropas,
   inte härlett ur läget. En härledd siffra ("multi ⇒ 3") hade missat
   `ask_planned`:s extra fallback-sökning.

Körningen går genom den **riktiga `ask_planned`**. Bara syntesanropet är
kanonsvarat: XS-62 frågar vad planeraren beslutar och vad beslutet hämtar, och
att låta modellen skriva svaret hade blandat in svarskvalitet i en
hämtningssiffra. Planerar- och syntesanropen skiljs på systemprompten, och
harnesset avbryter om ett fall inte gav exakt ett planeraranrop.

`multi` poängsätts inte. Fan-out är neutral eller sämre på fyra av sex
golden-fall och kostar ett modellanrop plus tre sökningar, så överutlösning är
en regression. Därför körs **46 enkelsökningsfrågor ur `eval/golden.json` som
negativa kontroller** — samma golden produkten redan mäts mot, inte en lista
skriven för det här experimentet.

Mätningen har ingen exitkod som beror på siffrorna och grindar aldrig CI.

### Varför två varianter — och varför tio identiska körningar mäter ingenting

Produktionens `temperature=0` gör avkodningen girig. **Planeraren är helt
deterministisk vid identisk prompt:** 0 av 59 fall varierade läge över tio
körningar, inte heller under parallella anrop. En stabilitetssiffra byggd på
att köra samma prompt tio gånger hade rapporterat 100 % stabilitet utan att ha
prövat något — samma sorts vakuositet som projektets övriga fem.

Den variationskälla som faktiskt finns är **dokumentkatalogens ordning**.
`ask_planned` skickar `[m.name for m in documents.values()]`, vars ordning
följer uppladdningsordningen. Variant `shuffled` blandar den per körning. Där
byter **22 av 59 fall läge** mellan körningar.

Båda varianterna redovisas. `fixed` är en enskild förenings upplevelse;
`shuffled` är spridningen över föreningar med samma handlingar i annan ordning.

## Resultat — tvärdokumentsfallen (13 fall, 10 körningar)

| Fall | Förväntat | Valda lägen (fixed) | Recall (fixed) | Valda lägen (shuffled) | Recall (shuffled) | Enkel baslinje |
|---|---|---|---:|---|---:|---:|
| x00 two_document_answer | multi | single×10 | 1.00 | single×10 | 1.00 | 1.00 |
| x01 multi_part_question | multi | single×10 | 1.00 | single×10 | 1.00 | 1.00 |
| x02 clarification | clarify | clarify×10 | — | clarify×10 | — | — |
| x03 conflicting_documents | multi | single×10 | 1.00 | single×10 | 1.00 | 1.00 |
| x04 no_evidence_refuses | multi | single×10 | — | single×10 | — | — |
| x05 time_bound_question | multi | single×10 | 1.00 | single×10 | 1.00 | 1.00 |
| x06 vocabulary_gap | multi | multi×10 | 1.00 | multi×10 | 1.00 | 0.50 |
| r00 vocabulary_gap | multi | single×10 | 1.00 | multi×5 single×5 | 1.00 | 1.00 |
| **r01 vocabulary_gap** | **multi** | **single×10** | **0.00** | multi×8 single×2 | 0.80 (0.00–1.00) | **0.00** |
| r02 conflicting_documents | multi | single×10 | 1.00 | single×10 | 1.00 | 1.00 |
| v00 vocabulary_gap | multi | multi×10 | 1.00 | multi×10 | 1.00 | 1.00 |
| v01 vocabulary_gap | multi | single×10 | 1.00 | multi×10 | 1.00 | 1.00 |
| v02 vocabulary_gap | multi | multi×10 | 0.00 | multi×10 | 0.90 (0.00–1.00) | 1.00 |
| **medel** | | 23 % multi, 1.3 sökn | 0.82 | 41 % multi, 1.7 sökn | 0.97 | 0.86 |

**`expect_mode` möts på 3 av 12** vid fast katalog (6 av 12 minst en gång vid
blandad). Fältet har aldrig prövats mot en planerare förut: i
`test_golden_crossdoc.py` bygger `_script()` planen **ur** `expect_mode` och
rad 62 jämför sedan resultatet med samma fält. Den här mätningen är fältets
första oberoende konsument.

### r01 — och varför den ibland fungerar

r01 är hela motivet: styrelsen frågar om "sophämtningen", handlingen heter
*Sophantering och gårdsskötsel* och säger "schablonbelopp". Inget ord matchar,
och en distraktor (`Sophamtning.pdf`) matchar frågans ord perfekt utan att
besvara den. Enkel sökning: 0.00 vid varje `searchWeighting`.

Vid fast katalog väljer planeraren `single` tio gånger av tio och skickar
frågans egna ord vidare. Resultatet blir identiskt med enkelsökningen: **0.00**.

Vid blandad katalog väljer den `multi` åtta gånger av tio, och de åtta planerna
är åtta olika. De som lyckas ser ut så här:

```
Avtal Sophantering och gardsskotsel 2022 | Prisjustering sophämtning | Faktura sophämtning
Sophantering avtal pris | Sophantering fast pris | Sophantering ersättning
sophämtning pris | sophämtning avtal | sophämtning kostnad     ← denna ger 0.00
```

Bron mellan `sophämtning` och `sophantering` är **dokumentets namn, avskrivet
ur katalogen** — inte svensk morfologi. Planeraren översätter när den råkar
fästa vid rätt filnamn i listan, och katalogordningen avgör om den gör det.
Det ger tre konsekvenser värda att skriva ner:

- Värdet hänger på att handlingar är **välnamngivna**. En förening med
  `Scan_2022_004.pdf` har ingen bro att låna.
- Ordningsberoendet är inte slump utan en **verklig produktionsvariabel** som
  ingen har designat.
- XS-66:s hypotes (teckenbaserade n-gram mot svensk morfologi) angriper samma
  glapp på ett sätt som inte beror på filnamn. Den bör vägas mot det här, inte
  mot "kan lyfta r01" som redan är motbevisat aritmetiskt.

## Resultat — negativa kontroller (46 enkelsökningsfrågor, 10 körningar)

| | fixed | shuffled |
|---|---:|---:|
| Fall som valde `multi` i **varje** körning | **14 av 46** | 4 av 46 |
| Fall som valde `multi` i **någon** körning | 14 av 46 | **23 av 46** |
| Fall som valde `clarify` i någon körning | 2 | 5 |
| Fall vars läge varierade mellan körningar | 0 | 20 |
| Medelantal sökningar (idealet är 1.0) | **1.57** | **1.60** |
| Medelrecall, planerarens delfrågor | 0.96 | 0.94 |
| Medelrecall, enkel sökning (baslinje) | **1.00** | **1.00** |

**Överutlösningen köpte ingenting.** Baslinjen är 1.00 på alla 46 fall — en
enda sökning hittar beviset varje gång. Planeraren ligger under den, och
kostar 57–60 % fler sökningar plus ett modellanrop per fråga.

### Varje recallförlust är en `clarify`, aldrig en `multi`

De fall där planeraren hamnade under baslinjen är `g33`, `g41` (fixed) och
`g21`, `g23`, `g33`, `g41`, `g43` (shuffled). **Samtliga har `clarify` i sin
lägesfördelning.** Ingen `multi`-utlösning sänkte recall.

Det delar upp regressionen i två olika saker:

| | Vad som händer | Kostnad |
|---|---|---|
| **Överutlösning (`multi`)** | 3 sökningar i stället för 1, plus ett modellanrop | Latens och beräkning. Svaret blir inte sämre. |
| **Falsk `clarify`** | **noll** sökningar, ingen hämtning alls, styrelsen får en motfråga | Frågan besvaras inte trots att beviset ligger en sökning bort |

Två frågor får `clarify` tio gånger av tio vid fast katalog:

- `g33` — "När hålls nästa styrelsemöte?" (baslinje 1.00)
- `g41` — "Hur stort är det samlade underhållsbehovet?" (baslinje 1.00)

Det är den felmod produkten är byggd för att undvika, uppnådd från fel håll:
inte ett påhittat svar, utan en vägran att leta. `PLANNER_CONTRACT` säger "Är du
osäker: välj single" — den regeln gäller valet mellan `single` och `multi`, och
säger ingenting om när `clarify` är befogat.

## Vad detta betyder

1. **Hämtningsstrategin är inte problemet.** Handskrivna delfrågor når 1.00 på
   r01. Planeraren är den svagaste länken, precis som `crossdoc-fanout.md`
   förutsade.
2. **Vid fast katalog levererar den planerade vägen inte funktionens motiv** och
   är en nettokostnad på enkelsökningspopulationen.
3. **`clarify` är en spärr utan tröskel.** Den är den enda av de tre lägena som
   kan göra en besvarbar fråga obesvarad, och den har inget mätvärde som skulle
   ha fångat det förrän nu.
4. Siffrorna gäller `gemma-4-12b-it` Q4_K_XL. En annan modell kan bete sig
   annorlunda — men harnesset finns nu, och kostar tio minuter att köra om.

## Reproduktion

```bash
cd backend
ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan &      # OBS: -lan, inte tailnet-aliaset
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
BRF_LLM_TIMEOUT_S=300 HF_HUB_OFFLINE=1 \
  .venv/bin/python -m scripts.eval_planner --runs 10 --catalogue both
```

Ungefär 25 minuter på en obelastad maskin. Kör den **inte** parallellt med
pytest-sviten — två sviter plus mätningen slog maskinen i minnestak och båda
stannade.

---

## Tillägg 2026-08-13: sorterad katalog

Mätningen ovan pekade ut dokumentkatalogens ordning som en **verklig men
odesignad produktionsvariabel**: `ask_planned` skickade
`[m.name for m in documents.values()]`, alltså uppladdningsordning, och 22 av 59
fall bytte läge när den blandades. Det är åtgärdat — `multihop.catalogue_names`
sorterar katalogen (casefold först, rånamn som tiebreak), så planen är en
funktion av vilka handlingar som finns, inte av i vilken ordning de laddades upp.
Låset heter `test_catalogue_order_is_the_corpus_not_its_upload_history`.

Det gör `shuffled`-varianten inert. Harnesset observerar det i stället för att
låta tabellen se stabil ut: `Run.catalogue_changed` räknar hur många körningar
som faktiskt fick en annan prompt, och rubriken skriver ut "0 av N — katalogen
sorteras, så omblandningen är inert och tabellen mäter INTE stabilitet".
`--catalogue` defaultar därför till `fixed`.

**Sorterad katalog är en tredje prompt.** Den är varken den gamla `fixed` eller
någon av de blandade, så siffrorna nedan är en ny mätning, inte en omtolkning.

### Tvärdokumentsfallen — sorterad katalog

Girig avkodning gör en körning per fall till hela sanningen för en given prompt.
r01 kördes ändå tre gånger som kontroll: **multi×3, recall 1.00 varje gång.**

| Fall | Läge | Recall | Enkel baslinje | Mot uppladdningsordning |
|---|---|---:|---:|---|
| x00 two_document_answer | single | 1.00 | 1.00 | oförändrat |
| x01 multi_part_question | single | 1.00 | 1.00 | oförändrat |
| x02 clarification | clarify | — | — | oförändrat |
| x03 conflicting_documents | single | 1.00 | 1.00 | oförändrat |
| x04 no_evidence_refuses | single | — | — | oförändrat |
| x05 time_bound_question | single | 1.00 | 1.00 | oförändrat |
| x06 vocabulary_gap | multi | 1.00 | 0.50 | oförändrat |
| r00 vocabulary_gap | single | 1.00 | 1.00 | oförändrat |
| **r01 vocabulary_gap** | **multi** | **1.00** | **0.00** | **0.00 → 1.00** |
| r02 conflicting_documents | single | 1.00 | 1.00 | oförändrat |
| v00 vocabulary_gap | multi | 1.00 | 1.00 | oförändrat |
| **v01 vocabulary_gap** | **multi** | **0.00** | **1.00** | **1.00 → 0.00** |
| v02 vocabulary_gap | multi | 1.00 | 1.00 | 0.00 → 1.00 |
| **medel** | 38 % multi, 1.7 sökn | **0.91** | **0.86** | 0.82 → 0.91 |

Tvärdokumentsmängden går från **0.04 under** baslinjen till **0.05 över** den.
Det är fem fall som rör sig, inte en trend: r01 och v02 upp, v01 ner.

### r01 — motivfallet fungerar nu

r01 är det enda verkliga fall där enkel sökning får 0.00: styrelsen frågar om
"sophämtningen", handlingen heter *Sophantering och gårdsskötsel* och säger
"schablonbelopp", och distraktorn `Sophamtning.pdf` matchar frågans ord perfekt
utan att besvara den.

Med sorterad katalog väljer planeraren `multi` och når **1.00**, tre gånger av
tre. Mekanismen är den som redan beskrevs ovan: bron mellan `sophämtning` och
`sophantering` är **dokumentets namn, avskrivet ur katalogen**. Sorteringen
avgjorde inte att bron finns — den avgjorde att planeraren ser samma katalog
varje gång, och för den här korpusen är det en katalog där den fäster vid rätt
filnamn.

Två saker som därför står kvar oförändrade från analysen ovan:

- Värdet hänger fortfarande på **välnamngivna handlingar**. En förening med
  `Scan_2022_004.pdf` har ingen bro att låna, och sortering ger den ingen.
- Att resultatet vänder på en sorteringsändring säger att marginalen är tunn.
  Ett fall är ett fall.

### Negativa kontroller — sorterad katalog (46 frågor)

| | uppladdningsordning | sorterad |
|---|---:|---:|
| Fall som valde `multi` | 14 av 46 | **14 av 46** |
| Fall som valde `clarify` | 2 (g33, g41) | **4 (g21, g23, g33, g43)** |
| Medelantal sökningar (idealet 1.0) | 1.57 | **1.50** |
| Medelrecall, planerarens delfrågor | 0.96 | **0.91** |
| Medelrecall, enkel sökning (baslinje) | 1.00 | **1.00** |

**Båda regressionerna står kvar.** Överutlösningen är oförändrad — 14 av 46
frågor kostar tre sökningar plus ett modellanrop utan att hitta något som en
sökning inte hittade (varje `multi`-fall ligger på 1.00, precis som baslinjen).
Den falska `clarify` blev fler fall, inte färre: fyra besvarbara frågor får noll
sökningar och recall 0.00 mot en baslinje på 1.00.

Uppdelningen från mätningen ovan håller alltså exakt: **ingen recallförlust kom
från en `multi`. Varje förlust är en `clarify`.**

### Vad tillägget ändrar, och vad det inte ändrar

| Slutsats ovan | Efter sortering |
|---|---|
| "Vid fast katalog levererar den planerade vägen inte funktionens motiv" | **Faller.** r01 går 0.00 → 1.00. |
| "Överutlösning är en nettokostnad utan recallvinst" | Står. 14 av 46, 1.50 sökningar mot idealets 1.0. |
| "`clarify` är en spärr utan tröskel" | Står, och blev värre: 2 → 4 fall. |
| "Katalogordningen är en odesignad produktionsvariabel" | Åtgärdad, med lås. |
| "Siffrorna gäller `gemma-4-12b-it` Q4_K_XL" | Står. |

### Reproduktion av tillägget

```bash
cd backend
ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan &      # OBS: -lan, inte tailnet-aliaset
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
  uv run python -m scripts.eval_planner --runs 1 --catalogue fixed
```

Ungefär fem minuter. Samma varning som ovan: kör den inte parallellt med
pytest-sviten.

---

## Tillägg 2026-08-13 (2): clarify efter hämtning, degraderad överutlösning

Tillägget ovan lämnade två regressioner öppna: falsk `clarify` (4 av 46) och
överutlösning (14 av 46). Två ändringar gjordes mot dem, och mätningen kördes om
en gång på **samma sorterade katalog** — planeraren avkodar girigt, så en
körning per fall är hela sanningen för en given prompt.

**Steg 2 — `clarify` blir ett beslut EFTER hämtning.** `ask_planned` söker på
originalfrågan innan motfrågan får verka; når något över `minRelevance` faller
clarify och frågan söks som `single`. Kostnad: en sökning på varje clarify, två
på en räddad fråga (räddningen lämnar tillbaka till den *oförändrade*
enkelvägen i stället för att återanvända träffarna). Noll extra modellanrop.
Lås: `test_clarify_stands_when_retrieval_finds_nothing`,
`test_clarify_is_overruled_when_retrieval_finds_material`.

**Steg 3 — en `multi` som inte tillför ordförråd degraderas.** `plan_query`
jämför delfrågornas innehållsord (`indexer.tokenize`, funktionsord bort) med
frågans egna; är varje delfråga en delmängd blir planen `single`. Lås:
`test_multi_that_only_repeats_the_question_is_degraded_to_single`,
`test_multi_that_translates_into_the_documents_vocabulary_survives`,
`test_a_function_word_is_not_a_contribution`. Alla fem låsen är brutna på riktigt
och sedda falla.

`QueryPlan.downgraded_from` bär vilket läge planeraren *bad* om när
applikationen överrullade den, och harnesset räknar och skriver ut det — annars
hade en överrullad plan sett ut som ett `single` planeraren själv valde, och båda
stegen varit omätbara.

### De fyra talen

| | före steg 2/3 | efter |
|---|---:|---:|
| g21 `Med hur mycket höjdes årsavgifterna 2026?` | clarify, recall 0.00, 0 sökn | **single (←clarify), recall 1.00, 2 sökn** |
| g23 `Hur hög var soliditeten?` | clarify, recall 0.00, 0 sökn | **single (←clarify), recall 1.00, 2 sökn** |
| g33 `När hålls nästa styrelsemöte?` | clarify, recall 0.00, 0 sökn | **single (←clarify), recall 1.00, 2 sökn** |
| g43 `Vad beräknas takomläggningen kosta?` | clarify, recall 0.00, 0 sökn | **single (←clarify), recall 1.00, 2 sökn** |
| Överutlösning, 46 negativa kontroller | 14 av 46 (30 %) | **14 av 46 (30 %) — oförändrat** |
| r01, recall | 1.00 (multi×3) | **1.00 (multi)** |
| Recall, hela kontrollpopulationen | 0.91 | **1.00** — lika med baslinjens 1.00 |
| Medelantal sökningar, kontrollerna (idealet 1.0) | 1.50 | 1.70 |

Falsk `clarify` är **4 → 0**. Recallglappet mot baslinjen är stängt: den
planerade vägen når nu samma 1.00 som enkel sökning på den population som
dominerar verklig användning. Sökkostnaden steg från 1.50 till 1.70, eftersom de
fyra räddade frågorna gick från noll sökningar till två.

### Fynd 1 — steg 3 utlöste inte en enda gång

**Applikationen degraderade 0 av 59 planer från `multi`.** Överutlösningen är
oförändrad, och tabellen ovan visar det i stället för att antyda en förbättring.

Premissen bakom steg 3 håller inte. Alla 14 `multi`-planer på kontrollerna
tillför nya innehållsord — planeraren hackar inte upp frågan, den **översätter**,
precis som regel 1b begär:

| fråga | delfrågor | nya ord |
|---|---|---|
| g14 `Vilket år byggdes fastigheten?` | byggår · uppförande · fastighetsdata | alla tre |
| g26 `Vad ersätts de gamla fönstren med?` | fönsterbyte · fönsterrenovering · fönsterutbyte | alla tre |
| g20 `Hur stora är föreningens lån?` | låneuppgifter · skuldsättning · låneresumé | alla tre |

Överutlösning är alltså **inte** "delfrågorna upprepar frågans ord". Det är
"planeraren översätter en fråga som inte behövde översättas" — och en
delmängdsregel kan per konstruktion aldrig se skillnad på en översättning som
behövdes och en som inte gjorde det, eftersom båda ser likadana ut i texten.
Skillnaden syns först i hämtningen.

Regeln är därför **verkningslös kod på verklig planerarutdata**, grön i
enhetstesten och tyst i produktionen. Den ena sak den bevisligen gör är att den
inte skadar: r01:s plan (`sophamtning pris | sophamtning avtal | sophamtning
kostnad`) överlever, eftersom `sophamtning` inte är frågans `sophämtningen`.

### Fynd 2 — steg 2 tar den äkta `clarify` med sig

`minRelevance` mäter om korpusen **har material**, inte om frågan **pekar ut ett
dokument**. En fråga som är tvetydig mellan två handlingar hämtar bra ur båda, så
regeln överrullar den också:

- **x02** (`När går avtalet ut?`, golden-fallet för tvetydighet, två avtal i
  korpusen) blev `single` och besvarades ur det som råkade ranka högst.
- Enhetsfallet `Vad står det i dokumentet?` likaså.

Två test är därför **röda** och har medvetet inte skrivits om:
`tests/test_golden_crossdoc.py::test_golden_crossdoc_case[x02]` och
`tests/test_multihop.py::TestPlannedAnswering::test_clarify_refuses_instead_of_guessing`.
Att ändra dem vore att skriva om kravet så att det passar koden. Svit: **1347
passerade, 2 fallerade, 3 hoppade**.

Netto för `clarify` som läge: falska försvann, äkta försvann också. Efter
körningen valde **0 av 59** fall `clarify`.

### Vad tillägget ändrar, och vad det inte ändrar

| Slutsats i tillägg 1 | Efter steg 2/3 |
|---|---|
| "Fyra besvarabara frågor får noll sökningar" | **Faller.** 4 → 0, alla fyra på recall 1.00. |
| "Recall 0.91 mot baslinjens 1.00 på kontrollerna" | **Faller.** 1.00 mot 1.00. |
| "Överutlösning: 14 av 46 utan recallvinst" | **Står oförändrat.** Steg 3 utlöste noll gånger. |
| "`clarify` är en spärr utan tröskel" | Tröskeln finns nu — och släpper igenom allt, äkta tvetydighet inkluderad. |
| "r01 går 0.00 → 1.00" | Står. Oförändrat 1.00. |

### Reproduktion

```bash
cd backend
ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan &      # OBS: -lan, inte tailnet-aliaset
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
  uv run python -m scripts.eval_planner --runs 1 --catalogue fixed
```

Cirka två minuter med `--runs 1`. Kör den inte parallellt med pytest-sviten.
Raden `Applikationen överrullade planeraren i N av M körningar` under varje
tabell är den som säger om steg 2 och steg 3 gjorde något alls.

### Efterspel — steg 3 borttaget, och den billiga fixen för fynd 2 finns inte

**Steg 3 är borttaget ur koden.** En regel som utlöst 0 av 59 gånger på den enda
riktiga mätning som finns är verkningslös kod som *ser ut som* en åtgärd: den
läser som om överutlösningen vore hanterad, och den är inte det. Kvar står en
kommentar i `query_plan.py` med siffran och premissen som föll, så att ingen
skriver den igen utan att först mäta att den utlöser. De tre enhetslåsen togs
bort med den — ett lås på en regel som aldrig utlöser är samma vakuositet en
nivå upp. Överutlösningen står **oåtgärdad på 14 av 46** och siffrorna ovan
gäller oförändrat, eftersom regeln aldrig påverkade dem.

**Fynd 2 har ingen billig fix.** Den självklara särskiljaren — "överrulla bara
clarify när materialet ligger i ETT dokument" — mättes innan den föreslogs, och
den separerar inte:

| fall | dokument över `minRelevance` |
|---|---:|
| x02 (äkta tvetydighet, ska förbli clarify) | 6 |
| g21 (falsk clarify, ska räddas) | 4 |
| g33 (falsk clarify, ska räddas) | 4 |
| g43 (falsk clarify, ska räddas) | 3 |
| g23 (falsk clarify, ska räddas) | 1 |

Ingen tröskel på dokumentantal räddar g21/g33/g43 och behåller x02. `minRelevance`
mäter om korpusen **har material**, och spridning mäter bara hur brett — ingen av
dem mäter om frågan **pekar ut** en handling, vilket är vad tvetydighet är.

Det lämnar tre vägar, alla med känd kostnad och alla produktbeslut:

| väg | kontrollrecall | falsk clarify | äkta clarify |
|---|---:|---:|---|
| **A. behåll steg 2** (nuläget) | **1.00** | 0 av 46 | borta — 0 av 59 fall valde clarify |
| **B. återställ steg 2** | 0.91 | 4 av 46 | bevarad |
| **C. överrulla bara vid ett dokument** | 0.93 | 3 av 46 | bevarad |

Koden står på **A**, och de två röda testen är A:s pris utskrivet.

---

## Tillägg 2026-08-13 (3): `clarify` borttaget ur kontraktet — och r01 föll tillbaka

Tillägg 2 lämnade `clarify` i ett tillstånd som inte gick att försvara: grinden
räddade alla fyra falska motfrågor och tog den enda äkta med sig, så läget
utlöste 0 av 59 gånger till någon nytta. **Läget är därför borttaget ur
`PLANNER_CONTRACT`**, tillsammans med efterhämtningsgrinden (som därmed blev
onåbar kod), `QueryPlan.clarification` och wire-fältet `AskResponse.clarification`.
Kontraktet har två lägen: `single` och `multi`.

Valet mellan att behålla grinden och att ta bort läget avgjordes av att de gör
**samma sak på alla 59 fall** — de fyra falska besvaras, den äkta besvaras — men
borttagningen gör det med en sökning i stället för två, utan grind och utan ett
wire-fält som alltid är null. Bevisningen för skadan var fyra fall ur den golden
produkten mäts mot; bevisningen för nyttan var ett konstruerat fall.

Låsen: `test_clarify_left_the_contract_and_cannot_come_back_through_the_model`
(en modell som ändå svarar `clarify` måste SÖKA), `test_an_off_contract_clarify_is_answered_not_refused`,
`test_an_off_contract_clarify_never_blocks_the_question` (API-nivå, skiljer på
`low_relevance` och den gamla `insufficient_data`-genvägen) och den frusna
fältmängden i `test_ask_response_exposes_no_actionable_field`. Alla tre nya
brutna på riktigt och sedda falla. Golden-fallet **x02 är borttaget**, inte
omskrivet — motiveringen ligger i `eval/golden_crossdoc.json`s `_comment`.

### Vad mätningen gav

| | tillägg 2 (clarify + grind) | nu (clarify borta) |
|---|---:|---:|
| Recall, 46 negativa kontroller | 1.00 | **1.00** |
| Överutlösning | 14 av 46 | **12 av 46** |
| Medelantal sökningar, kontrollerna | 1.70 | **1.52** |
| Falsk `clarify` | 0 (via grind) | **0 (strukturellt)** |
| Planeraren svarade utanför kontraktet | — | **0 av 58 körningar** |
| **r01, recall** | **1.00** | **0.00** |
| v01, recall | 0.00 | **1.00** |
| Recall, tvärdokumentsfallen | 0.91 | 0.91 |

Kontrollpopulationen blev alltså bättre på varje axel. Och så det som inte är en
detalj:

### Fynd 3 — r01 vänder på en promptändring som inte rör ordförrådsglappet

**r01 planeras nu `single` och får recall 0.00.** Fallet är motivet för hela
funktionen: styrelsen frågar om "sophämtningen", handlingen säger
"sophantering" och "schablonbelopp", och en enkel sökning hittar ingenting.

Det som ändrades var att ett stycke om ett **annat läge** togs bort ur
systemprompten. Ingenting i regel 1 eller 1b rördes, ingenting i hämtningen,
ingenting i katalogen. Avkodningen är girig, så planen är en funktion av
prompten — och den funktionen visade sig gå åt andra hållet.

Det är tredje gången r01 vänder på en ändring som inte handlar om fallet:

| ändring | r01 |
|---|---|
| uppladdningsordnad katalog | 0.00 |
| sorterad katalog | 1.00 |
| `clarify` borttaget ur kontraktet | **0.00** |

Slutsatsen är inte att borttagningen var fel — kontrollpopulationen, som är den
verkliga användningen, blev bättre på varje axel, och v01 gick åt andra hållet
(0.00 → 1.00) i samma körning. Slutsatsen är att **det ena verkliga
ordförrådsfallet inte bär någon vikt**: dess utfall bestäms av promptdetaljer
som inte har med ordförrådsglapp att göra. Villkor C i
[`fan-out-mvp-beslut.md`](fan-out-mvp-beslut.md) — reproducera vinsten på minst
tre verkliga fall, varav ett utan filnamnsbro — är efter det här inte en
formalitet utan hela frågan.

### Vad som står kvar oåtgärdat

Överutlösningen: **12 av 46** frågor kostar tre sökningar och ett modellanrop
utan att hitta något en sökning inte hittade (varje `multi`-fall ligger på 1.00,
precis som baslinjen). Regeln som skulle mäta bort den är borttagen som
verkningslös (tillägg 2, efterspel), och ingen ny har satts i dess ställe.

---

## Tillägg 2026-08-14 (4): vad överutlösningen faktiskt gör med prompten

Överutlösningen står oåtgärdad på 12 av 46, och varje mätning hittills har sagt
"recall oförändrad". Det har lästs som *slöseri men ofarligt*. Det är en slutsats
måttet inte kan bära: **recall mäter om beviset finns i påsen, inte vad som
ligger bredvid det.**

`backend/scripts/eval_fanout_delta.py` (ny) kör den riktiga `ask_planned` med den
plan `eval_planner` redan spelat in, utan modellanrop, och jämför fan-outens
bevispåse med vad enkelsökningen hade lagt fram.

| | tvärdokument (4 multi) | negativa kontroller (12 multi) |
|---|---:|---:|
| Nya utdrag fan-outen lade till | 16 | **27** |
| …av dem som bär svaret | **1** (x06) | **0** |
| Utdrag enkelsökningen hade och fan-outen tappade | 7 | **18** |
| …av dem som bar svaret | 0 | 0 |

**Överutlösningen är inte ett nollsummeslöseri — den byter ut prompten.** På de
12 kontrollerna lade fan-outen till 27 utdrag av vilka inte ett enda bär svaret,
och trängde undan 18 som enkelsökningen hade valt. På fem av fallen (g03, g04,
g16, g26, g41) är påsen exakt lika stor som enkelsökningens sex: där är det inte
utspädning utan **ren utbyteshandel**, två användbara-eller-neutrala utdrag mot
två som inte kan hjälpa.

Att inget av de 18 undanträngda bar svaret är ett **utfall, inte en garanti**.
Undanträngning är precis mekanismen bakom en recallförlust, och vi har sett den
inträffa: v01 låg på 1.00 → 0.00 i tillägg 2:s körning, och är 1.00 igen nu.

### Vad det gör med villkor B

Villkor B i [`fan-out-mvp-beslut.md`](fan-out-mvp-beslut.md) lyder "överutlösning
≤ 2 av 46, **eller** bevis för att de extra sökningarna köper recall". Andra
ledet går inte att uppfylla eller falsifiera med harnesset som finns:
syntessteget är kanonsvarat i varje mätning, så **svarskvalitet under utbytt
bevispåse har aldrig mätts**. Recall är det instrument som säger att allt är
bra. Skadan, om den finns, ligger i det instrumentet inte tittar på.

Det är en anmärkning på villkorets formulering, inte ett omprövat grindbeslut.

### En kandidat, mätt men inte byggd

Sista kolumnen i harnesset prövar ett efterhämtningsfilter: *släpp igenom bara
utdrag vars confidence når enkelsökningens egen toppträff.* Utfallet:

- **22 av 27** diluterande utdrag på kontrollerna faller bort.
- x06:s enda nyttiga nya utdrag (0.721 mot enkelsökningens topp 0.255)
  **överlever** — vinsten går inte förlorad.
- Fem utdrag överlever ändå på kontrollerna (g08 ×2, g11, g17, g41).

Den är **inte implementerad.** Skälet är samma som fällde steg 3: dess nytta
kan inte mätas med harnesset som finns, eftersom nyttan är svarskvalitet och
syntesen är kanonsvarad. Att bygga den nu vore att skeppa en åtgärd vars effekt
ingen kan se — vilket är exakt det fel som just har rättats en gång.

---

## Tillägg 2026-08-14 (5): den utbytta bevispåsen ändrade ingenting i svaret

Tillägg 4 visade att en överutlösande `multi` byter ut prompten — 27 utdrag in,
18 ut — och drog slutsatsen att skadan låg där mätinstrumentet inte tittade.
**Den slutsatsen höll inte. Skadan är mätt nu, och den finns inte på den här
populationen.**

`backend/scripts/eval_fanout_answer.py` (ny) kör **riktig syntes två gånger per
fall** på samma fråga och samma korpus, och skiljer bara på vilken bevispåse
modellen ser: enkelsökningens topK mot fan-outens påse. Måttet är produktens
eget ur `scripts/eval.py` — citerades rätt handling, pekar markeringen på rätt
sida och ruta — så ingen ny poängskala uppfanns för experimentet.

| | baslinje (enkel) | fan-out |
|---|---:|---:|
| Rätt handling citerad | **12 av 12** | **12 av 12** |
| Rätt markering | **12 av 12** | **12 av 12** |
| Vägran | 0 | 0 |
| Avvisade citat | 0 | 0 |
| **Svar som skilde sig** | | **0 av 12** |

Svaren är **ordagrant identiska på alla tolv fallen**. Inte "lika enligt måttet"
— samma text, tecken för tecken.

**Icke-vakuositeten är observerad, inte antagen.** Harnesset jämför de två
syntesprompterna och avbryter om de är identiska; det gjorde de aldrig.
Utdragsantalet skilde sig på sex av fallen (6→5, 6→7, 6→8, 6→9 ×2, 6→7) och på
de övriga sex var antalet lika men innehållet ett annat. Alla 24 syntesanrop
gick till den riktiga modellen.

### Vad det gör med villkor B

Villkor B går nu att svara på, och svaret är entydigt: **de extra sökningarna
köper ingenting, och de kostar ingenting i svarskvalitet.** Överutlösning är en
kostnad i sökningar, ett modellanrop och latens — inte en risk för svaret.

Det retirerar tillägg 4:s oro utan att retirera dess mätning: undanträngning
*är* mekanismen bakom en recallförlust, och v01 visade den falla ut åt fel håll
en gång. Men på frågor enkelsökningen redan besvarar överlever det svarsbärande
utdraget undanträngningen och dominerar prompten, och de tillagda utdragen
ignoreras.

### Vad mätningen inte säger

Tolv fall, en modell, den rekonstruerade korpusen, och bara den population där
enkelsökningen redan får 1.00. Den säger ingenting om ett fall där fan-outen
tränger undan det enda utdrag som bar svaret — det är fortfarande möjligt, och
det är fortfarande v01:s felmod.

Kandidatfiltret från tillägg 4 (confidence-golv vid enkelsökningens toppträff)
är därmed **avfärdat, inte uppskjutet**: det skulle ta bort 22 av 27 utdrag som
bevisligen inte gör någon skada.

---

## Tillägg 2026-08-14 (6): läsbarheten är inte längre den bindande gränsen

Mätningen 2026-08-12 (`d32e606`) räknade textlager i en verklig förenings arkiv,
fann att sju av nio handlingar saknade ett, och drog slutsatsen att **läsbarheten,
inte sökstrategin, var den bindande begränsningen**. Den slutsatsen gäller inte
längre: OCR-vägen kopplades in efter den mätningen (`app/store.py` →
`app/ocr.py`, tesseract med svenskt språkstöd), och ingen har mätt vad den ger.

`backend/scripts/eval_real_corpus.py` (ny) kör produktionens **egen**
ingestionsväg över arkivet — samma dokumentnivådispatch, samma OCR — och
rapporterar enbart siffror. Arkivets sökväg är ett argument, aldrig inbakad.

### Läsbarhet efter OCR — nio verkliga handlingar

| | sidor | ord/sida | ordlika tokens | tid |
|---|---:|---:|---:|---:|
| Två med textlager (digitala) | 13, 36 | 166, 104 | **75 %, 75 %** | 0 s |
| Sju utan textlager (OCR:ade) | 3–30 | **118–437** | **82–95 %** | 5–36 s |

**Alla sju OCR:ades utan fel**, på 99 sekunder tillsammans. Andelen ordlika
tokens är genomgående **högre** i de OCR:ade handlingarna än i de två digitala —
inte för att OCR är bättre, utan för att ett textlager också innehåller
tabellceller, sidhuvuden och tal. Det gör 75 % till den rimliga baslinjen för
"läsbar", och de sju ligger över den.

Villkor C är alltså inte längre blockerat av läsbarhet.

### Screening av glappet — och varför den inte är villkor C

Arkivet innehåller en forskningssammanställning med **14 källbelagda par**
*styrelsens ord → dokumentets ord*. Kört mot den OCR:ade korpusen visar **2 av
14** r01:s mönster: styrelsens ord under `minRelevance`, dokumentets över.

Den siffran ska inte läsas som "glappet finns knappt". Screeningen
**underdetekterar systematiskt**, och gör det på precis den mekanism r01 handlar
om: r01:s skada var att en distraktor matchade frågans ord *perfekt* utan att
besvara den. Ett confidence-mått kan inte skilja en sådan träff från en riktig,
så varje par där styrelsens ord landar högt men i fel handling räknas som "inget
glapp". Tio av de fjorton paren landade i olika handlingar för de två
ordförråden — hur många av dem som är den felmoden vet vi inte.

### Vad villkor C nu kräver

Inte mer teknik. Ett verkligt fall kräver ett **utpekat svarsstycke**, alltså att
någon läser handlingarna och markerar var svaret står. Det är den enda återstående
insatsen, och den går inte att ersätta med en numerisk gallring — det är just vad
det här tillägget försökte och misslyckades med.

Två saker gör det arbetet mindre än det låter: läsbarheten är löst, och
kandidatlistan är 14 par med källor, inte ett blankt papper. Två av dem (nr 11 och
13) är dessutom redan utpekade som troliga.

Villkorets skärpning står kvar oförändrad: minst ett fall där handlingens
**filnamn inte** innehåller det överbryggande ordet. Efter fynd 3 i tillägg 3 är
det den delen som avgör, eftersom r01:s utfall vände tre gånger på promptdetaljer
och alltså inte bär villkoret ensamt.

---

## Tillägg 2026-08-14 (7): villkor C uppfyllt — på verklig text, utan filnamnsbro

Villkor C i [`fan-out-mvp-beslut.md`](fan-out-mvp-beslut.md): *ordförrådsvinsten
reproducerad på minst tre verkliga fall, varav minst ett där handlingens filnamn
inte innehåller det överbryggande ordet.* Det var det villkor som återstod, och
det som fynd 3 gjorde till hela frågan — r01 vände tre gånger på promptdetaljer
och bar det inte ensamt.

**Villkoret är uppfyllt.** Åtta fall byggda ur två verkliga avtal ur en
förenings arkiv; tre visar vinsten, och alla tre saknar bro i filnamnet.

| fall | enkel sökning | fan-out | enkelsökningens toppträff |
|---|---:|---:|---|
| R1 kan en boende få en egen reserverad p-plats | 1.00 | 1.00 | rätt handling |
| R2 kan vi säga upp med en månads varsel | 1.00 | 1.00 | fel handling |
| **R3 vem betalar om en bil blir skadad** | **0.00** | **1.00** | fel handling (0.32) |
| R4 betalar vi fortfarande fast pris för sophämtningen | 1.00 | 1.00 | fel handling |
| **R5 vad är det för extra avgift på fakturorna** | **0.00** | **1.00** | fel handling (0.42) |
| R6 hur stor del av kostnaderna ska vi betala | 1.00 | 1.00 | fel handling |
| **R7 måste de säga till innan de höjer priset** | **0.00** | **1.00** | fel handling (0.26) |
| R8 när kan vi tidigast säga upp avtalet | 1.00 | 1.00 | fel handling |

De tre vinsterna är samma mekanism varje gång, och den är *inte* r01:s: bron går
inte via filnamnet utan via avtalets fackord, som styrelsen aldrig skulle skriva.
Styrelsen frågar *vem betalar om bilen blir skadad*, avtalet säger **friskrivning**.
Styrelsen frågar *vad är det för extra avgift*, avtalet säger
**administrationskostnad**. Styrelsen frågar *måste de säga till först*, avtalet
säger **varsko om betydande prisjusteringar**. Inget av de orden står i något
filnamn.

Det gör villkoret uppfyllt med marginal: det krävde ett fall utan filnamnsbro
och fick tre.

### Ett större fynd vid sidan av: toppträffen är fel handling i sju av åtta

Kolumnen längst till höger var inte det mätningen letade efter. **I sju av åtta
fall låg enkelsökningens toppträff i fel avtal** — och i fyra av dem fanns rätt
stycke ändå med bland de sex som når prompten, så recall räknar dem som träffar.

Det är en annan felmod än den som mätts hittills, och den syns inte i något
befintligt tal. Produkten visar citat med sidhänvisning: en styrelse som får rätt
svar med fel avtal överst har fått något som *ser* verifierat ut och pekar på fel
handling. Nio handlingar räckte för att framkalla det; ett riktigt arkiv har
hundratals.

Det här tillägget mäter det inte vidare — det noteras som ett eget fynd, med den
population det vilar på (åtta fall, ett arkiv).

### Hur facit togs fram, och vad som aldrig lämnade arkivet

Innehållsklassificeraren hindrar bulkläsning av korpusen, och den kringgicks inte.
Arbetsgången blev i stället: **Simon beskrev två handlingar med sina egna ord, och
sidnumren slogs upp ur indexet med hans beskrivning som ingång — endast metadata
(dokument, sida, confidence) lästes ut.** Ingen avtalstext har lästs ur arkivet,
och ingen finns i fallfilen, som ligger kvar i arkivkatalogen och aldrig committas.

Frågorna är skrivna i styrelsens ordförråd, delfrågorna i avtalets. Metodiken är
`eval_crossdoc.py`:s — planeraren hålls utanför med flit, så villkor C mäter
**hämtningsstrategin**. Att en riktig modell *väljer* de här delfrågorna är en
annan fråga, och tillägg 3 visade att den frågan är den svaga länken.

Kör om: `uv run python -m scripts.eval_real_corpus --archive <arkiv> --fall <fall.json>`.

---

## Tillägg 2026-08-14 (8): budgetkontrollen fäller två av tre — och rättar tillägg 7

Tillägg 7 rapporterade tre verkliga ordförrådsvinster och drog slutsatsen att
villkor C var uppfyllt med marginal. **Den slutsatsen var fel, och felet var en
kontroll som inte kördes.**

Jämförelsen ställde fan-out mot enkel sökning med `topK = 6`. Men fan-outens
bevispåse rymmer upp till `MAX_EVIDENCE_CHUNKS = 10`. De två sidorna hade alltså
inte samma budget, och skillnaden tillskrevs ordförrådet.

### Kontrollen

Samma frågor, samma korpus, enkel sökning med bredare budget:

| fall | topK=6 | topK=10 | topK=20 |
|---|---:|---:|---:|
| R3 vem betalar om en bil blir skadad | 0.00 | **1.00** | 1.00 |
| R5 vad är det för extra avgift | 0.00 | **1.00** | 1.00 |
| R7 måste de säga till innan de höjer | 0.00 | 0.00 | **1.00** |
| R7b får leverantören höja utan att meddela | 0.00 | 0.00 | **0.00** |

**Två av de tre vinsterna var budget, inte ordförråd.** R3 och R5 löses av att
enkel sökning får samma tio platser som fan-outen redan hade. R7 löses vid tjugo.
Bara **R7b** står emot — och R7 och R7b är samma underliggande fråga i två
formuleringar.

Rätt siffra är därför: **ett distinkt ordförrådsglapp i elva verkliga fall**, inte
tre av åtta. Villkor C är uppfyllt på formuleringens bokstav och inte på dess
mening; formuleringen sa inte att baslinjen skulle vara budgetmatchad, och det
borde den ha gjort.

### Vad som ändå står kvar från tillägg 7

Mätningen är inte värdelös, bara felaktigt sammanfattad. Det som håller:

- **R7b är ett äkta glapp på verklig avtalstext, utan bro i filnamnet.** Styrelsen
  frågar *får leverantören höja priset utan att meddela oss först*; avtalet säger
  *varsko om betydande prisjusteringar*. Ingen budgetbreddning hittar det — inte
  ens tjugo utdrag.
- **Enkelsökningens toppträff låg i fel handling i 7 av 8 fall.** Budget rättar
  inte det; det gör bara att rätt stycke smyger med längre ner i listan.

### Planeraren, mätt mot det verkliga arkivet

Den mätning som hela grindfrågan hängde på (se
[`brf1-vad-som-fattas.md`](brf1-vad-som-fattas.md)) kördes samtidigt, och dess
resultat påverkas inte av budgetfelet — den mäter om planeraren *väljer* rätt, inte
om valet slår baslinjen.

| | utfall |
|---|---:|
| Fall planerade som `multi` | **10 av 11** |
| Fall där planeraren nådde svarsstycket | **11 av 11** |

Planeraren skriver bron själv: på R7b valde den `prisjustering · kostnadsökning ·
ändring av pris` utan att frågan innehöll något av orden. Robusthetsvarianterna
(R3b/R5b/R7b, skrivna utan motpartens namn efter att namnet visat sig vara en
genväg jag själv lagt in) gav 3 av 3.

**Det är ett annat resultat än på den rekonstruerade korpusen**, där samma modell
överutlöste på 12 av 46 utan nytta och tappade motivfallet r01. På verkliga
handlingar väljer den `multi` nästan alltid, och den har rätt varje gång. Skillnaden
mellan korpusarna är att `golden.json`s frågor per konstruktion besvaras av en
sökning — baslinjen är 1.00 rakt igenom — medan ett verkligt arkiv innehåller frågor
där den inte gör det. Skäl 1 i [`fan-out-mvp-beslut.md`](fan-out-mvp-beslut.md)
("på den population som dominerar verklig användning är vägen sämre") vilar på att
`golden.json` är representativ, och det antagandet är nu ifrågasatt utan att vara
motbevisat.

### Den billigare åtgärden

Den mätning som faller ut ur kontrollen är inte om fan-out ska på, utan att
**`topK = 6` är för snävt**. Att höja till 10 återvinner två av tre apparenta
vinster till noll extra sökningar och noll modellanrop — och tillägg 5 mätte redan
att fler irrelevanta utdrag i prompten inte ändrade ett enda svar, vilket är den
invändning en breddning annars skulle mötas av.

Det är en inställningsändring med egen räckvidd — den träffar hela produkten, inte
bara den planerade vägen — och den är inte gjord här. Men den ska vägas *före*
fan-out, eftersom den är gratis.

---

## Tillägg 2026-08-14 (9): handlingens namn i indexet — och varför det inte räcker på svenska

Extern researchgenomgång (Grok, aug 2026) rangordnade **dokumentmedveten
hämtning** som första åtgärd mot "fel handling överst", med DAPR
(arXiv:2305.13915) som belägg: att lägga dokumentets identitet framför stycket
lyfter nDCG@10 med upp till 38 punkter på just de frågor vars sammanhang sitter i
handlingen och inte i stycket. Det är exakt felmoden i tillägg 7 — toppträffen låg
i fel avtal i 10 av 11 verkliga fall.

Berikningen i `app/enrich.py` la redan **år + avsnittsrubrik** i söktexten. Den la
inte handlingens **namn**. Nu gör den det, med separatorer omgjorda till
mellanslag så att `Avtal_Teknisk-forvaltning_2022.pdf` bidrar med de ord en
styrelse skriver. Invarianten är oförändrad och nu låst i båda riktningar:
namnet når indexet, aldrig det citerbara utdraget
(`test_document_name_is_searchable_but_never_citable`, bruten på båda sätten och
sedd falla).

### Vad det gav

| sökning | utan namnet | med namnet |
|---|---|---|
| `T2SECUREPRINT2` | fel handling (0.21) | **rätt handling (0.65)** |
| `parkeringsavtalet` | fel handling (0.77) | **rätt handling (0.79)** |
| `Ekebäckshöjd` | oförändrad | oförändrad |
| **11 verkliga fall, hela frågor** | 10/11 fel handling överst | **10/11 — oförändrat** |
| **16 frågor, ändrad toppträff** | — | **0** |

Ändringen fungerar, och den ändrar ingenting på riktiga frågor.

### Varför — och det är fyndet

`parkeringsavtalet` som ensam sökning hittar nu rätt. Samma ord inuti meningen
*"Vad står i parkeringsavtalet om uppsägning?"* gör det inte: `uppsägning` och
`står` drar mot en annan handlings uppsägningsklausul, och namnsignalen väger
för lätt för att hålla emot.

Under det ligger ett mekaniskt skäl. BM25 här har **ingen sammansättningsdelning
och ingen stamning**. `parkeringsavtalet` är ett enda token. Det matchar varken
`parkering` eller `avtal` — och det är just de orden filnamnet bidrar med.
Namnsignalen finns alltså bara för den som råkar skriva exakt det sammansatta
ordet, medan svenskan gör det motsatta: en styrelse skriver *parkeringsavtalet*,
*sophämtningsavtalet*, *underhållsplanen* i ett ord.

Researchunderlaget rangordnade dokumentmedveten omrankning som åtgärd 1 och
svensk morfologi som åtgärd 2, som två oberoende spår. **På svenska är de inte
oberoende.** Dokumentidentiteten är själv en sammansättning som användaren skriver
ihop, så namnet i indexet biter först när delningen finns. Åtgärd 1 utan åtgärd 2
är mätbart verkningslös på naturliga frågor — det är den här mätningen.

### Vad som är gjort och vad som inte är det

Namnet ligger kvar i indexet. Det kostar ingenting, det skadade ingen mätning
(11 fall oförändrade, noll försämringar), och det gör ensamma namnsökningar rätt.
Men det ska inte redovisas som en åtgärd mot fel-handling-överst förrän
sammansättningsdelningen finns, eftersom det inte är det förrän då.

Nästa steg enligt underlaget är därför **sammansättningsdelning + stamning på
BM25-sidan**, inte omrankning. Det är den starkast belagda svenska lexikala
åtgärden (CLEF: delning + stamning +25,3 % MAP, signifikant; stamning ensam +1,7 %,
inte signifikant) och det är förutsättningen för att namnet i indexet ska göra
någon nytta. En sak att kontrollera innan: OFFO:s svenska avstavningsfil har en
licens som kan hindra att den paketeras i RPM:en.
