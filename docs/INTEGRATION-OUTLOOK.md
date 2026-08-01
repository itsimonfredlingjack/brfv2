# Ansluta en brevlåda (Microsoft 365 / Outlook.com)

Den här integrationen låter styrelsen hämta ett **valt** meddelande ur en
brevlåda in i granskningskön, i stället för att exportera det till en `.eml`-fil
först. Ingenting annat.

## Vad den gör och inte gör

| | |
| -- | -- |
| Läser | rubrikrader i den valda mappen, och ett helt meddelande när någon klickar på det |
| Skriver | **ingenting** |
| Markerar som läst | nej |
| Flyttar, arkiverar, raderar | nej |
| Svarar, vidarebefordrar, skickar | nej |
| Bevakar brevlådan | nej — ingen prenumeration, ingen webhook, ingen delta-fråga, ingen bakgrundstråd |

Varje anrop sker för att en människa klickade. Det finns ingen kodväg som läser
brevlådan av sig själv, och testsviten kontrollerar det.

Behörigheterna som begärs är en **konstant i koden**
(`backend/app/integrations/graph_mail.py`, `READ_SCOPES`):

```
offline_access   en refresh-token, så att någon loggar in en gång
User.Read        kontots eget namn, för att visa vems behörighet läsningen sker under
Mail.Read        läsa meddelanden och deras bilagor i brevlådan
```

Ingen inställning, ingen konfigurationsfil och ingen återställd säkerhetskopia
kan lägga till `Mail.Send` eller `Mail.ReadWrite`, eftersom listan inte läses
från något. `Mail.ReadBasic` räcker inte — den utesluter brödtext och bilagor,
vilket är hela nyttolasten här.

Utgående trafik går bara till `login.microsoftonline.com` och
`graph.microsoft.com`, och bara som GET (utom själva token-anropet). Se
`backend/app/integrations/egress.py`.

## Det du behöver ordna en gång

Produkten är en **desktopapplikation utan klienthemlighet** (public client) och
loggar in med device code-flödet. Därför behövs en app-registrering i Microsoft
Entra ID:

1. Gå till Microsoft Entra admin center → **App registrations** → **New
   registration**.
2. Namn: valfritt, t.ex. `BRF Dokument-AI`.
3. **Supported account types** — välj det som matchar brevlådan:
   * personligt Microsoft-konto (outlook.com, hotmail.com) → *Personal
     Microsoft accounts only*, och katalog `consumers` i appen;
   * arbetskonto (Microsoft 365) → *Accounts in this organizational directory
     only*, och katalog `organizations` eller katalogens GUID i appen.
4. **Redirect URI**: lämna tom. Device code-flödet använder ingen.
5. Efter registrering: **Authentication** → **Advanced settings** → sätt
   *Allow public client flows* till **Yes**. Utan den svarar Microsoft
   `unauthorized_client` på device code-begäran.
6. **API permissions** → *Microsoft Graph* → *Delegated permissions* → lägg till
   `Mail.Read`, `User.Read`, `offline_access`. Lägg till `Mail.Read.Shared` bara
   om ni ska läsa en **delad** brevlåda. Ta bort allt annat.
   * I en organisation kan admin-medgivande krävas; be IT om **Grant admin
     consent**.
7. Kopiera **Application (client) ID** — det är det enda värdet appen behöver.

### Vilken brevlåda?

Rekommendationen är en **delad brevlåda** som styrelsen redan använder
(`styrelsen@…`), inte en enskild ledamots privata. Två skäl: läsningen sker då
under en adress föreningen äger, och den överlever att en ledamot slutar.

Delad brevlåda kräver att kontot som loggar in har delegerad åtkomst till den i
Exchange, och att `Mail.Read.Shared` finns i registreringen. Lämnas fältet tomt
läses det inloggade kontots egen brevlåda.

## Så här ansluter du i appen

1. **Inkommande → Anslutningar → Brevlåda → Konfigurera.**
   Fyll i klient-id, katalog (`consumers` / `organizations` / `common` / GUID),
   eventuell delad brevlådeadress och mapp (`inbox` som standard).
   Konfigurationen kräver ingen inloggning och kan göras i förväg.
2. **Logga in.** Appen visar en kort kod och en länk. Öppna länken i valfri
   webbläsare, skriv koden, logga in med kontot som får läsa brevlådan och
   godkänn behörigheterna. Appen upptäcker själv när det är klart.
3. Statusraden visar därefter vilket konto anslutningen läser under, vilka
   behörigheter som faktiskt beviljades (som Microsoft rapporterade dem
   tillbaka, inte vad vi bad om) och vem här som anslöt den.

Inloggningen är giltig tills refresh-token upphör eller någon återkallar den.
Appen förnyar automatiskt; misslyckas det står anslutningen som **utgången**
med skälet, och en administratör loggar in igen.

## Att importera ett meddelande

Listan visar de senaste meddelandena i mappen, med avsändare, ämne och om det
finns bilagor. Brödtext hämtas **inte** för listan.

När du väljer ett meddelande hämtar appen det som rå MIME (`/$value`) och kör
det genom exakt samma väg som en manuellt exporterad `.eml`: samma
formatgränser, samma regel att en bilaga utanför formatet vägrar hela
meddelandet, samma innehållshash, samma dubblettkontroll och samma atomiska
återställning. En ansluten brevlåda kan alltså inte importera något som den
manuella vägen hade vägrat.

Den manuella `.eml`-vägen finns kvar oförändrad och fungerar utan anslutning.

## Säkerhet

* Tokens ligger i `…/tenants/<förening>/integrations/credentials/`, läge `0600`
  i en katalog med `0700`.
* **Säkerhetskopior innehåller aldrig tokens.** `create_backup` hoppar över
  katalogen och skriver antalet uteslutna filer i manifestet. Efter en
  återställning står integrationen som ansluten men oanvändbar, och en
  administratör loggar in igen. Det är avsiktligt: en refresh-token i ett arkiv
  som ingen behandlar som en hemlighet är ett stående tillstånd att läsa någons
  brevlåda.
* Ingen token, refresh-token eller klienthemlighet returneras av något API,
  loggas eller syns i gränssnittet. Loggen skriver metod, värd och sökväg —
  aldrig query-strängen och aldrig ett huvud.
* Att radera föreningen (`DELETE /api/brf/{id}`) tar med sig credentials, utan
  att någon kod behöver komma ihåg dem: de ligger i föreningens egen katalog.

## Om något inte fungerar

| Symtom | Sannolik orsak |
| -- | -- |
| `unauthorized_client` när inloggningen startas | *Allow public client flows* är inte påslaget på registreringen |
| `invalid_client` | fel klient-id, eller fel katalog för kontotypen |
| Inloggningen går igenom men listan är tom | fel mapp, eller inga meddelanden med bilagor (listan filtrerar på det som standard) |
| `ErrorAccessDenied` mot en delad brevlåda | kontot saknar delegerad åtkomst, eller `Mail.Read.Shared` saknas i registreringen |
| Anslutningen blir **utgången** efter en tid | medgivandet återkallat, lösenordet bytt, eller registreringen ändrad — logga in igen |

## Vad som fortfarande kräver ett beslut utanför appen

Vem som äger brevlådan, vilka som får läsa den genom produkten, hur länge
importerat material sparas, och att de som mejlar föreningen vet att materialet
hamnar i föreningens dokumentarkiv. Det är föreningens beslut och inte
programmets.
