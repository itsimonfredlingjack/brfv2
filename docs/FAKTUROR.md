# Fakturor — en faktura som ett ärende, inte en rad siffror

Det här blocket gör en faktura till något en styrelse kan **arbeta med**: vad
den är, vad som ändrats, vad den stämmer mot, vilket underlag som saknas, vem
som tittar på den och vad som hänt hittills.

Det är beslutsstöd. Det är inte ett ekonomisystem, och det finns ingen kodväg
som skriver tillbaka någonstans — samma strukturella gräns som
[INTEGRATIONSDOMAN.md](INTEGRATIONSDOMAN.md) §3 och §8 beskriver, oförändrad.

## 1. Varför ett eget produktområde

Fakturagranskningen låg tidigare som en flik under **Inkommande**. Det var fel
plats av en enkel anledning: en faktura arbetas i veckor efter att posten den
kom med är avklarad. Inkommande är en kö som ska tömmas; en faktura är ett
ärende som ska avgöras. Nu är **Fakturor** ett eget område i sidomenyn, och
Inkommande har två flikar (kön och anslutningarna) i stället för fyra.

## 2. Ärendet

`backend/app/invoices/models.py`

| Fält | Innebörd |
| -- | -- |
| `case_key`, `identity_basis` | Den deterministiska identiteten flera observationer konvergerar på, och **meningen som säger varför de fick det**. |
| `observations` | Varje iakttagelse av fakturan — ekonomisystemet, mejlet, originalfilen — med `basis`, hash och tidpunkt. |
| `source_status` | Vad ekonomisystemet säger om **sin egen** post (bokförd, annullerad, saldo). Läses, visas, skrivs aldrig. |
| `review_status` | Föreningens **egen** granskningsstatus. Sju lägen, inget av dem ett godkännande. |
| `responsible` | Vem som tittar på den. Tomt betyder *ej utsedd* och visas så. |
| `signals` | Härlett ur fynden, ersätts helt av en ny granskning. Ingenting en människa skrivit lagras här. |
| `analysis_run_id`, `analysis_sequence`, `analysis_engine_version` | Vilken inspelad granskning de aktuella fynden kom ur, och under vilka regler (§4). |
| `timeline` | Append-only. Maskinens läsningar och människornas beslut i en ordning, med `human` satt på de senare. |

### Statusarna, och varför ingen av dem heter "godkänd"

| Status | Betyder |
| -- | -- |
| Ej granskad | Ingen här har tagit ställning. |
| Granskad – ingen invändning | En människa har läst fakturan och inte haft någon invändning. **Inte** ett godkännande, en attest eller en bokföringsåtgärd. |
| Behöver utredas | Något ska kontrolleras först. Kräver en mening. |
| Väntar på underlag | Bedömningen väntar på något föreningen inte har. Kräver en mening. |
| Fråga ställd | Någon här har frågat leverantören **utanför appen**. Produkten skickar ingenting. Kräver en mening. |
| Åtgärd skapad | Arbetet ligger som en uppgift under Uppgifter. |
| Granskning avslutad | Klart här. Ingenting har ändrats i ekonomisystemet. |

Var och en bär en `REVIEW_STATUS_CAVEATS`-mening som säger vad den **inte**
betyder, och API:t skickar med dem — så en klient kan inte visa etiketten utan
att kunna visa förbehållet.

Tre av dem kräver en förklaring innan de får sparas. Samma argument som för
`app.tasks` blockerad/avbruten: *"Behöver utredas"* utan en mening dokumenterar
att någon klickade, inte vad som ska utredas.

## 3. Identitet — vad som slås ihop, och vad som inte gör det

`backend/app/invoices/identity.py`

En riktig faktura kan ses tre vägar: läst ur ekonomisystemet, som PDF i ett
mejl, och som ett dokument i arkivet. De ska bli **ett** ärende där det går att
säga varför, och **inte** slås ihop där det inte går.

