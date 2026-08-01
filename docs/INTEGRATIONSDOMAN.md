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

Fyra adaptrar levereras:

* **`EmlFileAdapter`** — läser en fil användaren pekat ut. Ingen brevlåda, ingen
  credential, ingen mapp, inget schema. Därav *fil*adapter, inte mejladapter.
* **`GraphMailAdapter`** — läser en **ansluten brevlåda** över Microsoft Graph.
  Se [INTEGRATION-OUTLOOK.md](INTEGRATION-OUTLOOK.md).
* **`FixtureAccountingAdapter`** — läser syntetiska fixturfiler från disk.
  Payloaden är formad som en leverantörsfakturaexport ur ett svenskt
  ekonomisystem, så att mappningen är den riktiga övningen.
* **`FortnoxAccountingAdapter`** — läser leverantörsfakturor ur ett **anslutet
  Fortnox-företag**, genom exakt den mappning fixturen övade in. Se
  [INTEGRATION-FORTNOX.md](INTEGRATION-FORTNOX.md).

### Rättelse: "ingen brevlådelistning"

Den första versionen av `protocols.py` motiverade avsaknaden av `list_messages`
med att "en brevlådelistning är första steget i kontinuerlig synk". Första
halvan var fel och andra halvan var poängen. Regeln är nu skriven som det den
alltid betydde:

> **Varje läsning sker för att en människa bad om den.**

Det finns ingen pollingslinga, ingen webhook-prenumeration, ingen delta-token
och ingen bakgrundstråd någonstans i paketet, och testsviten kontrollerar det.
Det en operatör får är en lista hen bad om att se och ett meddelande hen valde
att importera — samma form som att peka ut en fil, med filvalet gjort mot
brevlådan i stället för mot filsystemet.

### Utgående trafik

`app/integrations/egress.py` är den enda platsen produkten talar med ett system
den inte äger. Tre regler, alla tvingande:

1. **Sluten värdlista per leverantör.** En URL mot något annat vägras innan en
   socket öppnas — även efter en omdirigering, för `Location` kontrolleras med
   samma funktion som originalanropet.
2. **GET för data, POST bara för tokens.** Att läsa någons brevlåda eller
   reskontra är en GET. Den enda POST som finns är en egen metod, bunden till
   leverantörens auktoritetsvärd och dess token-sökväg. Det finns ingen allmän
   POST, ingen PUT, ingen PATCH och ingen DELETE.
3. **Hemligheter når aldrig en logg.** Loggen skriver metod, värd och sökväg.
   Query-strängen släpps hel — Graph lägger `$filter`-värden där, och en token
   kan hamna var som helst efter en dålig refaktorering.

Klassen tar sin transport som argument. I produktion är den `httpx`; i
testsviten är den en stub som kräver exakt rätt begäran. Det är därför hela
integrationen — inklusive vägranden — går att testa utan credential, utan nät
och utan inspelad trafik.

### Var credentials ligger, och inte ligger

`app/integrations/credentials.py`. Två poster per ansluten leverantör:
`Connection` (allt gränssnittet, API:et och ett supportsamtal får se — ingen
hemlighet finns i typen, så ingen route behöver komma ihåg att skala bort en)
och hemlighetsfilen (`0600` i en `0700`-katalog inne i föreningens egen
katalog, så `registry.delete()` sveper den).

**Säkerhetskopior bär inga credentials.** `create_backup` hoppar över katalogen
vid namn och skriver antalet uteslutna filer i manifestet. Följden sägs rakt
ut i stället för att döljas: efter en återställning står integrationerna som
anslutna men oanvändbara, och en administratör loggar in igen. Det är rätt håll
att ha fel åt — en refresh-token i ett arkiv som ingen behandlar som en
hemlighet är ett stående tillstånd att läsa någons brevlåda, och det överlever
varje samtal om vem som fick det.

Det finns medvetet inget krypteringslager. En nyckel som ligger bredvid sin
kryptotext skyddar mot exakt en sak, och på en enanvändarinstallation skulle
nyckeln ligga i samma hemkatalog under samma rättigheter som filen den skyddar.
Det som faktiskt skyddar de här bytena är filrättigheterna — samma skydd
`auth.db` får för lösenordshashar och levande sessioner. Att rulla ett chiffer
för att få det att se starkare ut vore värre än att säga det rakt ut.

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
granskas mot.

