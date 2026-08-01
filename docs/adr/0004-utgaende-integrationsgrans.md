# ADR 0004 — Den utgående gränsen för liveintegrationer

Status: **antagen** (2026-08-01)
Bygger vidare på: [ADR 0002 — Modellgränsen](0002-model-endpoint-boundary.md).

## Problemet

Fram till det här beslutet hade den installerade desktopprodukten **en** utgående
adress: modelltjänsten, kontrollerad av `app/model_endpoint.py` och ADR 0002.
Allt annat stannade på maskinen, och det var en gräns som gick att uttala i en
mening.

Live-läsning ur en brevlåda (Microsoft Graph) och ur ett ekonomisystem (Fortnox)
bryter den meningen. Två nya destinationsfamiljer, två OAuth-flöden, långlivade
credentials och trafik som bär föreningens material *in* i produkten. Den
uppenbara implementationen — en `httpx`-klient i varje adapter — hade spridit
gränsen över fyra filer och gjort "vad når produkten ut till" till en fråga man
besvarar genom att läsa all kod.

Tre saker behövde bestämmas, inte antas:

1. **Vart** trafiken får gå.
2. **Vad** den får göra när den kommer fram.
3. **Var** credentials lever, och vad som händer med dem i en säkerhetskopia.

## Beslut

### 1. En modul, en policy per leverantör

`app/integrations/egress.py` är den enda platsen produkten talar med ett system
den inte äger. Varje leverantör deklarerar en `EgressPolicy`: exakta värdar för
API-läsning, exakt auktoritetsvärd, exakta token-sökvägar. En URL utanför den
listan vägras innan en socket öppnas.

Omdirigeringar följs inte automatiskt. En `Location` kontrolleras med **samma
funktion** som originalanropet, för en allowlist som bara granskar första hoppet
är en allowlist man kan bli utledd ur.

### 2. GET för data. Den enda POST:en är bunden till token-endpointen

Det finns ingen allmän POST, ingen PUT, ingen PATCH och ingen DELETE i klassen.
Att läsa någons brevlåda eller reskontra är en GET; `token_post` är en separat
metod som bara accepterar leverantörens auktoritetsvärd och dess deklarerade
token- eller login-sökväg.

Det här är det som gör "read-only" till något annat än en avsikt, och det är
särskilt viktigt mot **Fortnox, vars scopes inte är uppdelade i läs och skriv**:
`supplierinvoice` ger båda, och det finns ingen smalare behörighet att be om.
Read-only mot Fortnox vilar därför på tre kontrollerbara saker — inget skrivande
verb i adaptern, ingen skrivande metod i egress, och en testsvit som prövar
båda — inte på en behörighet.

Mot Microsoft är behörigheten däremot verklig och används: `READ_SCOPES` är en
konstant i `graph_mail.py`, så ingen inställning, konfigurationsfil eller
återställd säkerhetskopia kan begära `Mail.Send` eller `Mail.ReadWrite`.

### 3. Transporten är ett argument

`ReadOnlyEgress` tar sin transport som parameter. I produktion är den `httpx`; i
testsviten är den en stub som kräver exakt rätt begäran och svarar ur en
ruttabell.

Det är inte en teststilfråga. Det är det som gör att hela integrationen —
inklusive varje vägran — går att pröva utan credential, utan nät och utan
inspelad trafik, och därmed att egenskapen "testsviten behöver ingen
credential" fortfarande gäller efter att produkten fått liveintegrationer.

### 4. Credentials ligger i föreningens katalog, och aldrig i en säkerhetskopia

Hemligheterna hamnar i `tenants/<förening>/integrations/credentials/`, `0600` i
en `0700`-katalog. Det ärver tenantisoleringen i stället för att återuppfinna
den: `registry.delete()` sveper dem utan att någon behöver komma ihåg att de
finns.

`create_backup` hoppar över katalogen vid namn och skriver antalet uteslutna
filer i manifestet. Följden är att en återställd installation visar
integrationerna som anslutna men oanvändbara tills någon loggar in igen, och den
följden är avsedd. En säkerhetskopia är den artefakt som mest sannolikt lämnar
maskinen — kopierad till ett USB-minne, mejlad till en konsult, återställd på en
reservdator — och en refresh-token i den är ett stående tillstånd att läsa någons
brevlåda som överlever varje samtal om vem som fick det.

### 5. Ingen kryptering, och det sägs rakt ut

Ett krypteringslager övervägdes och valdes bort. En nyckel som ligger bredvid
sin kryptotext skyddar mot exakt en sak, och på en enanvändarinstallation skulle
nyckeln ligga i samma hemkatalog under samma rättigheter som filen den skyddar.
Det som faktiskt skyddar de här bytena är filrättigheterna — samma skydd
`auth.db` får för lösenordshashar och levande sessioner.

Att implementera ett chiffer för att få skyddet att *se* starkare ut vore värre
än att beskriva det som det är, särskilt i en produkt vars hela poäng är att
inte påstå mer än den kan visa.

## Följder

* Nätverksprofilen för den installerade produkten är nu: modelltjänsten (ADR
  0002), plus `login.microsoftonline.com` och `graph.microsoft.com` när en
  brevlåda är ansluten, plus `apps.fortnox.se` och `api.fortnox.se` när ett
  ekonomisystem är det. Ingen anslutning innebär ingen ny utgående trafik alls.
* Anslutningarnas status visar värdlistan och behörigheterna direkt ur koden, så
  en styrelse kan se vad installationen får göra utan att fråga någon.
* En ny leverantör är en ny `EgressPolicy` och en ny adapter. Den kan inte råka
  få en skrivväg, eftersom det inte finns någon att ärva.

## Vad det inte löser

Att produkten inte skriver är kontrollerbart. Att rätt personer läser är det
inte — vem som äger brevlådan, vilken Fortnox-användare integrationen loggar in
som och vilka fält styrelsen lagligen får läsa är beslut som ligger utanför
programmet och står som sådana i integrationsdokumenten.
