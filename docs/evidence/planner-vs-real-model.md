# Planeraren mot en riktig modell (XS-62)

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