* **Leverantör + fakturanummer** ⇒ samma ärende. Det är den regeln som gör att
  samma faktura läst ur fixturunderlaget och ur Fortnox hamnar på ett ärende i
  stället för två.
* **Annars källans egen referens** (`adapter:external_ref`), som är unik per
  källa och konvergerar med ingenting. Det är det ärliga utfallet: vi kan inte
  avgöra, alltså påstår vi inte.

Att knyta ett **mejl** till ett ärende är strängare, eftersom ett mejl är text
avsändaren kontrollerar. Två vägar in, ingen tredje:

1. fakturan lästes bokstavligen ur meddelandet (`InvoiceSnapshot.source_event_id`);
2. meddelandet skriver fakturanumret ordagrant **och** namnger leverantören med
   något särskiljande, oberoende av fakturan.

Ett mejl som bara råkar komma från samma leverantör vid ungefär rätt tidpunkt
knyts inte. Det kan mycket väl vara följebrevet — men "kan mycket väl vara" är
precis den sortens koppling som senare citeras som om någon kontrollerat den.

## 4. Analysen

Två motorer, båda deterministiska, båda körda av samma knapp.

**Mot föreningens dokument** — `app/integrations/review.py`, oförändrad. Varje
siffra läses ur en passage som klarat `app.citations.resolve_citation`, ankrad
på leverantörens identitet, med domen *överensstämmer* / *möjlig avvikelse* /
*kan inte verifieras*.

**Mot föreningens egen fakturahistorik** — `app/invoices/compare.py`, ny:

* **Föregående faktura.** Skillnaden i kronor och procent, och — det som gör
  den användbar — uppdelad i den del fakturan förklarar själv och den del den
  inte gör: `Δbelopp = p₀·(q₁−q₀) + q₁·(p₁−p₀)`. En snöröjningsfaktura som
  dubblats för att det snöat dubbelt så mycket är inte samma händelse som en
  som dubblats för att timtaxan höjts, och en granskning som rapporterar
  "+4 625 kr" utan att säga vilket är ingen granskning.
* **Dubbletter.** Samma fakturanummer under två stavningar av leverantörsnamnet,
  och samma belopp från samma leverantör inom tre veckor.
* **Kreditfakturor.** En post med exakt motsatt belopp erbjuds som möjlig
  kreditering — med förbehållet att två belopp som tar ut varandra inte säger
  att krediteringen avser just den här fakturan.
* **Nya rader.** En radtext som aldrig förekommit från leverantören är inte en
  avvikelse och inte ingenting. Den är en fråga, och redovisas som *kan inte
  verifieras*.

### Ingen fjärde dom

Den efterfrågade epistemiska modellen — *verifierat*, *sannolik avvikelse*,
*underlag saknas*, *ingen avvikelse hittad* — ryms i de tre ord produkten redan
har. *Överensstämmer* täcker både "verifierat" och "ingen avvikelse hittad",
för i den här domänen är det samma påstående. Att lägga till en fjärde vore att
slå fast en avvikelse som faktum, vilket är exakt vad
[INTEGRATIONSDOMAN.md](INTEGRATIONSDOMAN.md) §5 vägrar. Vyn skriver ut vad varje
dom betyder i klartext bredvid ordet i stället.

### Fynd utan citat, och varför det är rätt

Historikfynden bär **inga** citat, och det är avsiktligt. Ett citat betyder i
den här produkten en ordagrant verifierad passage i ett dokument. En jämförelse
mot förra månadens faktura har ingen sådan passage — det som står bakom den är
en lagrad fakturapost, namngiven med nummer och datum bland de verifierade
fakta. Att hitta på en citatform åt dem vore första stället ordet slutade betyda
det det betyder överallt annars. Vyn har därför två rubriker: *mot föreningens
dokument* och *mot föreningens tidigare fakturor*, och säger rakt ut att den
andra gruppen saknar citat med flit.

### Vad en omkörning ersatte, och vad den byggde på

