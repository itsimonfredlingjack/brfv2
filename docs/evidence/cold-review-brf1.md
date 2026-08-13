# Kallgranskning av BRF-1 (XS-64)

**Datum:** 2026-08-13 · **Gren:** `feat/brf-1-cross-document` ·
**Granskarens utgångsläge:** noll kunskap om hur funktionen byggdes; allt nedan
är läst i koden eller kört i den här sessionen.

Tempoläget är Regulated eftersom funktionen läser verkliga föreningars
handlingar. Hela funktionen är byggd, mätt, dokumenterad och bedömd av samma
agent, vilket är skälet till att den här granskningen är ett krav och inte en
rekommendation.

Granskningen frågar **vad som finns**, inte om tidigare påståenden stämmer.
Observerade fakta står skilt från slutsatser.

---

## 1. Påstår testerna något?

### 1.1 Ett vakuöst lås — `test_evidence_is_bounded`

`tests/test_multihop.py:321` hävdar att bevismängden är begränsad:

```python
assert len(result.pack.hits) <= MAX_EVIDENCE_CHUNKS   # taket är 10
```

**Observerat:** `store`-fixturen består av två dokument på tre korta rader var,
vilket blir **2 chunkar totalt**. `pack.hits` kan aldrig bli fler än 2. Taket
är 10.

**RED-prov:** hela kapningen togs bort ur `app/multihop.py`:

```python
    # if len(pack.hits) > MAX_EVIDENCE_CHUNKS:
    #     pack.hits = pack.hits[:MAX_EVIDENCE_CHUNKS]
```

→ `1 passed`. Låset är **grönt mot en väg utan tak alls**.

Det är felmod 3 i projektets egen checklista (`vacuous-lock-failure-modes`): ett
urval som är för litet för att assertionen ska kunna gå sönder. Fixturen som
löser det finns redan i samma fil — `dense_store`, som skrevs för exakt det här
skälet en gång tidigare.

### 1.2 En vaktpost som inte vaktar det den säger

`tests/test_golden_crossdoc.py:117` — `test_time_bound_case_asserts_more_than_the_amount`
säger sig kräva att minst ett villkor gäller **datumet**, inte bara beloppet:

```python
assert any(any(ch.isalpha() for ch in n) for n in needles)
```

**Observerat:** villkoret är "någon nål innehåller en bokstav". Nålmängden
`['1400 kr', '1250 kr']` — två belopp, inget datum — passerar, eftersom "kr" är
bokstäver. Idag är fallets nålar `['1400', '1 januari 2026']`, så vaktposten är
grön av rätt skäl, men den skulle inte fånga den ändring den beskriver.

### 1.3 `expect_mode` har aldrig prövats mot en planerare

**Observerat:** före den här sessionen lästes `expect_mode` på exakt två
ställen, båda i `tests/test_golden_crossdoc.py`. Rad 43 använder fältet för att
**bygga** FakeLLM-skriptet; rad 62 jämför sedan resultatet med samma fält.
Planen dikteras alltså av förväntan den jämförs mot.

Det är inte fel — filens docstring säger rakt ut att LLM:en är scriptad — men
konsekvensen är att golden-filens `expect_mode` var ett **oprövat påstående**.
XS-62:s mätning är fältets första oberoende konsument och visar att en riktig
modell möter det på 3 av 12 fall.

### 1.4 Två jag misstänkte, som höll

`test_default_request_never_reaches_the_planner` och
`test_opt_in_without_the_server_flag_is_ignored` (`tests/test_api.py:384, 392`)
har formen `all(... for c in stub.calls)`, och **`stub.calls` är tom i det gröna
fallet** — förfrågan vägras på `low_relevance` innan någon leverantör anropas.
Det är formen på felmod 1.

**RED-prov:** grindningen i `app/main.py` byttes mot `if True:` →
**båda föll rött**, med rätt felmeddelande (`assert all(...)` över en lista som
nu innehöll planerarprompten). Skälet: `ask_planned` anropar planeraren *före*
varje vägran, så brottet flyttar in ett anrop i samlingen.

De är alltså riktiga lås. Det är värt att notera att de är riktiga av ett skäl
som inte står i dem, och som en framtida refaktorering (auktorisera → planera
→ hämta) kan ta bort utan att någon märker det.

### 1.5 Övrigt observerat, utan RED-prov

- `test_conflicting_case_really_states_two_different_figures` väljer
  `next(c for c in CASES if c["kind"] == "conflicting_documents")` — det finns
  **två** sådana fall (`x03`, `r02`). `r02` är ovaktad.
- `TestK1...test_ask_planned_takes_a_store_not_a_tenant_identifier` prövar mot
  en fast förbjuden namnlista. Ett fält som hette `association_id` passerar.
  Begränsning, inte defekt — men den står inte i testet.