Fram till det här blocket betydde det att ett avtal som kommit per mejl aldrig
kunde bli underlag — konservativt, och en verklig lucka: styrelsen hade avtalet,
produkten kunde se det, och den vägrade använda det. Nu finns steget som
saknades, och det är en **handling, inte en inställning**:

* en **namngiven administratör** arkiverar bilagan, och det sparas med vem;
* hen måste säga **varför** — en mening, obligatorisk, för ett dokument som blir
  bevis på ingens uttalade ansvar är inte ett arkiv;
* det sker **per bilaga**, inte per meddelande: ett mejl med både avtal och
  faktura arkiverar avtalet och låter fakturan ligga;
* dokumentet flyttas inte och ändras inte. Det var redan inläst och citerbart;
  det som ändras är att det inte längre utesluts som bevis;
* det går att ångra. Ett oåterkalleligt beslut är ett beslut folk undviker att
  fatta, och poängen är att det ska vara lätt att göra rätt.

En fakturas **egna** bilagor är fortfarande uteslutna för just den fakturans
granskning, arkiverade eller inte. Att arkivera en faktura-PDF är fullt rimligt;
att låta den intyga sig själv är det inte.

**2. Jämför bara samma sorts kvantitet.**
Avtalet säger "1 250 kronor per timme". Fakturan går på 6 250 kr. De är inte
oense, och en regel som drar det ena från det andra säger att de är det. Belopp
klassificeras därför som `rate` (per timme, per säck, per styck), `periodic`
(per månad, per kvartal, per år) eller `plain`, och matchas bara mot en
jämförbar post på fakturan — ett à-pris mot ett à-pris, ett periodbelopp mot
fakturans periodbelopp.

**3. Granskningen ankras på leverantörens identitet.**
Utan ankaret jämförde motorn ett hissbolags utryckningsavgift mot
snöröjningsavtalets timtaxa och rapporterade en "möjlig avvikelse" på 13 750
kronor. Allt i det var verifierat: beloppet stod verkligen i dokumentet, citatet
löste verkligen upp. Det var ändå nonsens, för de två talen handlade aldrig om
samma avtal. Nu gäller: om inget dokument identifierar leverantören — ordagrant
verifierat, inte bara högt rankat — finns ingenting i arkivet som är bevis om
den här fakturan, och enda ärliga svaret är *kan inte verifieras*.

### Ankaret har en styrka, och styrkan står i fyndet

Första versionen jämförde exakt tokensekvens, vilket var fel åt andra hållet:
ett avtal som skriver "Snösvängen AB" var osynligt för en faktura från
"Snösvängen Entreprenad AB", som är samma bolag. `app/integrations/supplier.py`
avgör nu vad som ska letas efter, och `ReviewFinding.anchor_strength` bär svaret:

| Styrka | Betyder |
| -- | -- |
| `org_number` | Fakturans organisationsnummer står ordagrant i dokumentet. Två bolag kan dela firmanamn; inga delar organisationsnummer. |
| `exact` | Hela namnet står ordagrant. |
| `alias` | En människa **här** har bekräftat att de två namnen är samma leverantör. Ett beslut, sparat med vems. |
| `legal_form` | Samma namn, annan eller ingen bolagsform. |
| `partial` | Den särskiljande delen stämmer, resten inte. **Svagt.** |

Ett svagt ankare ger ett fynd — tystnad vore sämre — men fyndet måste då säga
att namnen skiljer sig, och bär ett `alias_proposal` som en människa kan
bekräfta med ett klick. Efter bekräftelsen är samma koppling stark. Det är
skillnaden mellan ett system som lär sig och ett system som antar.

Två spärrar mot att det blir slarv: en träff som bara är *början* på ett längre
namn i dokumentet degraderas alltid till `partial` (annars hade "Snösvängen"
inuti "Snösvängen Entreprenad AB" räknats som samma namn), och ett generiskt
förstaord räcker aldrig ensamt — "Svenska Hiss AB" ankrar inte på "Svenska".

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

### Villkor som inte är siffror

`app/integrations/terms.py`. Den första versionen läste belopp och ISO-datum och
svarade *kan inte verifieras* på allt annat — vilket är rätt svar när avtalet är
tyst, men gavs till klausuler en människa läser utan besvär:

