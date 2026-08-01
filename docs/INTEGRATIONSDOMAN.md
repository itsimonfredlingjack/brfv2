# Integrationsdomänen — inkommande underlag och read-only fakturagranskning

Det här blocket gör produkten till ett **intelligens- och evidenslager** ovanpå
de system föreningen redan har. Det är inte ett ekonomisystem, inte en
mejlklient och inte en integrationsplattform. Det tar emot underlag, normaliserar
det, jämför det mot föreningens egna dokument och lägger fram ett *fynd* som en
människa avgör.

Allt slutar före extern åtgärd. Det finns ingen kodväg som skriver tillbaka
någonstans, och den frånvaron är strukturell — se §3.

## 1. Domänen

Tre poster, ingen av dem uppkallad efter en leverantör.

### `SourceEvent` — något har kommit in

`app/integrations/models.py`

| Fält | Innebörd |
| -- | -- |
| `tenant_id`, `source_type` | Vilken förening, och vilken *sorts* källa (`email`). Aldrig vilket program som skickade det. |
| `received_at` / `occurred_at` | När vi tog emot det, och när källan säger att det hände. Två olika frågor: ett mejl som importeras sex veckor sent får inte se ut att ha kommit idag. |
| `external_ref` | Källans egen identifierare (`Message-ID`). Används för spårbarhet, aldrig som tillitsankare — det är text avsändaren kontrollerar. |
| `content_sha256` | SHA-256 av originalbytena. Det är den här som bär dubblettkontrollen. |
| `provenance` | Metod, adapter, originalfilnamn, storlek, vem som importerade och när. |
| `origin`, `origin_display`, `recipients`, `subject`, `body_text` | Vem det kom från och vad det säger sig handla om. |
| `attachments` | Varje bilaga med filnamn, typ, storlek, hash och det `document_id` den blev. |
| `import_status` | `imported` eller `rejected`. Det finns inget `partial` — se §4. |
| `review_status` | `open` → `approved` / `dismissed` / `corrected`. |
| `linked_document_ids` vs `suggested_document_ids` | Bekräftat av en människa respektive föreslaget av systemet. Två fält, aldrig ett: en kö som blandar ihop dem lär sina användare att lita på gissningar. |

### `InvoiceSnapshot` — en ögonblicksbild, inte en post

Leverantör, referens, datum, period, belopp, valuta, moms, rader, originalkälla
och hash. **Inget bokföringstillstånd som appen får ändra** — inte för att det
är bortglömt, utan för att det inte finns någon kodväg som kunde skriva ett.

Belopp är `Decimal`, aldrig `float`, och serialiseras som JSON-*sträng*.
`12500.10 != 12500.099999999999` spelar roll när en jämförelse avgör om ett fynd
säger *överensstämmer* eller *möjlig avvikelse*.

### `ReviewFinding` — ett fynd, inte ett beslut

| Fält | Innebörd |
| -- | -- |
| `verdict` | `matches` / `possible_deviation` / `cannot_be_verified` — svenska etiketter i `verdict_label`. |
| `verified_facts` | Vad som faktiskt är fastställt, uppdelat på `invoice` och `document`. |
| `citations` | `CitationOut` — samma typ, samma verifiering och samma rektanglar som ett svars citat. |
| `suggestion` + `suggested_by` | Systemets förslag i klartext, och vem som skrev det. Idag `regelmotor`, för det är vad det är. |
| `uncertainty` | Vad som **inte** gick att fastställa. Obligatoriskt för allt utom en ren match. |
| `status`, `decided_by`, `decided_at`, `decision_note` | Det mänskliga ställningstagandet. |

## 2. Var data ligger

Per tenant, i tenantens egen katalog:

```
tenants/<brf_id>/integrations/
    meta.json            {"schemaVersion": 1}
    source-events.json
    invoices.json
    findings.json
```

Filerna skrivs atomärt med läge `0600`.

Det här är inte en stilfråga. Isoleringsmodellen i den här backenden är
objektgraf- och filsystemsseparation, inte frågefiltrering (`app/registry.py`).
En SQLite-tabell med `tenant_id`-kolumn hade infört produktens **första delade
samling** — och därmed det första stället där en glömd `WHERE` läcker en
förenings leverantörsfakturor in i en annans kö. Här finns ingen sådan samling:
ett `brf_id` löser upp till en katalog, och den katalogen är det enda stället
posterna finns. `registry.delete()` sveper dem med allt annat, utan att någon
behöver komma ihåg det.

