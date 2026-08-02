# Inkommande post

En brevlåda är råmaterial. Det här är granskningskön mellan brevlådan och
föreningens arkiv — och hela poängen med den är att det finns ett steg där, med
en människa i.

Flödet, från vänster till höger:

```
källhändelse → proveniens → koppling till befintligt material
             → förslag → mänskligt beslut → sökbar historik
```

Ingen ruta i den kedjan hoppas över, och den sista rutan når man bara genom den
näst sista.

## 1. Vad det inte är

Det är inte en e-postklient. Produkten skickar inte, svarar inte, markerar inte
som läst, flyttar inte och raderar inte — varken när posten kommer in eller när
den avgörs. En post som markeras "inte relevant" ligger kvar i brevlådan
precis där den låg. Den regeln är strukturell, inte en inställning:
`app.integrations.protocols` vägrar vid import att definiera en adapter med ett
skrivande verb i metodnamnet, och adaptern gör ingenting annat än GET.

Det är inte heller ett andra arkiv. Allt som bevaras från kön landar i domäner
som redan finns — dokument, uppgifter, bevakningar. Ett e-postarkiv vid sidan om
skulle ge föreningen två svar på "vad säger vårt avtal om uppsägningstiden", och
det andra svaret är det ingen underhåller.

## 2. Hämtning som frågar efter det nya

Första versionen av den här vyn listade de 25 senaste meddelandena varje gång
den öppnades. Efter fjorton dagar är det en vägg av sådant någon redan tagit
hand om, med de två nya begravda i mitten.

En hämtning frågar i stället: *vad har kommit sedan sist?* Tre delar, och ingen
av dem är en synkroniseringsslinga:

1. **En checkpoint.** `MailboxCheckpoint` håller tidsstämpeln på det nyaste
   meddelande som förra lyckade hämtningen faktiskt såg. Den ligger i
   föreningens egen katalog som allt annat här.
2. **En smalare läsning.** `receivedDateTime ge <checkpoint>` går till Graph, så
   filtreringen sker där meddelandena finns i stället för efter överföringen.
3. **En andra spärr som inte beror på klockor.** Varje kandidat jämförs mot
   köns egna `external_ref`, och importen vägrar fortfarande en dubblett på
   innehållshash. Två meddelanden kan dela sekund, en brevlåda kan migreras och
   flytta alla tidsstämplar — checkpointen är en optimering, hashen är regeln.

Checkpointen flyttas **bara vid framgång**. Ett misslyckat försök skriver
`last_error` och lämnar tidsstämpeln orörd, för en hämtning som aldrig kördes får
inte se ut som en som inte hittade något.

### Det som inte kunde tas in

`.eml`-formatet är smalt med avsikt: en bilaga som inte är PDF vägrar **hela**
meddelandet, så att ingenting halvimporteras (`docs/INTEGRATIONSDOMAN.md`). En
batchhämtning som tyst tappade dem skulle låta operatören tro att kön *är*
brevlådan. Så de rapporteras: ämne, avsändare, och den kod och mening parsern
vägrade med. Ingenting skrivs till kön för dem, och meddelandet ligger kvar i
brevlådan där det går att exportera för hand.

## 3. Trådar

Meddelanden grupperas till konversationer, och grupperingen är en **läsning** av
materialet — aldrig ett påstående om det. Två signaler, i den ordningen:

1. **Svarskedjan** (`Message-ID`, `In-Reply-To`, `References`). Rätt oftare än
   någon heuristik när den finns. Fortfarande text avsändaren skriver.
2. **Ämnesraden utan svarsprefix, plus de inblandades domäner.** Fallet där
   någon svarar i ett nytt meddelande. Avgränsat på domän så att två
   leverantörers separata "Offert" inte blir en tråd.

Ingen likhetsberäkning, ingen klustring. Ett trådkort visar alltid de enskilda
meddelanden det består av, så en gruppering som blev fel är synlig och ofarlig i
stället för en tyst sammanslagning.

Tråden avgörs **vid import** och sparas, så ett kort inte kan omgruppera sig
självt under en läsare. En post från ett äldre bygge har tom `thread_key` och
grupperas på ämne vid läsningen — ingen migrering bestämmer konversationer åt
någon i efterhand.

**"Ser ut att vänta svar"** är formulerat så med flit. Produkten läser inkommande
post och kan inte se styrelsens skickade mejl, alltså inte veta om någon redan
svarat. Det den kan se är att trådens nyaste meddelande ställde en fråga och att
ingen tagit ställning till det.

## 4. Bedömningen

Sju kategorier: `invoice`, `contract_or_quote`, `authority_or_manager`,
`decision_or_approval`, `question_awaiting_reply`, `information`, `unclear`.

`unclear` är en fullvärdig medlem och inget misslyckande. En kö som gissar en
kategori på ett meddelande den inte kunde läsa något i har börjat lära sina
användare att etiketten inte betyder något.

Tre regler, samma som granskningsmotorn och bevakningsmotorn lever efter:

**Ingenting påstås som inte lästs.** Varje fält bygger på en `TriageSignal` som
bär med sig de ord den lästes ur. Kortet visar värdet *och* meningen bakom det.

**Golvet är deterministiskt.** Kategori, datum, belopp, leverantör och kopplingar
kommer från regler över texten, med produktens egna läsare — `app.terms` och
`scan_amounts` ur granskningsmotorn, alltså exakt den kod som läser föreningens
avtal. De kräver ingen modell, inget nät och ingen inloggning, vilket är därför
kön fungerar på en installation som aldrig konfigurerat generering.