Öppna maskinfynd ersätts av en ny granskning, avgjorda behålls. Det är rätt
förval — en inaktuell slutsats kvar bredvid en färsk är värre än ingen — men
*ersatt* får inte betyda *borta*. **"Ingen hade formellt beslutat om det" är
inte samma sak som "ingen arbetade utifrån det."** Ett öppet fynd kan mycket väl
vara skälet till att någon ringde leverantören.

Därför skrivs varje körning som **ändrade något** ned en gång, och redigeras
aldrig (`app/invoices/audit.py`, `AnalysisRun`):

| Frågan | Var den besvaras |
| -- | -- |
| Att en ny analys ersatte den gamla | `supersedes`, `supersedes_sequence`, `summary` — och en egen tidslinjepost, "Granskning körd (version 2)" |
| Vilken källversion den byggde på | `source`: adapter, referens, dataset, **innehållshash** och lästidpunkt. Hashen är den bärande — två körningar mot samma hash läste samma bytes, vad tidsstämplarna än säger |
| Vad som ändrades | `changes`: per fynd, i klartext, med `from_text`/`to_text` hela och `fact_changes` som *etikett, förut, nu* |
| När det skedde | `ran_at` |
| Vilken motor och regelversion | `engine`, `engine_version` (`ANALYSIS_ENGINE_VERSION`) |
| Vad den ersatte | `replaced`: de öppna fynden som stod där innan, hela |

Den gamla versionen ligger **inte kvar som ett aktivt kort**. Den ligger bakom
en kontroll i *Analyshistorik*, märkt "ersatt", utan en enda knapp — den är en
post, inte något som är i spel. Ärendet bär `analysis_run_id`, så det som står
på skärmen alltid är en uppslagning från sin egen revisionspost.

**En körning som kom fram till exakt samma sak är ingen version.** Villkoret är
tredelat: samma läsning (innehållshash), samma resultat, samma regelversion. Att
skriva ned tomma körningar hade fyllt spåret med rader som säger "någon tryckte
uppdatera", vilket är precis bruset som döljer raderna som säger "den här
slutsatsen ändrades" — och det hade brutit idempotensen nedan.

Två saker som föll ut av det och är värda att säga:

* **Fynd jämförs på vad de säger, inte på id** (`finding_content_key`). Motorn
  mintar nya id varje körning, så en id-jämförelse hade fått varje omkörning att
  se ut som ett totalbyte. De *verifierade fakta* ingår i nyckeln, och det var
  ett verkligt hål: en faktura vars belopp ändrats medan prosan råkade vara
  oförändrad — "inget dokument namnger leverantören" ser likadant ut oavsett
  belopp — hade jämförts som oförändrad, och siffran hade flyttat sig under
  läsaren utan att något registrerade det.
* **Ett fynd någon redan avgjort skrivs inte som ett andra kort.** Innan det här
  gav "avfärda ett fynd, tryck uppdatera" två kort med samma mening, ett märkt
  *avfärdad* och ett *öppen*, och läsaren fick själv lista ut att det andra var
  det första som kom tillbaka. Ett beslut täcker det påstående det fattades om;
  att motorn fortfarande säger det registreras på körningen
  (`already_decided_count`) i stället för på skärmen.

Regelversionen betyder en sak: *vilka regler skrev det här*. Ett fynd stämplat
med en äldre version är ett fynd ingen kört om sedan reglerna ändrades, och vyn
säger det rakt ut ovanför fynden i stället för att låta en två månader gammal
slutsats se likadan ut som en färsk.

### Regelversionen kan inte längre halka efter reglerna

`backend/app/invoices/rules.py` · `backend/app/invoices/RULES.lock.json`

Numret var handbumpat, som en CHANGELOG-rad, och lika lätt att glömma. En
glömd bump felar inte högt — den **påstår tyst att två slutsatser skrivna under
olika regler skrevs under samma**, vilket är exakt den felläsning hela
revisionsspåret finns för att förhindra.

