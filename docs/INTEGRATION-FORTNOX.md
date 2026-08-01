# Ansluta Fortnox (read-only)

Den här integrationen läser föreningens **leverantörsfakturor** ur Fortnox så
att de kan jämföras mot föreningens egna avtal. Den skriver ingenting, någonsin.

## Vad den gör och inte gör

| | |
| -- | -- |
| Läser | leverantörsfakturor (`/3/supplierinvoices`), företagsnamn (`/3/companyinformation`), och — om det valts till — leverantörsregistret (`/3/suppliers`) för organisationsnummer |
| Skriver | **ingenting** |
| Bokför, konterar, attesterar, betalar | nej |
| Ändrar status, makulerar, låser upp | nej |
| Skapar eller ändrar poster | nej |

## Den ärliga delen om "read-only"

**Fortnox scopes är inte uppdelade i läs och skriv.** `supplierinvoice` ger
båda, och det finns ingen smalare behörighet att be om. Read-only här är alltså
*klientsidig*, och den består av tre saker som var för sig går att kontrollera:

1. modulen `backend/app/integrations/fortnox.py` innehåller inget skrivande
   verb — adaptern har `list_invoices`, `get_invoice` och `mapping_preview`, och
   `protocols.py` vägrar vid import att definiera ett adapterprotokoll med en
   metod som heter något skrivande;
2. `backend/app/integrations/egress.py` har ingen metod som kan skicka PUT,
   PATCH, DELETE eller ens en POST mot ett API — den enda POST som finns är
   bunden till Fortnox token-endpoint;
3. testsviten prövar båda, och prövar dessutom att varje anrop modulen gör är
   en GET.

Det som **inte** följer av det är ett löfte om att token inte kan missbrukas av
något annat. Därför: anslut en Fortnox-användare vars egna behörigheter är
begränsade till att läsa leverantörsfakturor. En behörighet kan inte vara sista
försvarslinjen när leverantören inte erbjuder en läsbehörighet.

## Det du behöver ordna en gång

Fortnox kräver en **konfidentiell klient**: en integration registrerad hos
Fortnox med klient-id *och* klienthemlighet.

1. Skaffa ett **Fortnox Developer**-konto och registrera en integration
   (Fortnox Developer Portal).
2. Ange en **redirect-URI** på integrationen. Den måste vara `https://` och
   matchas exakt av Fortnox. Appen fångar inte upp anropet själv — se nedan —
   så URI:n behöver bara vara en adress du kan läsa av i webbläsarens
   adressfält.
3. Begär scopet `supplierinvoice` och `companyinformation` för integrationen.
   Lägg till `supplier` bara om ni vill slå på läsning av leverantörsregistret.
4. Föreningen (Fortnox-kunden) måste **aktivera integrationen** för sitt
   konto. Utan det finns ingen relation att logga in på.
5. Notera klient-id och klienthemlighet.

### Varför man klistrar in en kod i stället för att bli omdirigerad

Alternativet är att desktopapplikationen binder en port och tar emot
inkommande anslutningar — en verklig attackyta, tillagd för att slippa ett
klipp och klistra. Appen visar i stället inloggningslänken, du loggar in i din
egen webbläsare, och klistrar tillbaka antingen `code`-värdet eller hela
adressen från adressfältet. `state` genereras per inloggning och kontrolleras
på vägen tillbaka, så det inklistrade värdet ensamt räcker inte för att slutföra
någon annans inloggning.

## Så här ansluter du i appen

1. **Inkommande → Anslutningar → Ekonomisystem → Konfigurera.** Klient-id,
   klienthemlighet, redirect-URI, och valet om leverantörsregistret ska läsas.
2. **Logga in.** Öppna länken, godkänn i Fortnox, klistra tillbaka koden.
3. Statusraden visar vilket Fortnox-företag anslutningen läser, vilka scopes
   som faktiskt beviljades och vem här som anslöt den.

Access-token gäller en timme och förnyas automatiskt. **Fortnox refresh-token
är engångs och roterar**: varje förnyelse ger en ny och ogiltigförklarar den
gamla. Appen skriver den nya innan den används, eftersom en tappad roterad
refresh-token är det enda felet i en OAuth-klient som inte går att reparera vid
körning. Den är giltig i 45 dagar av inaktivitet; en installation som inte
använts på längre tid behöver anslutas om.

## Kontrollera mappningen första gången

`Inkommande → Fakturor → Källa: Fortnox → Visa fältmappning` visar vilket
Fortnox-fält som blev vilket av våra, med båda värdena:

| Vårt fält | Fortnox |
| -- | -- |
| `external_ref` | `GivenNumber` |
| `supplier_name` | `SupplierName` |
| `supplier_ref` | `SupplierNumber` (+ `OrganisationNumber` om registret läses) |
| `invoice_number` | `InvoiceNumber`, annars `ExternalInvoiceNumber` |
| `invoice_date` | `InvoiceDate` |
| `due_date` | `DueDate`, annars `FinalPayDate` |
| `total_amount` | `Total` (inkl. moms) |
| `vat_amount` | `VAT` |
| `currency` | `Currency` |
| radens `description` | `Description`, annars `ArticleNumber`, annars `Account` |
| radens `quantity` / `unit_price` | `Quantity` / `Price` |
| radens `amount` | `Total`, annars `Debit` |

`Booked`, `Cancelled`, `Balance` och verifikationsfälten **läses och visas** men
skickas aldrig någonstans.

**Fortnox leverantörsfaktura har inget periodfält.** Periodgranskningen görs
därför inte för fakturor som kommer den här vägen, och mappningsvyn säger det
rakt ut i stället för att lämna ett tomt fält. Beloppsgranskningen påverkas inte.

Gör den här jämförelsen mot fakturan i Fortnox **en gång**, vid första
anslutningen. Det är det enda tillfälle mappningen faktiskt går att kontrollera,
och "beloppen såg rätt ut" är inte en kontroll.

## Säkerhet

Samma som för brevlådan: `0600` i en `0700`-katalog inne i föreningens egen
datakatalog, aldrig i en säkerhetskopia, aldrig i ett API-svar, aldrig i en
logg, och borta när föreningen raderas. Se
[INTEGRATION-OUTLOOK.md](INTEGRATION-OUTLOOK.md#säkerhet).

Klienthemligheten lagras på samma sätt som tokens och lämnar aldrig datorn
annat än som `Authorization: Basic` mot Fortnox token-endpoint.

## Om något inte fungerar

| Symtom | Sannolik orsak |
| -- | -- |
| `invalid_client` vid inloggning | fel klient-id/hemlighet, eller integrationen är inte aktiverad hos föreningen |
| `invalid_grant` när koden klistras in | koden är äldre än 10 minuter, redan använd, eller redirect-URI matchar inte exakt |
| Anslutningen blir **utgången** | refresh-token förbrukad eller äldre än 45 dagar — anslut igen |
| `403` på `/3/suppliers` | leverantörsregistret är inte påslaget, eller `supplier`-scopet saknas |
| Tomma perioder på alla fakturor | förväntat: Fortnox leverantörsfaktura har inget periodfält |

## Vad som fortfarande kräver ett beslut utanför appen

Vem som administrerar Fortnox-relationen, vilken användare integrationen loggar
in som, vilka fält styrelsen lagligen får läsa, och hur länge inlästa
ögonblicksbilder sparas. Produkten kan bevisa att den inte skriver; den kan inte
avgöra vem som ska få läsa.