`Store.integrations` är lat och stämplar `tenant_id` från butiken, aldrig från
anroparen — samma disciplin som håller `corpus_origin` ärlig i `add_document()`.

## 3. Adaptergränsen

`app/integrations/protocols.py` vägrar, **vid import**, att definiera ett
adapterprotokoll med en metod vars namn är ett utåtriktat skrivverb:
`send`, `archive`, `update`, `approve`, `attest`, `post`, `book`, `pay` och ett
fyrtiotal till. Att lägga till `def send_reply(...)` ger inte en
granskningskommentar sex veckor senare; det ger ett `ImportError` första gången
något i paketet importeras, inklusive varje testkörning.

Kontrollen matchar på namn, vilket är en verklig begränsning och sägs vara det:
en metod som heter `fetch` men gör POST skulle passera. Den är en snubbeltråd
mot den drift som faktiskt inträffar — någon utökar en adapter för att datan
ändå ligger där. Beviset att ingen skrivväg finns är att ingen av de levererade
adaptrarna importerar en HTTP-klient eller nämner ett URL-schema över huvud
taget, vilket testas separat.

Två adaptrar levereras:

* **`EmlFileAdapter`** — läser en fil användaren pekat ut. Ingen brevlåda, ingen
  credential, ingen mapp, inget schema. Därav *fil*adapter, inte mejladapter.
  Det finns medvetet ingen `list_messages`: en brevlådelistning är första steget
  i kontinuerlig synk.
* **`FixtureAccountingAdapter`** — läser syntetiska fixturfiler från disk.
  Payloaden är formad som en leverantörsfakturaexport ur ett svenskt
  ekonomisystem, så att mappningen är den riktiga övningen. En framtida adapter
  mot ett verkligt system ersätter `_to_snapshot()` och ärver resten.

## 4. Mejlintaget

### Det format som tas emot

`app/integrations/eml.py`, och serverat på
`GET /api/brf/{brf_id}/integrations/format` så att dialogen som berättar för
operatören och koden som avgör inte kan glida isär.

* filen måste tolkas som ett MIME-meddelande och bära `From` och `Subject`;
* högst 25 MB totalt, högst 10 bilagor, högst 20 MB per bilaga;
* läsbar kropp: `text/plain`, eller `text/html` som reduceras till text;
* **varje** bilaga måste vara `application/pdf` — och innehållet måste börja med
  `%PDF-`, för en deklarerad content-type är ett påstående från avsändaren.

En bilaga utanför formatet vägrar **hela meddelandet**. Inte "PDF:er läses in och
resten noteras": en händelse som tyst tappade ett kalkylblad är en händelse vars
fullständighet inte går att lita på.

### Atomicitet

`app/integrations/intake.py` gör stegen i en fast ordning, och det är det enda
intressanta i modulen:

1. validera allt — inget är skrivet när det vägras;
2. dubblettkolla på innehållshash;
3. läs in bilagorna och kom ihåg vilka `doc_id` som landade;
4. vid fel i steg 3: **radera varje dokument som redan lagts till** genom
   produktens egen `delete_document`, och kasta;
5. skriv `SourceEvent` sist.

Händelsen skrivs sist med flit: dör processen dessförinnan har föreningen i
värsta fall några föräldralösa dokument den kan se och radera — aldrig en
köpost som pekar på dokument som inte finns.

**Dubbletter.** Samma bytes två gånger ger `409` med den befintliga händelsens
id. Samma *bilaga* i ett nytt kuvert — en vidarebefordran — länkas till det
dokument den redan blev, i stället för att läsas in igen; posten märks
`reused_existing_document`. Pilotjournalen noterade att produkten tog emot fem
bit-identiska dubbletter "utan varning eller dedupliceringsfråga"; en kö som för
den defekten vidare in i dokumentarkivet är värre, eftersom kopiorna sedan
konkurrerar i retrieval.

## 5. Faktura–avtal-granskningen