Så reglerna fingeravtrycks, och avtrycket låses till den version som gällde när
det togs:

| Frågan | Svaret |
| -- | -- |
| Vad räknas som en regel | Modulerna som avgör vad ett fynd **säger**: `integrations/review.py`, `invoices/compare.py`, `integrations/supplier.py`, `terms.py` — plus etikettabellerna i `integrations/models.py`, eftersom en omformulerad dom är en ändrad slutsats för den som läser den |
| Vad räknas medvetet inte | Retrieval, extraktion och `citations.resolve_citation`. En ändring där kan mycket väl ändra ett fynd — och gör den det så spelas en ny version in ändå, för `build_run` triggar på att *resultatet* skiljer sig. Regelversionen svarar på den smalare frågan de två andra triggrarna inte kan: vilka regler skrev det här, för ett fynd vars text råkar vara oförändrad |
| Vad avtrycket tas över | Det parsade syntaxträdet med docstrings borttagna. Att formatera om en regelmodul eller skriva om dess dokumentation kräver alltså ingen bump — men strängarna ingår, för domens ordalydelse är det en styrelseledamot faktiskt läser |
| Vad som händer om en regel ändras utan bump | `tests/test_invoice_rules_version.py` felar och **namnger modulen som rörde sig** |
| Vad som händer om någon spelar in om låsfilen i stället för att bumpa | `record()` vägrar. En redan inspelad version behåller sitt avtryck, så enda vägen till en grön svit är bumpen |
| Vad som händer om reglerna flyttar till en ny modul | Testet letar upp varje modul i `backend/app` som konstruerar en `ReviewFinding` och kräver att den ingår i avtrycket |

Efter en avsiktlig regeländring: höj `ANALYSIS_ENGINE_VERSION` i
`app/invoices/models.py` och kör `make invoice-rules-lock`. Låsfilen växer med
en rad per version, aldrig genom att skriva om en gammal, så skillnaden mellan
två versioner visar vilken regelkälla som ändrades mellan dem.

Kontrollen har körts skarpt: `2026.08.2` är den version som blev följden av att
kreditfyndet formulerades om (nästa avsnitt), och testet felade på `compare.py` innan
bumpen fanns.

### Kreditfakturan, och vilket håll den läses åt

En post vars belopp tar ut en annan exakt är ett faktum. **Vilken faktura en
kreditnota hör till är det inte** — ingenting i underlaget säger det, och tre
fakturor på samma belopp tar ut samma kreditnota lika exakt. Fyndet säger båda
delarna: vad som är räknat, och vad som inte går att avgöra.

Riktningen är inte en detalj. Ett negativt belopp krediterar ett positivt och
aldrig tvärtom, så en enda mening för båda hållen är fel i ett av dem — och den
var fel i just det håll en granskare möter: *öppnad på kreditnotan* läste den
som om den vanliga fakturan krediterade kreditnotan. Nu står det åt rätt håll i
båda riktningarna, och acceptansen i den riktiga applikationen kontrollerar
det (§10).

## 5. Idempotens

Det som gör "Läs om och granska" trygg att trycka på två gånger:

* **Ögonblicksbilden behåller sin identitet.** `upsert_invoice` behåller
  `id` för samma `(adapter, external_ref)`. Utan det hade en omläsning bytt id
  och lämnat varje fynd, ärende och uppgift som pekade på det gamla pekande på
  ingenting.
* **Ärendet konvergerar på `case_key`**, och ett lagrat ärende är också
  sökbart via den läsning det beskriver. Det behövs när identiteten *ändras*:
  en faktura som kom utan nummer nycklas på källans referens, och får en riktig
  nyckel den dag någon fyller i numret i ekonomisystemet. Det härledda id:t
  flyttar med, och anteckningarna flyttar med det — annars hade en omläsning
  tyst strandat någons utredning på en rad ingenting längre pekar på.
  Adoptionen sker **i projektionen**, alltså i minnet; raden skrivs om under
  det nya id:t nästa gång någon faktiskt ändrar något.
