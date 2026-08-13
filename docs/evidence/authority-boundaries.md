# BRF-5: authority- och säkerhetskriterier för BRF-1 (XS-61)

**Datum:** 2026-08-13 · **Gren:** `feat/brf-1-cross-document` ·
**Lås:** `backend/tests/test_authority_boundaries.py`

Jira BRF-5 beställer uttryckliga acceptanskriterier och regressionskontroller
för de gränser den planerade tvärdokumentsvägen inte får försvaga. Det här
dokumentet listar kriterierna och var vart och ett bevisas. Kriterierna själva
bor i testfilen, inte här — det här är RED-protokollet.

**Regeln XS-61 sätter:** ett kriterium vars enda stöd är "koden ser rätt ut"
räknas inte som uppfyllt. Fyra av de sju gränserna hölls redan i praktiken men
var bara *härledda ur kodläsning*. De har nu lås. Tre bevisades redan av
befintliga tester och skrivs inte om.

## Kriterierna och deras bevis

| # | Gräns | Bevisas av | Status |
|---|---|---|---|
| K1 | Strukturell tenant-isolering | `TestK1TenantIsolationIsStructural` (3 lås) | **nytt** |
| K2 | Suverän inferens | `TestK2SovereignInference` + `test_model_endpoint.py` | **nytt** (delvis) |
| K3 | Citerbar PageData/Word-proveniens | `test_multihop.py::TestPlannedAnswering::test_ungrounded_citation_is_still_rejected_on_the_planned_path` | fanns |
| K4 | Refuse-over-fabricate | `…::test_empty_corpus_refuses_without_planning` · `test_api.py::TestPlannedAskFlag::test_clarify_is_distinguishable_from_an_ordinary_refusal` | fanns |
| K5 | Ingen modellauktoritet över pengar/externa skrivningar | `TestK5AskingIsReadOnly` | **nytt** |
| K6 | Mänskliga godkännandegränser | `TestK6TheAskSurfaceStaysAdvisory` (2 lås) | **nytt** |
| K7 | Deterministisk validering före mutationer | `…::test_numeric_gate_still_applies_on_the_planned_path` | fanns |

## Vad K1 medvetet *inte* gör

Det självklara isoleringstestet — "en fråga i förening A returnerar inte B:s
hemlighet" — är **vakuöst i den här arkitekturen** och är därför inte skrivet.
Varje tenant har sin egen `Store` med sitt eget `HybridIndex`; det finns inget
delat index att läcka igenom, så assertionen hade varit grön oavsett isolering.
Det är exakt den felmod som en extern granskning fångade tidigare i BRF-1: ett
canary-mönster lånat från en shared-index-arkitektur, korrekt där, meningslöst
här.

Den egenskap som faktiskt kan gå sönder är **store-upplösningen**: kan något
klientstyrt fält peka ut en annan förening? Det är vad de tre K1-låsen mäter.

## RED-protokoll

Ett obrutet lås är inte verifierat. Varje lås bröts i appkoden (inte i testet),
kördes rött, och koden återställdes från kopia — inte med `git checkout`, som
enligt CLAUDE.md hade slängt andra ostagade ändringar i samma fil.

| # | Brott (i appkoden) | Utfall |
|---|---|---|
| 1 | `ask_planned` får parametern `brf_id: str = ""` | RÖTT — `{'brf_id', …}` i signaturen |
| 2 | `AskRequest` får fältet `source_brf` | RÖTT — frusen fältmängd bruten |
| 3 | `AskResponse` får fältet `approve_invoice_id` | RÖTT — frusen fältmängd bruten |
| 4 | `tenant_store`: `role_for(...) or "member"` | RÖTT — icke-medlem fick 200, frågan nådde modellen |
| 5 | Syntesanropet får `provider=None` och löser upp själv | RÖTT — `leverantören löstes upp 2 gånger` |
| 6 | `ask_planned` skriver `ask_log.jsonl` till tenantkatalogen | RÖTT — `{'ask_log.jsonl': '6bba29c4…'}` |
| 7 | En ny rutt `POST /api/brf/{brf_id}/ask-planned` | RÖTT — frågeytan har växt |