`app/integrations/review.py`. Deterministisk, inte ett modellanrop: varje siffra
i ett fynd är läst ur en passage som klarat `app.citations.resolve_citation` —
samma ordagranna kontroll, samma fel-förekomst-skydd och samma allt-eller-inget
som ett svars citat.

### Tre regler som gör skillnaden mellan ett fynd och en gissning

Alla tre kom ur den **första riktiga körningen** mot den seedade korpusen. Var
och en producerade ett verifierat, självsäkert och felaktigt fynd.

**1. En bilaga i kön är aldrig bevis.**
Den inlästa fakturan blir ett vanligt dokument: indexerat, sökbart, citerbart.
Kvar i kandidatmängden hittade granskningen "5 000 kronor" *i fakturan själv*
och rapporterade att fakturan stämmer med fakturan. Verifierat citat, tydlig
dom, noll information. Regeln som stänger det är inte en filnamnskontroll: en
inkommande bilaga är **det som granskas**, och föreningens eget arkiv är det som
granskas mot. Ett avtal som kommit per mejl räknas alltså inte som underlag
förrän någon medvetet lägger det i arkivet — en verklig begränsning, och rätt
riktning att ha fel åt.

**2. Jämför bara samma sorts kvantitet.**
Avtalet säger "1 250 kronor per timme". Fakturan går på 6 250 kr. De är inte
oense, och en regel som drar det ena från det andra säger att de är det. Belopp
klassificeras därför som `rate` (per timme, per säck, per styck), `periodic`
(per månad, per kvartal, per år) eller `plain`, och matchas bara mot en
jämförbar post på fakturan — ett à-pris mot ett à-pris, ett periodbelopp mot
fakturans periodbelopp.

**3. Granskningen ankras på leverantörens namn.**
Utan ankaret jämförde motorn ett hissbolags utryckningsavgift mot
snöröjningsavtalets timtaxa och rapporterade en "möjlig avvikelse" på 13 750
kronor. Allt i det var verifierat: beloppet stod verkligen i dokumentet, citatet
löste verkligen upp. Det var ändå nonsens, för de två talen handlade aldrig om
samma avtal. Nu gäller: om inget dokument namnger leverantören — ordagrant
verifierat, inte bara högt rankat — finns ingenting i arkivet som är bevis om
den här fakturan, och enda ärliga svaret är *kan inte verifieras*.

### Domarna

| Dom | Betyder |
| -- | -- |
| **överensstämmer** | En ordagrant verifierad passage bär ett värde som är lika med fakturans. |
| **möjlig avvikelse** | En verifierad passage bär ett jämförbart värde, och det skiljer sig. |
| **kan inte verifieras** | Inget jämförbart kunde verifieras. |

Det finns medvetet ingen fjärde dom, och särskilt inget "avviker". Att slå fast
en avvikelse vore att påstå vad avtalet *säger*; det som faktiskt är fastställt
är att den passage som hittades säger något annat — vilket inte är samma sak,
eftersom villkoret kan stå på en sida som retrieval inte lyfte fram.

### Vad den inte klarar