* **Öppna fynd ersätts, avgjorda behålls** — `replace_findings_for_invoice`.
  Det som ersätts sparas på körningen som ersatte det (§4).
* **Maskinella tidslinjeposter bär en nyckel** härledd ur vad de *säger*
  (`analysis:<run-id>`, `finding:<fingerprint>`, `obs:<kind>:<ref>`). En
  omkörning som inte hittar något nytt lägger inte till något — den skriver
  ingen körning, och därmed ingen post. Mänskliga poster bär ingen nyckel: att
  säga samma sak två gånger är två handlingar.
* **En läsning skriver ingenting.** `project()` är ren: den läser fakturor,
  fynd och köhändelser och räknar ut vilka ärenden de innebär. Ett `GET` av
  arbetsytan har alltså inga sidoeffekter alls, och två samtidiga läsningar
  räknar ut samma svar utan att lämna spår. Ett ärende skrivs till disk första
  gången någon *gör* något med det.

### Varför identiteten är nyckeln, och inte ett slumptal

`InvoiceCase.id` härleds ur `(tenant_id, case_key)` i stället för att mintas.
Det är det som gör skrivvägen säker: butiken upsertar på `id`, så två samtidiga
skribenter som var för sig kommer fram till att fakturan behöver ett ärende
landar på **en** rad i stället för att lägga till två.

Den första versionen av det här blocket gjorde tvärtom. `ensure_cases` var en
"projektion" som körde på varje läsning men *skrev* medan den gjorde det, och
`id` var ett `uuid4`. Åtta samtidiga läsningar av fyra fakturor gav **trettioen
ärenden** — hitta-sedan-skriv var inte atomärt, och ett slumpat id gjorde att
butikens upsert inte kunde slå ihop dubbletterna efteråt. Båda halvorna
regressionstestas nu (`TestConcurrency`), eftersom endera ensam skulle släppa
tillbaka felet.

### Var skrivningarna sker, och under vilket lås

`mutate()` är den enda skribenten. Den håller tenantens butikslås över hela
läs–ändra–skriv och **projicerar om inuti låset**, så en anropare som läste
ärendet för en sekund sedan inte kan skriva tillbaka en version som hunnit få en
kommentar. `analyse_case`, `set_review_status`, `assign`, `comment` och
`note_task` tar alla ett **id**, aldrig ett `InvoiceCase` — det är signaturen
som tvingar fram att den version som ändras är den som ligger på disk nu.

Gränsen sägs rakt ut: låset är ett trådlås över en process cachade
per-tenant-`Store`, vilket är den samtidighetsmodell hela den här backenden
redan har. Det gör samtidiga *anrop* säkra; det gör inte två *processer* säkra.
Det härledda id:t håller även där — två processer kan inte skapa dubbla ärenden
— men en samtidig kommentar från vardera skulle fortfarande kunna tappas. Att
säga det är billigare än att antyda en garanti filupplägget inte kan ge.

Att projektionen är ren är också vad som gör att fakturor som lästes in innan
den här arbetsytan fanns dyker upp utan ett migreringssteg, och utan att ett
`GET` tyst skapar poster.

## 6. Leverantörsminnet

Byggt av poster som redan finns — tidigare ärenden, dokument granskningen
citerat, bekräftade namnalias, öppna uppgifter, tidigare avvikelser, vem som
brukar hantera leverantören. **Ingen leverantörstabell införs.** Ett andra
ställe där leverantörsfakta bor är det ställe som ingen underhåller.

## 7. API

Alla under `/api/brf/{brf_id}/invoices`, med samma `tenant_store` /
`require_admin`-beroenden som resten. Läsning kräver medlemskap; allt som ändrar
tillstånd kräver `admin`. En icke-medlem får `404`, aldrig `403`.