> "Avtalet gäller från den 1 november 2026 och tills vidare."
> "Avtalstiden är tolv (12) månader från undertecknande."
> "Priserna indexregleras årligen enligt SCB:s entreprenadindex E84."
> "Uppsägningstiden är tre månader."

Problemet är att *kan inte verifieras* ser likadant ut oavsett om avtalet är
tyst eller om koden inte kunde läsa vad det sa, och det är två helt olika
situationer för den som ska agera. Så de läses nu, och används på tre sätt:

**En löpande avtalstid är en avtalstid.** "från den 1 november 2026 och tills
vidare" begränsar nedåt, och det räcker för att säga att en faktura ligger inom
avtalet — med förbehållet om uppsägning utskrivet, för ett avtal som löper tills
vidare är precis ett som kan ha upphört. Svenska datum (`den 1 november 2026`)
läses; ett datum utan år gissas aldrig.

**En indexklausul förbjuder en självsäker avvikelse.** Säger avtalet att priset
indexregleras är ett citerat grundbelopp som skiljer sig från fakturan inte
bevis för en avvikelse — det är bevis för att grundbeloppet inte är dagens pris.
Domen blir *kan inte verifieras* med **både** beloppet och indexklausulen
citerade, vilket är mer användbart än en "möjlig avvikelse" en granskare måste
motbevisa. Är beloppen däremot lika är det fortfarande *överensstämmer*, med
noteringen att ingen uppräkning slagit igenom.

**Ett villkor som inte går att jämföra är ändå värt att citera.** En löptid utan
känt undertecknandedatum, eller en uppsägningstid, redovisas som verifierat
faktum med sitt citat. Svaret förblir *kan inte verifieras* och säger nu vilken
klausul som lästes och varför den inte gick att jämföra.

Kvar som gräns: ett indextal räknas aldrig upp åt någon, och ett
undertecknandedatum som inte står i en citerad passage finns inte att räkna
från.

## 6. API

Alla under `/api/brf/{brf_id}/integrations/`, med samma `tenant_store` /
`require_admin`-beroenden som resten av produkten. Läsning kräver medlemskap;
allt som ändrar tillstånd kräver `admin`. En icke-medlem får `404`, aldrig `403`
— tenant-id:n får inte gå att sondera.

| Metod | Väg | Vad |
| -- | -- | -- |
| GET | `format` | Det accepterade formatet, ur parserns egna konstanter |
| GET | `connections` | Anslutningarnas status. Innehåller ingen hemlighet |
| PUT | `connections/microsoft-graph` | Konfigurera brevlådan (admin) |
| PUT | `connections/fortnox` | Konfigurera ekonomisystemet (admin) |
| POST | `connections/{p}/login` | Starta inloggning (admin) |
| POST | `connections/{p}/login/poll` | Ett svep av device code-inloggningen (admin) |
| POST | `connections/{p}/login/complete` | Lös in en inklistrad kod (admin) |
| DELETE | `connections/{p}` | Koppla bort. Allt redan importerat ligger kvar (admin) |
| GET | `mailbox/messages` | Lista den anslutna brevlådan. Bara rubrikrader (admin) |
| POST | `mailbox/messages/{id}/import` | Importera ett valt meddelande (admin) |
| GET | `source-events` | Kön |
| GET | `source-events/{id}` | En händelse |
| POST | `source-events` | Importera en `.eml` (admin) |
| POST | `source-events/{id}/decision` | Godkänn/avfärda/korrigera, koppla dokument (admin) |
| POST | `source-events/{e}/attachments/{a}/archive` | Arkivera bilagan som föreningens underlag; kräver ett skäl (admin) |
| DELETE | `source-events/{e}/attachments/{a}/archive` | Ångra arkiveringen (admin) |
| DELETE | `source-events/{id}` | Ta bort köposten. **Inte** kaskad: inlästa dokument ligger kvar |
| GET | `supplier-aliases` | Bekräftade leverantörsnamn |
| POST | `supplier-aliases` | Bekräfta att två namn är samma leverantör (admin) |
| DELETE | `supplier-aliases/{id}` | Ta bort en bekräftelse (admin) |
| GET | `available-invoices?source=` | Vad källan kan erbjuda. Att titta lagrar ingenting |
| GET | `invoices/mapping-preview` | Vilket källfält som blev vilket av våra (admin) |
| GET | `invoices` | Inlästa ögonblicksbilder |
| POST | `invoices` | Läs in en (admin) |
| POST | `invoices/{id}/review` | Kör granskningen (admin) |
| GET | `findings` | Fynden. Läses också av mobilklienten, read-only |
| POST | `findings/{id}/decision` | Ställningstagande (admin) |