### K5:s vakuositetsgrindar är också prövade

K5 hävdar först att korpusen finns, att planen blev `multi`, att bevischunkar
nådde prompten och att svaret inte vägrades — och mäter skrivningar först
därefter. En grind som aldrig prövats är själv en gissning, så båda de
väsentliga bröts:

| Grind | Utfall |
|---|---|
| Planen faller tillbaka till `single` | RÖTT — `planen blev single, inte multi — fan-outen kördes aldrig` |
| Inga bevischunkar når prompten | RÖTT — `vägen kortslöts före skrivrisken` |

Utan dessa hade ett skrivlås mot en kortsluten väg passerat och sett ut som ett
bevis.

## Ett vakuöst lås till — mitt eget, fångat efter första gröna körningen

K6:s ruttlås skrevs först som `{r.path for r in app.routes if "ask" in
getattr(r, "path", "")}`. Det passerade brott 7, och såg färdigt ut. Det var
verkningslöst på två sätt samtidigt:

1. **Det såg 19 av 75 rutter.** FastAPI 0.139 lägger allt som monteras med
   `include_router` bakom ett `_IncludedRouter` som saknar `.path`. `getattr(…,
   "path", "")` gav tom sträng för dem, tyst. Hela integrations-, faktura-,
   uppgifts-, bevaknings- och hemsideytan var osynlig för låset — alltså
   precis de ytor där de mänskliga godkännandegränserna faktiskt bor.
2. **`tasks` innehåller delsträngen `ask`.** Så fort vandringen lagades hade
   delsträngsmatchningen fällt låset av fel skäl. Ett lås som felar av fel skäl
   lär folk att ignorera det.

Rättat: vandringen följer `original_router` rekursivt, och matchningen går på
sista segmentet. Två nya RED-körningar:

| Brott | Utfall |
|---|---|
| Ny `POST /ask` monterad via integrations-routern | RÖTT — `frågeytan har växt: ['/api/brf/{brf_id}/ask', '/ask']` (det gamla låset hade varit grönt) |
| Vandringen regredierar till naiv `app.routes` | RÖTT — `ruttvandringen når inte router-monterade rutter` |

Den andra är kanariefågeln som gör att felet inte kan komma tillbaka tyst.

**Det här är sessionens femte vakuösa test, och det första jag skrev själv i en
fil vars uttryckliga syfte var att undvika dem.** Mönstret är stabilt nog att
formulera som en regel: `getattr(x, "attr", default)` i en assertion döljer
strukturen den påstår sig läsa. Ett lås över en samling måste först bevisa att
samlingen innehåller det den ska täcka.

## Vad K2 täcker och inte

`app/model_endpoint.py` validerar **vilken** adress som är tillåten (bara
loopback eller adress i det egna nätet; alla domännamn avvisas) och bevisas av
`tests/test_model_endpoint.py`. Det som saknades var om BRF-1 tyst skaffat sig
en *andra* inferensväg: planeraren är ett extra modellanrop, och ett anrop som
löser upp sin egen leverantör kan gå någon annanstans än svaret gör. K2 låser
att planering och syntes delar en och samma redan upplösta leverantör.

**Kvar otäckt:** att endpointen är suverän i drift — alltså att den konfigurerade
adressen faktiskt pekar på egen hårdvara — är en driftfråga, inte en
kodegenskap, och kan inte låsas här.

## Suitläge

`1339 passerade, 3 överhoppade` (från 1332 före XS-61; +7 nya lås).

## Rättelse som gäller det här kortet

Mätarbetet i commit `a987843` etiketterades felaktigt som BRF-5. Det hörde
aldrig hit — BRF-5 är det här, och var orört fram till nu. Mätningen ligger i
`crossdoc-fanout.md`.