| Metod | Väg | Vad |
| -- | -- | -- |
| GET | `` | Kön: ärenden, räknare, etiketter, källor |
| GET | `cases/{id}` | Ett ärende med faktura, fynd, dokument, mejl, leverantörskontext, uppgifter och de inspelade granskningarna |
| GET | `cases/{id}/analyses/{run_id}` | En inspelad granskning **med de fynd den ersatte** |
| POST | `cases/{id}` | Granskningsstatus och/eller ansvarig (admin) |
| POST | `cases/{id}/comment` | Kommentar (admin) |
| POST | `cases/{id}/refresh` | Läs om källan och kör om granskningen (admin) |
| POST | `import` | Läs in en faktura, konvergera och granska (admin) |

Den tredje läsningen är ett medvetet undantag från "två läsningar räcker för
hela ytan": att bära varje ersatt fynd, med citat och allt, på varje
ärendeläsning vore bytes ingen bett om. Den kräver bara medlemskap — ett
revisionsspår som en granskare inte kommer åt utan adminrätt är ett spår
styrelsen inte kan kontrollera, och ingenting i det ändrar något.

En omläsning där källan inte svarar, är utloggad eller inte längre har fakturan
**stoppar inte granskningen**: den körs mot det som redan är inläst, och svaret
säger varför omläsningen inte gick igenom. En uppdatering som tyst gjorde
hälften av vad den sa är värre än en som säger det.

## 8. Vyn

`brfv2-mockup/src/components/Invoices.jsx` (kön) och `InvoiceCase.jsx`
(ärendet), nåbara som **Fakturor** i sidomenyn. Som resten av
desktopfunktionerna renderas de bara när `/api/desktop/state` svarar.

Kön har två skilda kolumner med två skilda rubriker: *I ekonomisystemet* och
*Vår granskning*. De blir aldrig en badge, för det är precis
sammanslagningen som skulle få någon att tro att den här produkten godkänt en
faktura någonstans.

Ärendet är tre kolumner:

* **Vad som kom in** — originalfilen i appens egen dokumentvy, fälten som
  källan skrev dem, varje källa med sin `basis`, sin hash och sin tidpunkt, och
  mejlet fakturan kom med. Ett härlett utdrag ersätter aldrig originalet.
* **Vad produkten tror** — fynden, med verifierat faktum, förslag och osäkerhet
  i tre olika visuella vikter (samma stilmall som Inkommande, `Integrations.css`,
  eftersom det är samma sak som visas). Kolumnen slutar med **Analyshistorik**:
  varje granskning som ändrat något, medvetet tystare formgiven än ett fynd,
  eftersom den beskriver vad motorn *brukade* säga och inte får konkurrera med
  vad den säger nu. Det ersatta ligger bakom en kontroll, märkt "ersatt", utan
  knappar.
* **Vad människor gjort** — granskningsläge, ansvarig, kommentarer, uppgifter
  och hela tidslinjen, där maskinella poster och mänskliga beslut är visuellt
  åtskilda.

## 9. Vad som inte finns, och varför

Ingen attest, ingen betalning, ingen kontering, ingen bokföring, ingen
statusändring i ett främmande system, ingen regelbyggare och ingen automatisk
åtgärd. Ingen knapp heter "Godkänn faktura". Det som finns är ett
ställningstagande till **fyndet** ("Godkänn fyndet") och ett granskningsläge för
**ärendet** — två olika saker, och vyn säger vilken som är vilken.

Gränsen är byggd som frånvaro av kodväg, inte som en regel någon ska minnas:
`protocols.py` vägrar vid import ett adapterprotokoll med ett utåtriktat
skrivverb, och `egress.py` har ingen metod som kan skicka något annat än GET mot
ett API.

## 10. Verifiering