`source` på fakturaruttarna är `fixture` eller `fortnox`, aldrig gissat: en
installation med Fortnox ansluten kan fortfarande läsa fixturunderlaget, och en
skärmdump ska inte kunna förväxla de två.

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

Ingen polling, ingen webhook, ingen prenumeration, ingen delta-fråga, ingen
bakgrundstråd, inget utskick, inget svar, ingen vidarebefordran, ingen
markering som läst, ingen flytt, ingen radering i brevlådan, ingen extern
arkivering, ingen bokföring, ingen kontering, ingen attest, ingen betalning och
ingen statusändring i ett främmande system.

Det är inte kvarvarande arbete. Det är blockets gräns, och den är byggd som
frånvaro av kodväg snarare än som en regel någon ska minnas: `protocols.py`
vägrar vid import ett adapterprotokoll med ett utåtriktat skrivverb, och
`egress.py` har ingen metod som kan skicka något annat än GET mot ett API.

Det som **numera finns**, och som §8 tidigare räknade upp som frånvarande, är
live-läsning ur en ansluten brevlåda (Microsoft Graph) och ur ett anslutet
Fortnox-företag — båda read-only, båda igångsatta av en namngiven
administratör, båda dokumenterade i
[INTEGRATION-OUTLOOK.md](INTEGRATION-OUTLOOK.md) och
[INTEGRATION-FORTNOX.md](INTEGRATION-FORTNOX.md). Det som **inte** följer av
det, och som fortfarande är föreningens beslut och inte programmets: vem som
äger brevlådan, vem integrationen loggar in som, vilka fält styrelsen lagligen
får läsa, och hur länge inläst material sparas.

En ärlighet till, eftersom den inte går att koda bort: **Fortnox scopes är inte
uppdelade i läs och skriv.** Read-only mot Fortnox är klientsidigt och vilar på
de tre kontrollerbara sakerna i INTEGRATION-FORTNOX.md — inte på en behörighet.

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

`backend/tests/test_integrations.py` — adaptergränser, formatet och dess
vägran, atomisk import, dedup, värdeutvinning, granskningens tre domar,
persistens och fixturhygien.

`backend/tests/test_integrations_review.py` — leverantörsnamn och
organisationsnummer, svenska datum, löpande och relativa avtalstider,
indexklausuler, ankarstyrkor, alias-slingan, och arkiveringen av en bilaga.

`backend/tests/test_integrations_live.py` — utgående-gränsen (vägrad värd,
vägrad omdirigering, ingen POST mot ett API), båda inloggningsflödena, roterad
refresh-token, Graph- och Fortnox-adaptrarnas exakta anrop, och att ingen
hemlighet lämnar processen — inklusive att en säkerhetskopia innehåller
anslutningen men inte token.

`backend/tests/test_integrations_isolation.py` och
`backend/tests/test_integrations_connections_http.py` — samma sak över riktig
HTTP, med två föreningar: kön, fakturorna, fynden, bilagorna, anslutningarna,
aliasen och de påbörjade inloggningarna är osynliga för den andra tenanten, en
medlem får läsa men inte ansluta, och `DELETE /api/brf/{id}` sveper
integrationskatalogen inklusive credentials.

`backend/tests/test_desktop.py` — den vertikala skivan genom desktopadapterns
exakta origin-kontroll och installationsspecifika cookie.

`brfv2-mockup/src/Integrations.test.jsx` — att vyn håller isär verifierat,
föreslaget och osäkert, att ett citat navigerar dit det säger, att en svag
koppling syns som svag, och att en korrigering utan förklaring vägras.

`xs_mobilapp` — mobilens read-only vy av fynden: samma tre block, samma
citatnavigering, och inget sätt att fatta ett beslut därifrån.

Ingenting i någon av dem behöver en credential, en nätverksendpoint eller en
körande modell. Att de inte gör det är i sig en del av det som testas — en
testsvit som behövde det skulle betyda att kodvägen gjorde det. De två
liveintegrationerna testas genom en injicerad transport som kräver exakt rätt
begäran, vilket är strängare än ett verkligt anrop mot en förlåtande server.
