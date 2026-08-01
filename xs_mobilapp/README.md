# Källa — mobilklienten för BRF Dokument-AI

Föreningens dokument, med källa. Ställ en fråga, få ett grundat svar, tryck på
källan och se passagen markerad på rätt sida — eller ett tydligt besked när
underlaget inte räcker.

Byggd mot samma backend, samma auth och samma citatverifiering som
pilotprodukten. Klienten fattar inga egna beslut om vad som är belagt: den
visar det backenden har verifierat.

Riktningen finns i [docs/APP-BUILD-BRIEF.md](docs/APP-BUILD-BRIEF.md).

## Kom igång

Backenden måste köra först (från repo-roten):

```bash
cd backend && uv run uvicorn app.main:create_app --factory --port 8787
```

Sedan appen:

```bash
cd xs_mobilapp
npm install
npm run dev
```

Öppna <http://localhost:5174/m/>. Vite proxar `/api` till `:8787`, så appen och
API:t delar origin även i utvecklingsläge — sessionskakan fungerar utan
CORS-undantag och utan token i JavaScript.

I dev-läge listar inloggningen demokontona. `bo@gjutformen12.se` /
`gjutformen-medlem-2026` är en vanlig styrelseledamot; `max@demo.se` /
`max-demo-2026` är med i två föreningar och är den att använda för att prova
föreningsbyte.

### Produktionsläge

```bash
npm run build
```

Backenden serverar då bygget på `/m` från sin egen origin — ingen separat
webbserver, ingen CDN, ingen extern host.

## Test

```bash
npm test          # enhetstester (vitest)
npm run test:e2e  # browseracceptans (playwright, startar egna processer)
npm run lint
npm run typecheck
npm run build
```

E2E startar en isolerad backend med `BRF_LLM=scripted` i en temporär datarot.
Auth, tenantskopning, lagring, retrieval, citatverifiering, sidrastrering och
markeringsplacering är **verkliga** — bara generering är deterministisk.

Backendsidan av den här appen testas i repo-roten:

```bash
cd backend && uv run pytest tests/test_page_image.py tests/test_mobile_static.py
```

## Så fungerar den

```
Fråga ──► POST /api/brf/{id}/ask ──► svar + verifierade citat
                                          │
                          citat: {document_id, page, rects[]}
                                          │
                     GET .../page/{n}?w=1080  (PNG från PyMuPDF)
                                          │
                          markering = rect × (bildbredd / sidbredd)
```

**Ingen pdf.js.** Backenden rastrerar sidan och klienten ritar rutor ovanpå
en `<img>`. Citatens rects är redan i PDF-punkter med origo uppe till vänster
— samma rum som rastreringen — så hela transformen är en skalfaktor:

```ts
left = x0 * (bildbreddPx / sidbreddPt)
```

Ingen y-flip, ingen viewport-matris, ingen rotationshantering i klienten.
Desktopappens `PdfPane.jsx` behöver allt det bara därför att pdf.js arbetar i
ett y-uppåt-koordinatsystem. Sidoeffekten är att appen slipper ~1 MB
PDF-motor och att en sida blir ~95 kB som går att cacha offline.

### Källan öppnas på passagen, inte på sidan

En A4-sida som pressas ned i en telefons bredd renderar 10-punktstext i
ungefär fem pixlar: markeringen syns, orden gör det inte. Eftersom hela
poängen är att räcka fram telefonen till någon annan zoomar källvyn till
**raden**, inte till sidan.

`lib/rects.passageZoom()` räknar fram zoomen ur citatets egen rect-höjd — den
faktiska radhöjden — så den anpassar sig till både storstilta stadgar och
täta årsredovisningar, och stannar på 1 när sidan redan är läsbar. Sidan
scrollas så att passagen ligger i vy; en rad som är bredare än skärmen
landar på sin *början*, eftersom man läser från vänster. `Hela sidan` växlar
till helsidesvy. Pinch-zoom finns kvar ovanpå.

### Vad som ligger på telefonen

Bara två saker, båda härledda och båda utbytbara:

| | Innehåll | Livslängd |
|---|---|---|
| Svarsjournal | fråga, svar, citat, tidpunkt | 30 dagar, rensbar, **raderas vid utloggning och utgången session** |
| Sidbildscache | rastrerade sidor | **raderas vid utloggning, utgången session och föreningsbyte** |