`backend/tests/test_invoice_cases.py` — identitet och konvergens (inklusive två
källor på ett ärende och ett mejl som *inte* knyts), samtidighet (att en läsning
inte skriver, att åtta samtidiga skrivningar ger ett ärende och noll tappade
kommentarer, och att id:t är härlett), idempotent omläsning,
jämförelsens uppdelning i förklarat och oförklarat, dubbletter, kreditrelation,
nya rader, signaler ur fynd, att ett avfärdat fynd slutar driva en signal, att
en omkörning inte rör granskningsstatus, kommentarer eller ansvarig, och att
historiken bara kan växa. Och revisionsspåret: att första körningen spelas in
med sin källhash och regelversion, att en omkörning som inte ändrade något
*inte* blir en version, att en ändrad läsning blir en version som namnger den
den ersatte, att det ersatta finns kvar ordagrant, att skillnaden skrivs ut med
både förra och nuvarande värdet, att en inspelad körning inte går att skriva om
(och att det inte finns någon metod som kunde), att ett avgjort fynd aldrig
hamnar i det ersatta, och att bekräftandet av ett leverantörsnamn registreras
som *vad* det ändrade — kopplingen gick från "delvis namnlikhet" till "ett namn
någon här har bekräftat".

`backend/tests/test_invoices_http.py` — samma sak över riktig HTTP med två
föreningar: kön, ärendena och kommentarerna är osynliga för den andra tenanten,
en främling får `404` och aldrig `403`, en medlem får läsa men inte besluta, och
hela resan från källa till avgjort ärende körs igenom — två gånger, med samma
poster som resultat.

`brfv2-mockup/src/Invoices.test.jsx` — att de två statusarna hålls isär, att
ingen kontroll kan förväxlas med ett godkännande, att ett fynd håller isär
verifierat, föreslaget och osäkert, att ett citat navigerar dit det säger, att
förändringen står i klartext med den oförklarade delen utpekad, att tidslinjen
märker vad en människa gjort, och att en medlem inte erbjuds något att ändra.

`brfv2-mockup/src/Integrations.test.jsx` — att Inkommande **inte längre**
granskar fakturor, vilket är det som hindrar produkten från att tyst få två
fakturaskärmar som säger olika saker.

`backend/scripts/invoice_acceptance.py` (`make invoice-acceptance`) — hela resan
genom den **riktiga installerade applikationen**: Tauri/WebKitGTK, riktig
uppladdning, riktig granskning, riktiga klick. Den behöver **ingen modell**, och
att den inte gör det är en egenskap hos funktionen snarare än hos skriptet —
granskningen är deterministisk hela vägen, så en installation utan modell kan
ändå läsa in en faktura, jämföra den mot föreningens dokument och dess egen
historik, och arbetas av en styrelse. Skriptet vägrar om Fakturor inte ligger
som eget område, om ett fynd som inte är en match saknar osäkerhet, om någon
kontroll läser som ett godkännande, om ett citat inte öppnar rätt sida med
passagen markerad, om en omkörning växer tidslinjen, eller om Inkommande
fortfarande granskar fakturor.

Den kör också hela ersättningsfallet i det riktiga fönstret, med enbart
levererad fixturdata: den tredje fakturan kommer från "Snösvängen AB" medan
avtalet skriver "Snösvängen Entreprenad AB", så granskningen ankrar svagt och
frågar om det är samma företag. Att bekräfta det och köra om är den enda vägen
en operatör kan ändra analysen utan att något rört sig i ekonomisystemet — och
det är precis fallet spåret finns för. Skriptet vägrar om version 2 inte säger
att den ersatte version 1, om körningen inte namnger sin källhash och sin
regelversion, om skillnaden inte står i klartext, eller om ett ersatt fynd
saknar märkningen "ersatt" eller erbjuder en enda knapp.