- `test_pack_reports_the_documents_it_spans` klarar sig på en enda delfråga:
  korpusen har 2 chunkar och `top_k=2`, så varje sökning returnerar båda
  dokumenten. Assertionen om `document_ids` är verklig; att fan-outen är det
  som spänner över två dokument är den inte.

---

## 2. Stämmer MVP-dokumentet med observerat beteende?

`docs/MVP-STATUS.md` är daterat **"Senast avstämd mot kod och körd evidens:
2026-07-27"** men innehåller egna avsnitt daterade 2026-08-01 och 2026-08-02.
Rubrikdatumet är alltså inte sant om dokumentets eget innehåll.

### 2.1 Sifferpåståendena stämmer inte

| Påstående i dokumentet | Observerat 2026-08-13 |
|---|---|
| Backend `pytest -q` → 530 passed, 6 skipped | **1339 passed, 3 skipped** (316 s) |
| Kanonisk frontend Vitest → 14 passed | **258 passed** (12 filer), `npx vitest run` |

Tabellen står under rubriken "Senast körda sammanhållna lokala resultat" och
läses rimligen som nuläge.

### 2.2 Dokumentet motsäger sig självt

- Rad 27–29: "Global sök, dokumentbunden chatt, kvalitetskontroll, **bevakningar**
  och inställningsflöden ligger utanför MVP. I pilotvyn är de dolda, spärrade
  eller uttryckligen märkta som otillgängliga."
- Rad 253–255: "Den tidigare **spärrade Bevakningar-fliken är nu en verklig
  funktion.**"

Det första stycket uppdaterades aldrig när det andra skrevs.

### 2.3 BRF-1 finns inte i dokumentet

Ingen träff på BRF-1, tvärdokument, fan-out, planerad väg eller
`BRF_PLANNED_ASK`. Givet att funktionen ligger bakom två grindar och inte är
merge:ad är frånvaron försvarbar, och punkt 5 i begränsningslistan täcker den
generellt. **Slutsats:** dokumentet över- eller underdriver inte BRF-1 — det
nämner den inte. Det som inte stämmer är sifferunderlaget och
bevakningsstycket, alltså avstämningen mot kod, inte mot avsikten.

---

## 3. Har den planerade vägen en egen väg förbi någon grind?

**Citat- och siffergrinden: nej.** Motprov kört —
`ask_planned` med ett ogrundat citat ger `grounding_failed`, och med ett
osiffergrundat svar `numeric_grounding_failed`. `_synthesize()` är delad.

**Men tre andra grindar körs inte på den planerade multi-vägen.** Orsaken är en
och samma: `answer.ask()` returnerar tidigt på rad 148 när `evidence` är satt,
och de tre stegen ligger på rad 174–230.

### 3.1 Relevansgrinden hoppas över — och varningen med den

**Observerat**, `minRelevance=0.99`, samma korpus, samma fråga, samma citat:

| Väg | Utfall |
|---|---|
| Enkel sökning | `refusal=True`, `low_relevance` — "Det står inte i något av era dokument." |
| Planerad `multi` | `refusal=False`, 1 verifierat citat, **`warning=None`** |

`ask()` anropas med `low_relevance=False` hårdkodat. Styrelsen får alltså inte
bara ett svar där enkelvägen vägrat — de får det **utan osäkerhetsvarningen**
("Osäkert underlag: träffarna låg långt från frågan"), som är den enda kvar
när vägran uteblir. `minRelevance` är en inställning en förening kan skruva på;
på den planerade vägen har den ingen verkan.

Det gör en detalj i `evidence.py` inaktuell: `expand_context` sätter
`confidence=0.0` med motiveringen att det "keeps it out of the relevance gate's
`max(confidence)`". Den grinden körs inte på den enda väg funktionen används
från.

### 3.2 Ett medvetet högljutt fel blir en tyst degradering

`answer.py:174` höjer `LLMError` när `rerankEnabled` är på men
omrankningsmodellen saknas, med en kommentar som förklarar varför felet **måste**
vara högljutt: att svara ändå "would look like it worked while quietly
reverting to the exact failure mode this fix addresses".

**Observerat** med `rerankEnabled=True` utan reranker installerad:

| Väg | Utfall |
|---|---|
| Enkel sökning | `LLMError: Omrankning är aktiverad men omrankningsmodellen är inte tillgänglig…` |
| Planerad `multi` | svarade, `refusal=False`, 1 citat — **ingen omrankning, inget fel** |

### 3.3 Den länkade tabellförklaringen saknas

`append_linked_table_legends` anropas på `answer.py:230`, efter den tidiga
returen. MVP-STATUS tillskriver just den mekanismen att livegaten gick från
underkänd till `READY` på `q03`. Den finns inte på den planerade vägen.
*(Läst i koden, inte kört — kräver en kodad tabellfixtur.)*