**En modell får förfina orden, aldrig fakta.** Är en riktig leverantör
konfigurerad ombeds den om två saker en regelmotor skriver dåligt — en rubrik
och en mening om varför posten spelar roll — och en sak den rimligen kan tycka
annorlunda om: kategorin. Svaret accepteras bara om kategorin finns i
vokabulären **och** meningen den anger som belägg återfinns *ordagrant* i
meddelandet. Annars står den deterministiska läsningen kvar och kortet säger att
en kontroll gjordes och inte höll. `suggested_by` säger vilket det blev:
`regelmotor` eller `regelmotor + språkmodell (<modell>)`. Signalerna, datumen och
beloppen rör modellen aldrig.

En bedömning är ett förslag. En människa kan sätta kategorin, och det sparas
**bredvid** förslaget, inte över det: paret är det enda spåret av var läsningen
tog fel.

## 5. Utfallen

| Utfall | Vad som händer | Domän |
| -- | -- | -- |
| `take_in` | Meddelandets text bevaras som dokument, och de bilagor granskaren valt läggs i arkivet | Dokument |
| `create_task` | Arbete med rubrik, ansvarig, datum och historik | `app.tasks` |
| `monitor` | Ett datum eller ett väntat svar på bevakningstavlan | `app.watches` |
| `already_handled` | Viktigt, men inget mer behöver göras | — |
| `not_relevant` | Ut ur kön. Brevlådan orörd | — |

De fyra första kombineras fritt; `already_handled` och `not_relevant` är
exklusiva. Ett protokoll som säger både "inte relevant" och "här är uppgiften jag
gjorde av den" är ett protokoll ingen kan agera på, så routen vägrar
kombinationen i stället för att spara den.

Ordningen är fast: **bevara först**. Det är bevarandet som producerar dokumentet
som uppgiftens och bevakningens citat pekar in i.

En avgjord post kan öppnas igen. Det den producerat står kvar — en uppgift som
gjorts av posten är ett beslut i sig, och att öppna ett kort är inget beslut om
den.

## 6. Att bevara meddelandet självt

Bilagan är inte poängen. Den dyraste posten en styrelse får bär ofta ingen fil
alls:

> "Vi godkänner offerten på 148 000 kr, sätt igång vecka 12."
> "Uppsägning måste ske senast tre månader före avtalstidens utgång."
> "Ni har tio dagar på er att svara på föreläggandet."

En produkt som bara bevarar PDF:er tappar varenda en av dem, och kan sedan inte
svara på "godkände någon offerten" ett halvår senare.

Så ett granskat meddelande kan bevaras — och det intressanta beslutet är *hur*.
**Det blir en PDF och går genom den vanliga ingestionen.** Inte en ny
e-posttyp med egen sökning, egen visning och egen sorts citat.
`Store.add_document` extraherar, chunkar och indexerar det; `app.citations`
verifierar citat mot dess sidord och målar rutor på dem; `app.answer` hämtar det
bredvid föreningens avtal och vägrar när det inte är relevant. Meddelandet öppnas
på sidan med meningen markerad, precis som en årsredovisning gör.

Det är värt kostnaden att rendera en PDF, och kostnaden är den ärliga delen: en
andra bevisväg hade betytt en andra citatlösare, en andra ordagrannhetsregel och
ett andra ställe där ett citat kunde "verifieras" av maskineri som ingen
angripit.

Sidan bär proveniensen i sig — avsändare, mottagare, båda tidsstämplarna,
Message-ID och innehållshashen på originalets MIME — så dokumentet är
självbeskrivande när någon öppnar det om två år utan kön framför sig.

**Ett bevarat meddelande är bevis.** Till skillnad från en bilaga behöver det
inget separat adoptionssteg: en namngiven administratör bevarade det, med ett
angivet skäl, vilket *är* adoptionströskeln. Det som fortfarande gäller är att
det inte får styrka en faktura som kom in i samma meddelande — se
`evidence_excluded_document_ids` i `app.integrations.review`.

## 7. Vad kedjan gör möjligt

När posten är granskad och bevarad går de här frågorna att ställa i chatten, med
citat tillbaka till originalmeddelandet, avsändaren och datumet:

- Vad sa leverantören om förseningen?
- Vilken avtalsversion skickades senast?
- Godkände någon offerten?
- Vilka frågor väntar fortfarande på svar?
- Vad är källan till den angivna uppsägningstiden?

Svaren är spårbara till originalet, inte till en genererad sammanfattning. Det
är samma refusal-kontrakt som resten av produkten: finns inget verifierbart
citat i föreningens eget underlag så vägras svaret.

## 8. Var koden ligger

| Fil | Ansvar |
| -- | -- |
| `app/integrations/mailbox.py` | Hämtning mot checkpoint, rapport över det som inte togs in |
| `app/integrations/threads.py` | Gruppering till konversationer. Härledd, aldrig lagrad |
| `app/integrations/triage.py` | Den deterministiska läsningen, och den valfria modellförfiningen |
| `app/integrations/preserve.py` | Meddelande → PDF → dokument → verifierat citat |
| `app/integrations/resolve.py` | Utfallen, och routningen in i dokument, uppgifter och bevakningar |
| `app/integrations/routes.py` | HTTP-ytan (`/integrations/intake`, `/mailbox/fetch`, `…/resolve`) |
| `brfv2-mockup/src/components/IntakeQueue.jsx` | Kön |

Tester: `backend/tests/test_intake_queue.py` och
`brfv2-mockup/src/IntakeQueue.test.jsx`. Ingen av dem behöver inloggning, nät
eller modell — vilket är en del av det som påstås: en kö som krävde det vore en
kö som inte gick att granska offline.