Och kreditfakturan, som är den fjärde inläsningen i samma körning: att beloppet
**visas som negativt** i stället för att teckenet ska härledas ur ordet
"kredit" någonstans, att signalen "Möjlig kreditfaktura" ligger som *info* och
inte som en varning (ett par som tar ut varandra exakt är en normal och riktig
sak att hitta), att fyndet namnger fakturan det tar ut och står åt rätt håll,
att det säger vad det inte kan avgöra, att det inte bär något citat — det finns
ingen dokumentpassage bakom en jämförelse mot en annan faktura — och att vyn
inte erbjuder någon kontroll som **kvittar** eller **matchar** paret. Att kvitta
är något som sker i ekonomisystemet.

`backend/tests/test_accounting_edge_cases.py` — det en riktig
ekonomisystemexport innehåller och en snäll fixtur inte gör, för båda
adaptrarna: paginering, saknad bilaga, tom radlista, rader utan innehåll,
`null` i stället för värde, annullerad faktura, kreditfaktura, samma faktura ur
två källor, och en leverantör exporten knappt identifierar. Fixturfallen ligger
i en **egen katalog** (`backend/fixtures/accounting-edge-cases/`) som den
levererade adaptern aldrig läser — demons datamängd får förbli den lilla
läsbara berättelse den är — och Fortnox-fallen körs genom samma stubbade
transport som resten av den skarpa integrationssviten: riktiga URL:er, riktig
mappningstabell, riktiga vägranden, utan att någon behöver vara online.

`backend/tests/test_invoice_rules_version.py` — att regelversionen inte kan
halka efter reglerna (§4). Med sitt eget RED-bevis: ett ändrat tröskelvärde och
en omformulerad dom flyttar avtrycket, en omskriven docstring och en ny
kommentar gör det inte, och en ny modul som skriver fynd utan att ingå i
avtrycket felar sviten.

### Var evidensen hamnar

`docs/evidence/<etikett>-invoice-<vy>.png` plus ett maskinläsbart
`docs/evidence/<etikett>-invoice-acceptance.json` — samma namngivning och samma
skydd som desktopacceptansen: evidens som git redan bär skrivs aldrig över utan
`--overwrite-evidence`, eftersom det är den posten en tidigare acceptans
godkändes på. Kvittot bär körningens etikett, binärens SHA-256, regelversionen,
varaktigheten, `modelRequired: false` och varje steg skriptet noterade — och
skrivs även när resan **failar**, då tillsammans med felskärmbilden, eftersom
det är den körningen kvittot är mest värt på.

Den provisionerade `XDG_DATA_HOME` är en slängbar temporärkatalog och ligger
medvetet **inte** i evidensträdet: evidens committas, en förenings butik gör det
inte.

`make desktop-acceptance-full` kör båda acceptanserna under en etikett — först
fakturaresan, som är modellfri och därför felar snabbt och billigt, sedan den
fulla resan som kräver den självhostade modellen. `<etikett>-invoice-*` och
`<etikett>-desktop-*` kan aldrig skriva över varandra, vilket är testat och
inte antaget.

### Vad som är verifierat mot Fortnox, och vad som inte är det

Värt att säga rakt ut, eftersom "Fortnox-integrationen är testad" annars går att
läsa på två sätt:

* **Verifierat:** kontraktet och mappningen. Varje URL, verb, scope, header och
  fältöversättning körs mot en stubbad transport som vägrar en obeställd
  begäran, plus kantfallen ovan. Att varje anrop är ett `GET` och att ingen
  skrivmetod finns är strukturellt bevisat.
* **Inte verifierat:** att en riktig Fortnox-företagsdatabas svarar med de
  former stubben svarar med. Ingen körning mot ett skarpt Fortnox-konto har
  gjorts i det här repot. Fältnamnen och sidformerna kommer från Fortnox
  API-dokumentation och inte från observerad trafik.

Det är också därför `mapping_preview` finns: den första skarpa anslutningen är
det enda tillfälle mappningen faktiskt går att kontrollera, och "beloppen såg
rätt ut" är inte att kontrollera. Se
[INTEGRATION-FORTNOX.md](INTEGRATION-FORTNOX.md) för hela gränsdragningen.