Belopp och ISO-daterade perioder. Ett avtal som uttrycker sitt pris som "index
enligt SCB:s entreprenadindex", eller sin löptid som "tolv månader från
undertecknande", bär inget jämförbart värde. Då blir svaret *kan inte
verifieras* i stället för en gissning — vilket är rätt svar och det en granskare
kan agera på. Den seedade snöröjningsavtalets avtalstid ("från den 1 november
2026 och tills vidare") är exakt det fallet, och används som testfall.

## 6. API

Alla under `/api/brf/{brf_id}/integrations/`, med samma `tenant_store` /
`require_admin`-beroenden som resten av produkten. Läsning kräver medlemskap;
allt som ändrar tillstånd kräver `admin`. En icke-medlem får `404`, aldrig `403`
— tenant-id:n får inte gå att sondera.

| Metod | Väg | Vad |
| -- | -- | -- |
| GET | `format` | Det accepterade formatet, ur parserns egna konstanter |
| GET | `source-events` | Kön |
| GET | `source-events/{id}` | En händelse |
| POST | `source-events` | Importera en `.eml` (admin) |
| POST | `source-events/{id}/decision` | Godkänn/avfärda/korrigera, koppla dokument (admin) |
| DELETE | `source-events/{id}` | Ta bort köposten. **Inte** kaskad: inlästa dokument ligger kvar |
| GET | `available-invoices` | Vad adaptern kan erbjuda. Att titta lagrar ingenting |
| GET | `invoices` | Inlästa ögonblicksbilder |
| POST | `invoices` | Läs in en (admin) |
| POST | `invoices/{id}/review` | Kör granskningen (admin) |
| GET | `findings` | Fynden |
| POST | `findings/{id}/decision` | Ställningstagande (admin) |

En omkörd granskning ersätter bara `open` fynd. Ett godkänt eller avfärdat fynd
är ett protokoll över ett mänskligt beslut och raderas aldrig av en ny körning.

## 7. Desktopvyn

`brfv2-mockup/src/components/Integrations.jsx`, nåbar som **Inkommande** i
sidomenyn. Posten renderas bara när `/api/desktop/state` svarar — på webben
404:ar den, så vyn finns inte där. Ingen byggflagga, ingen andra bundle.

Den visuella hierarkin bär den epistemiska: verifierade fakta läses som data,
förslaget som prosa i ett tonat block, och osäkerheten i ett *varmare* block som
inte går att skumma förbi. Varje citat är klickbart och öppnar dokumentet på
rätt sida med passagen markerad — genom appens egen citatnavigering, samma
maskineri som ett svars citat. Ett fynd vars bevis inte går att öppna är ett
påstående, inte ett fynd.

## 8. Vad som inte finns, och varför

Ingen Outlook, ingen Microsoft Graph, ingen Fortnox-OAuth, ingen API-klient,
ingen polling, ingen webhook, ingen brevlådemapp, inget utskick, inget svar,
ingen vidarebefordran, ingen extern arkivering, ingen bokföring, ingen kontering,
ingen attest, ingen betalning och ingen statusändring i ett främmande system.

Det är inte kvarvarande arbete i det här blocket. Det är blockets gräns. En
live-spik mot Outlook eller Fortnox får starta först när ägarskap, samtycke,
minsta behörighet, retention och faktiskt återkommande behov är beslutade — se
Linear-dokumentet *Genomförandeordning — desktop, mejlintag och Fortnox*.

## 9. Fixtures

`backend/fixtures/mail/*.eml` och `backend/fixtures/accounting/*.json`, allt
syntetiskt. Adresser ligger under `.example` och `.invalid` (reserverade av
RFC 2606); föreningen, leverantörerna, organisationsnumren och beloppen är
påhittade och samma som demokorpusen redan använder.

`.eml`-filerna genereras av `backend/scripts/make_integration_fixtures.py` och är
byte-stabila — `Message-ID` och MIME-gräns är fasta i stället för slumpade, för
en fixtur som ändrar sig varje gång den byggs om går inte att granska som en
diff. Ett test kör om generatorn och jämför hashar, så en committad fixtur som
generatorn inte längre reproducerar upptäcks.

## 10. Verifiering

`backend/tests/test_integrations.py` (52) — adaptergränser, formatet och dess
vägran, atomisk import, dedup, värdeutvinning, granskningens tre domar,
persistens och fixturhygien.

`backend/tests/test_integrations_isolation.py` (18) — samma sak över riktig
HTTP, med två föreningar: kön, fakturorna, fynden och bilagorna är osynliga för
den andra tenanten, en bilaga läcker inte genom retrieval, en medlem får läsa men
inte ändra, och `DELETE /api/brf/{id}` sveper integrationskatalogen.

`backend/tests/test_desktop.py` — den vertikala skivan genom desktopadapterns
exakta origin-kontroll och installationsspecifika cookie.

`brfv2-mockup/src/Integrations.test.jsx` (12) — att vyn håller isär verifierat,
föreslaget och osäkert, att ett citat navigerar dit det säger, och att en
korrigering utan förklaring vägras.

Ingenting i någon av dem behöver en credential, en nätverksendpoint eller en
körande modell. Att de inte gör det är i sig en del av det som testas — en
testsvit som behövde det skulle betyda att kodvägen gjorde det.
