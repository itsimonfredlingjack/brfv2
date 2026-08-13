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
