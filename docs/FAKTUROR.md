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

## 5. Idempotens

Det som gör "Läs om och granska" trygg att trycka på två gånger:

* **Ögonblicksbilden behåller sin identitet.** `upsert_invoice` behåller
  `id` för samma `(adapter, external_ref)`. Utan det hade en omläsning bytt id
  och lämnat varje fynd, ärende och uppgift som pekade på det gamla pekande på
  ingenting.
* **Ärendet konvergerar på `case_key`**, och faller tillbaka på "det ärende som
  redan pekar på den här ögonblicksbilden" om nyckeln ändras (t.ex. när en
  omläsning fyller i ett fakturanummer som saknades). Föreningens
  granskningsanteckningar blir aldrig föräldralösa.
* **Öppna fynd ersätts, avgjorda behålls** — `replace_findings_for_invoice`,
  oförändrad.
* **Maskinella tidslinjeposter bär en nyckel** härledd ur vad de *säger*
  (`analysis:<fingerprint>`, `finding:<fingerprint>`, `obs:<kind>:<ref>`). En
  omkörning som inte hittar något nytt lägger inte till något. Mänskliga poster
  bär ingen nyckel: att säga samma sak två gånger är två handlingar.
* **Kön skriver bara när något faktiskt skiljer sig**, så en vanlig läsning av
  arbetsytan inte river i filen.

`ensure_cases` är en **projektion** och körs på varje läsning. Den fattar inga
beslut — ett projicerat ärende börjar på *Ej granskad* utan ansvarig, vilket är
ett sant påstående om att ingen tittat på det. Det är också vad som gör att
fakturor som lästes in innan den här arbetsytan fanns dyker upp utan ett
migreringssteg.

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
| GET | `cases/{id}` | Ett ärende med faktura, fynd, dokument, mejl, leverantörskontext och uppgifter |
| POST | `cases/{id}` | Granskningsstatus och/eller ansvarig (admin) |
| POST | `cases/{id}/comment` | Kommentar (admin) |
| POST | `cases/{id}/refresh` | Läs om källan och kör om granskningen (admin) |
| POST | `import` | Läs in en faktura, konvergera och granska (admin) |

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
  eftersom det är samma sak som visas).
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
källor på ett ärende och ett mejl som *inte* knyts), idempotent omläsning,
jämförelsens uppdelning i förklarat och oförklarat, dubbletter, kreditrelation,
nya rader, signaler ur fynd, att ett avfärdat fynd slutar driva en signal, att
en omkörning inte rör granskningsstatus, kommentarer eller ansvarig, och att
historiken bara kan växa.

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
