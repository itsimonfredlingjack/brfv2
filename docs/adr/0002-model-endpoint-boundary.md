# ADR 0002 — Modellgränsen: vem får peka om, och vart

Status: **antagen** (XS-49, 2026-07-28)
Ersätter: XS-47:s "vilken http- eller https-URL som helst, valfritt inloggat konto".

## Problemet

XS-47 beskrev produkten som *kontrollerat självhostad*. Implementationen sa
något annat på två punkter, och båda gick att kontrollera i koden:

1. **Vem.** `PUT /api/desktop/model-runtime` krävde bara en giltig session.
   Vilket konto som helst på installationen kunde alltså peka om den tjänst
   *alla* föreningars dokument skickas till. Det är inte en föreningsfråga; det
   är en fråga om själva installationen.
2. **Vart.** Adressen validerades med `https?://[^\s/][^\s]*`. Det tillåter
   `https://api.openai.com/v1` lika gärna som `http://127.0.0.1:8000/v1`. En
   regel som accepterar varje destination på internet beskriver ingen gräns —
   den beskriver bara ett URL-format.

Ingen av dem var en bugg i en enskild rad. Båda var *en gräns som fanns i texten
men inte i produkten*.

## Beslut

### Behörighet: installationsadministratör

En ny, uttrycklig behörighet i `AuthStore` — `installation_admins` — skild från
medlemsrollerna `member`/`admin`, som handlar om vad ett konto får göra *inom en
förening*. Den ges en gång, till kontot som konfigurerar installationen vid
första start, och det finns ingen route i den levererade produkten som delar ut
den till någon annan.

`PUT /api/desktop/model-runtime` och `POST /api/desktop/model-runtime/test`
kräver den. `GET` gör det inte: adressen är den proveniens som visas under varje
genererat svar, och att läsa den är inte det priviligierade steget.

En installation som återställs från en säkerhetskopia tagen före den här
behörigheten fanns adopteras vid start — kontot som skapades först är det som i
praktiken redan hade rollen. Alternativet vore en maskin där ingen kan byta
modelltjänst.

### Destination: två namngivna driftklasser, allt annat nekas

Regeln bor i `app/model_endpoint.py` och är default-deny:

| Klass | Värdar | Scheman |
| --- | --- | --- |
| `loopback` | `localhost`, `127.0.0.0/8`, `::1` | `http`, `https` |
| `private-network` | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7` | endast `https` |

Portar: 1–65535. När destinationsvärden redan är bunden till de två klasserna
tar en portbegränsning inte bort någon nåbar destination, så den finns inte.

Nekas, med varsin stabil kod:

* alla scheman utom `http`/`https` (`scheme_not_allowed`);
* **alla domännamn utom `localhost`** (`hostname_not_allowed`) — ett namn är en
  föränderlig indirektion, så en namnbaserad tillåtelse är inte en
  destinationstillåtelse;
* publika IP-adresser (`address_not_self_hosted`);
* `http` mot en adress utanför datorn (`plaintext_off_host`) — förfrågan bär
  frågan och ordagranna utdrag ur föreningens dokument;
* länklokalt `169.254.0.0/16` och `fe80::/10` (`link_local_address`), där
  molnens metadatatjänster bor;
* IPv4-inbäddade IPv6-former (`ambiguous_address_form`);
* användarnamn/lösenord i adressen, frågesträng och fragment.

`https` krävs utanför datorn men inte på loopback. Det är inte inkonsekvens:
på loopback lämnar bytesen aldrig maskinen, och pilotens topologi — en
SSH-forward till `agenntserver` — är just loopback för klienten.

### Kontrollen sitter i typen, inte i routen

`ModelRuntimeConfig.normalized()` anropar policyn, och `apply_model_runtime()`
gör om kontrollen precis innan adressen blir processtillstånd. Därför gäller
den för alla vägar in, inte bara för HTTP-API:t:

* en handredigerad `desktop-config.json` — filen är skrivbar för OS-användaren,
  så det som står i den är ett förslag, inte ett beslut. En otillåten adress
  loggas och installationen startar **utan** modelltjänst;
* en återställd säkerhetskopia;
* framtida kod som råkar konstruera en konfiguration själv.

Policyn publiceras dessutom maskinläsbart på
`GET /api/desktop/model-endpoint-policy` och i `/api/desktop/state`, och det är
samma `policy_document()` som testerna, gränssnittet och acceptansevidensen
läser. Det finns ingen andra kopia som kan glida isär från koden.

## Vad detta *inte* är

Det är inte ett skydd mot OS-användaren själv. Den som kör som samma
Unix-användare kan läsa och skriva applikationens data direkt, utan att gå
genom API:t. Gränsen som flyttas här är produktens egen: vilka destinationer
den *själv* kan förmås att kontakta, och vem som kan förmå den. Den lokala
tillitsgränsen är oförändrad och står kvar i leveransdokumentationen.

Samma origin- och IPC-arkitektur som XS-46 bevisade är också oförändrad: tom
`capabilities`, `withGlobalTauri: false`, inga plugins, och UI + API från exakt
samma loopback-origin.