Sidbilderna skickas med `Cache-Control: private, no-store`. Bytesen är
visserligen oföränderliga, men webbläsarens HTTP-cache är inget appens
utloggning kan tömma — en kopia där skulle överleva sessionen på en delad
telefon, utanför den tenant-namngivna lagringen som hela raderingslöftet
vilar på. Service workern rör aldrig `/api`, så ingen föreningsdata hamnar i
Cache Storage heller.

Varje nyckel är prefixad med `brf_id`. Det är en säkerhetsgräns, inte
städning: backendens isoleringssvit bevisar att förening A aldrig når
förening B, och en odelad klientcache skulle lämna tillbaka precis den läckan.
`src/state/localStore.test.ts` och acceptanssviten failar om det glider.

## Struktur

```
src/
  api/          typad klient mot backendens HTTP-kontrakt
  app/          router (~60 rader) och skärmsammansättning
  components/   AppFrame, CitationChip, Finding, Watch, KallaSheet, Notice,
                ikoner
  lib/          rects (transformen), refusals (vägranstexter), findings,
                watches, format
  screens/      Login, ValjForening, Fraga, Svar, Bibliotek, Dokument,
                Granskning, Bevakningar, Konto, Lock
  state/        session, localStore (IndexedDB), usePageImage, useOnline, lock
  styles/       tokens.css (designsystem), app.css (komponenter)
e2e/            browseracceptans + tillgänglighet
```

## Designsystem i korthet

Ljus och pappersnära, för att det användaren tittar på är en vit sida ur ett
riktigt dokument. Mörkt läge dämpar **bara** ramverket — sidbilden inverteras
aldrig, den är bevismaterialet.

- En accent (`--action`). Grönt för verifierat citat.
- **Vägran är gul, aldrig röd.** När produkten vägrar gör den rätt. Rött är
  reserverat för sådant som faktiskt är trasigt: nätverk, session, modell.
- Markeringen tonas in 120 ms efter att sidan målats — ögat ska landa på
  passagen, inte leta efter den.
- Ingenting signaleras med enbart färg: verifierat har bock, ungefärligt har
  streckad kant plus texten ”ungefärlig markering”.

## Gränser

- **Granskningen är en läsvy.** Fynden ur fakturagranskningen
  (`docs/INTEGRATIONSDOMAN.md`) visas med sina citat, men klienten känner inte
  till beslutsendpointen: att godkänna, avfärda, korrigera eller bekräfta ett
  leverantörsalias är ett ställningstagande med en person bakom sig och görs i
  webbappen. Fynden cachas inte heller på telefonen — det som ligger kvar där
  är de två raderna i tabellen ovan, ingenting mer.
- **Bevakningarna är också en läsvy.** De daterade skyldigheterna visas
  grupperade som servern grupperat dem — hinkarna, etiketterna och
  dagräkningen är backendens, så telefonen och webbappen aldrig kan vara oense
  om vad ”snart” betyder. Klienten känner varken till `scan`, beslutet eller
  raderingen: att godkänna en bevakning är att föreningen åtar sig något.
  Förslag ligger under en egen rubrik som säger att ingen tagit ställning till
  dem ännu. Inte heller bevakningarna cachas på telefonen — tabellen ovan är
  fortfarande hela sanningen om vad som ligger kvar där.
- **Ingen uppladdning eller kamera.** Väntar på OCR-gaten (`docs/SLUTRAPPORT.md` §5).
  Administration sker i webbappen.
- **Ingen strömning** av svar (XS-21, parkerad). Väntetiden beskrivs i stället
  ärligt i två steg.
- **Kodlåset är ett lokalt UI-lås**, inte en ny inloggning mot servern. Det
  kräver säker kontext (https eller localhost) och göms annars.
- **Frågor köas aldrig offline.** Ett svar som genereras timmar senare, mot en
  korpus som kan ha ändrats, utan att användaren är där för att läsa en
  eventuell vägran, är en grundningsrisk. Appen säger nej i stället.
- Webbappar kan inte sudda sig själva i OS:ets appväxlare. Accepterad gräns.
