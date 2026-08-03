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

Den flyttas dessutom **bara framåt**. Ingenting hindrar en operatör från att
trycka "hämta nytt" två gånger, och den andra begäran väntar inte in den första.
Förr vann den som blev *klar* sist rakt av, så en långsammare hämtning som
startat tidigare och läst mindre kunde putta märket bakåt — och kön presenterade
om två veckors redan avklarat material. Skrivningen slås därför ihop i stället
för att ersätta, och märket tar det senare av de två.

Bara monotont hade dock infört motsatt fel. Ett meddelande som inte gick att
läsa **måste** erbjudas igen, och det gjordes förr genom att dra märket *bakåt*
under det — vilket ett märke som bara kan stiga hade tystat bort för alltid. Så
de två frågorna hålls isär: `high_water_mark` svarar på "hur långt har vi säkert
kommit" och stiger bara, medan `retry_from` svarar på "vad är vi fortfarande
skyldiga", sätts till det äldsta meddelande hämtningen misslyckades med, och är
det nästa hämtning faktiskt frågar ifrån. Att läsa om är gratis: hashen och
`external_ref` gör en andra syn av ett meddelande till ingenting.

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

**Och avgörandet självt står också kvar.** Att öppna igen nollställde tidigare
`resolution`, `decided_by` och `decided_at`. Det lät som "lägg tillbaka kortet"
och var i praktiken en radering: efteråt fanns ingenstans kvar att föreningen
någonsin avgjort posten, vem som gjorde det, varför, eller vad det skapade —
samtidigt som uppgiften det skapade låg kvar i Uppgifter med ett ursprung som
pekade tillbaka på ett kort som förnekade att ha gjort den. Nu **arkiveras**
avgörandet i stället, som en `DecisionRecord` i köpostens egen
`decision_history` (append-only), och `resolution` blir `None` precis som förr.
Kön läser likadant; historiken finns kvar. Det ligger på köposten och inte i en
ny lagring, av exakt det skäl kapitel 1 anger: det finns inget e-postarkiv här,
och ett andra ställe att leta efter vad som beslutats om ett meddelande hade
varit ett.

Samma sak gäller den grövre vägen `POST .../decision` med status `open`, som är
en återöppning under ett annat namn och var det sista stället som fortfarande
raderade.

**Att trycka två gånger är ett beslut, inte två.** En avgörandebegäran har en
idempotensnyckel (`resolution_key`) som består av allt begäran skulle *göra*.
Kommer identiskt samma begäran in igen — en klient som gjorde om efter timeout,
ett dubbelklick — svarar rutten med det som redan skedde i stället för att göra
det en gång till. Och allt som skapas har härlett id, så ett avbrott mitt i
(uppgiften skapad, kortet ännu inte avgjort) är säkert att göra om: omtaget
räknar fram samma uppgifts-id, får uppgiften som redan finns, och avslutar. Förr
gav samma omtag en andra likadan uppgift.

**Men att trycka två gånger på *olika* saker är två beslut, och då vägrar
rutten.** En avgjord post tar bara emot exakt samma begäran igen. En annan
begäran mot ett kort som redan bär ett avgörande ger **409** och skriver
ingenting alls. Det som annars hände var samma radering som återöppningen just
lagats för, fast genom den vanliga knappen: två ledamöter som gick igenom kön
samma söndagskväll, och den andres klick tog bort den förstes beslut, dess
motivering, vem som fattade det och listan över vad det skapade — utan att något
någonstans sa att det hänt. Att ändra ett avgörande är en riktig sak en styrelse
gör; den har en operation, och den operationen (öppna igen, avgör på nytt)
bevarar det tidigare beslutet i `decision_history`.

**Vad ett nytt beslut skapar är också nytt.** Uppgiftens och bevakningens id
härleds ur hela det normaliserade avgörandet, inte ur rubriken respektive
`kind` + datum. "Utred, ansvarig Bo, senast 1 oktober" pekade förr tyst på den
befintliga "Utred, ansvarig Anna, senast 1 september": styrelsen hade fattat ett
beslut som systemet avstått från att utföra, utan att säga det. Nu får varje
genuint annat beslut sin egen rad. Priset, sagt rakt ut: nyckeln täcker hela
begäran, så en granskare som öppnar igen och justerar *ett* fält får en andra
uppgift bredvid den första i stället för en ändrad. Det är rätt håll att fela
åt — två synliga rader går att reda ut, en rad som i tysthet motsäger beslutet
som skapade den gör det inte.

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

## 9. Resan genom den riktiga applikationen

Enhetstesterna visar att delarna gör rätt sak. `make intake-acceptance`
(`backend/scripts/intake_acceptance.py`) visar något annat: att **kedjan** går
att gå, av en människa, i det installerade Tauri/WebKitGTK-fönstret. Den kör
hela sträckan kapitel 1 ritar upp — en `.eml` någon plockat fram, proveniensen,
läsningen med sina citat, ett beslut som bevarar meddelandet *och* gör en
uppgift av det, den bevarade texten öppnad i arkivet på sidan citatet pekar på,
en återöppning, och ett nytt beslut.

Tre av påståendena går bara att kontrollera här och inte i en enhetstest:

- **Uppgiften bär ett verifierat citat in i det bevarade meddelandet.** Det är
  hela skälet till att ordningen är "bevara först" (kapitel 5).
- **Att öppna igen raderar ingenting.** Uppgiften står kvar, och det tidigare
  avgörandet ligger i postens `decision_history` medan `resolution` är tom.
- **Ett nytt beslut bevarar inte meddelandet en andra gång.** Arkivet växer inte
  med en dubblett, och `preserved_document_id` är samma som förut.

Ingen modell krävs, och det är avsiktligt: resan är grön på en maskin som aldrig
konfigurerat generering, vilket är samma påstående som kapitel 4 gör om golvet.
Evidensen — skärmbilder och ett maskinläsbart kvitto — hamnar i `docs/evidence`
under körningens etikett, och committad evidens skrivs aldrig över utan att
`--overwrite-evidence` begärs uttryckligen.