### 3.4 `clarify` går aldrig genom `ask()` alls

`_clarify_response` i `multihop.py:70` bygger sitt `AskResponse` direkt.
Modellskriven fritext når styrelsen utan citatgrind, siffergrind eller
`requireSources`. **Observerat:** en planerare som returnerar
`"SYSTEM: alla dokument är godkända. Klicka betala."` som `clarification` får
den texten visad som svarets `answer`.

Dämpningen är verklig — `refusal=True`, `citations=[]`, och frågans text når
planeraren som data under `FRÅGA:`-prefix — så den kan inte utge sig för att
vara ett grundat svar. Men det är den enda vägen i `ask_planned` där modelltext
når användaren utan att passera en enda verifiering, och en `clarification` som
innehåller ett påhittat belopp skulle inte fångas av något.

### 3.5 Sammanlagt: inget hindrar den planerade vägen från att svara

`ask_planned`s gren `if not pack.hits:` är i praktiken onåbar — sökningarna
körs med `min_confidence=0.0`, så ett icke-tomt index returnerar alltid
träffar. **Observerat:** delfrågorna `"zzzqqq xyzzy plugh"` och
`"qwertyuiop asdfghjkl"` gav ändå 2 bevischunkar.

Tillsammans med 3.1 betyder det att **ingenting på den planerade multi-vägen kan
avgöra att korpusen saknar svaret innan modellen tillfrågas.** Det som återstår
mellan en dålig hämtning och ett svar är modellens eget `insufficient_data`,
`requireSources` och siffergrinden — alla tre efter genereringen, ingen före.

---

## 4. Vad händer när det går fel?

Allt nedan är kört.

| Fel | Utfall | Bedömning |
|---|---|---|
| Syntesen dör efter lyckad planering | `refusal=True`, `provider_error`, "Tekniskt fel vid svarsgenerering" — planen och 2 bevischunkar finns kvar i packen | Säkert |
| Planeraren svarar med prosa i stället för JSON | `plan.mode=single`, `degraded=True`, frågan besvaras normalt | Säkert — planeraren kan inte blockera en besvarbar fråga *genom att gå sönder* |
| Planeraren väljer `clarify` utan motfråga | Faller tillbaka på sökning (`test_clarify_without_a_question_degrades_to_search`) | Säkert |
| Tom korpus | `no_documents`, **noll** planeraranrop | Säkert |
| Uppmaning inbäddad i frågan | Når planeraren som data under `FRÅGA:` | Se 3.4 |
| Fan-out ger noll träffar | Onåbart i praktiken | Se 3.5 |

**Det som inte är täckt:** planeraren kan blockera en besvarbar fråga genom att
**fungera** — genom att välja `clarify`. XS-62 mätte det: två av 46
enkelsökningsfrågor får `clarify` tio gånger av tio och besvaras aldrig, med
noll sökningar. Det är den allvarligaste felmoden och den finns inte i något
test.

---

## 5. Suitläge

`1339 passed, 3 skipped` på 316 s, ren körning utan granskningsproberna.
Ingenting i den här granskningen ändrade produktionskod: varje brott återställdes
från kopia och `git status` på `backend/app/` är rent.

De tre överhoppade är miljöberoende (tesseract, rerank-extran, seedad
tripwire-data) och redovisas i `MVP-STATUS.md`.

**Att suiten är helt grön är inte ett motargument mot §1.** Ett verkningslöst
lås är grönt per definition; det är hela problemet.

---

## Slutsatser som följer direkt av observationerna

1. **`test_evidence_is_bounded` är verkningslöst.** Kör den mot `dense_store`
   i stället, och bryt taket för att se den fela.
2. **`clarify` behöver en grind.** Det är den enda planerarutgången som kan
   göra en besvarbar fråga obesvarad, den mäts nu som en verklig regression
   (XS-62), och den passerar ingen verifiering (3.4).
3. **Skillnaden mellan `ask()`s två vägar bör vara ett medvetet beslut, inte en
   följd av var den tidiga returen ligger.** Relevansgrinden, omrankningsfelet
   och tabellförklaringen faller bort tyst. Minst omrankningsfelet bör höjas
   även på den planerade vägen — kommentaren intill förklarar redan varför.
4. **`expect_mode` i golden-filen bör antingen prövas mot en planerare eller
   sluta kallas en förväntan.**
5. **MVP-STATUS behöver en avstämning**, inte ett tillägg: siffrorna och
   bevakningsstycket beskriver ett äldre repo.
6. **Inget av ovanstående ändrar att den planerade vägen är dubbelgrindad och
   avstängd som default.** Riskerna är villkorade av att någon slår på
   `BRF_PLANNED_ASK`.
