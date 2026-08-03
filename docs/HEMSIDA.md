# Hemsidan

En bostadsrättsförening som redan har sina dokument, sin post, sina fakturor och
sina åtaganden i den här produkten kan också bygga den sida medlemmarna faktiskt
läser — utan ett andra system, en andra inloggning och ett andra ställe där en
uppgift kan vara fel.

Det är inte en sidbyggare som råkar ligga i samma app. Tre saker skiljer den
från en, och resten av det här dokumentet handlar om varför de tre är samma
beslut.

## 1. En sida är strukturerad data, aldrig HTML

En sida är en lista av **block** av deklarerade typer med deklarerade fält,
lagrad som produktens egen schemaversionerade JSON:

```json
{
  "id": "page-4f1c2a",
  "slug": "start",
  "draft": {
    "title": "Startsida",
    "content": [
      {
        "id": "block-9c1e",
        "type": "ImportantNotice",
        "props": {
          "heading": "Stambytet börjar i port 12",
          "body": "<p>Arbetet startar i trapphus A.</p>",
          "tone": "warning"
        },
        "grounding": "authored",
        "sources": []
      }
    ]
  }
}
```

`backend/app/website/components.py` är auktoriteten på vad som får stå där.
Elva blocktyper, deras fält, och ingenting annat: det finns ingen `html`-typ,
ingen `custom`, inget fritt stilfält. En sida som ingen granskat, i en layout
ingen ritat, med ett påstående ingen kan spåra, går helt enkelt inte att
uttrycka.

Rich text är det enda stället där formatering alls är tillåten, och även där
bara de element `backend/app/website/sanitize.py` släpper igenom. Den modulen
**vägrar** i stället för att tvätta bort: en sanerare som tyst tar bort det den
inte känner igen förvandlar en dålig indata till en *tyst annorlunda* utdata, och
då står det något på sidan som ingen skrivit och ingen läst. Samma kontroll
gäller det redigeraren producerar och det en modell producerar, för i samma
sekund som de två vägarna skiljer sig är det den svagare som kommer att användas.

### Blockvokabulären

| Typ | Namn | Till vad |
| --- | --- | --- |
| `Hero` | Toppsektion | Sidans första intryck |
| `TextSection` | Text | Löpande text med rubrik |
| `ImageWithText` | Bild och text | Huset, gården, ett projekt |
| `ImportantNotice` | Viktigt meddelande | Det de boende behöver veta nu |
| `NewsList` | Nyheter | Korta notiser i datumordning |
| `Calendar` | Kalender | Stämma, städdag, container |
| `Faq` | Frågor och svar | Det som ändå frågas |
| `ProjectStatus` | Projektstatus | Var stambytet står, steg för steg |
| `ContactCard` | Kontakt | Vem man når, och hur |
| `FaultReport` | Felanmälan | Vägen in när något är trasigt |
| `DocumentList` | Dokument | Föreningens egna handlingar ur arkivet |

`DocumentList` pekar på dokument som redan finns i föreningens arkiv, och
backend vägrar ett dokument-id som inte är den här föreningens — 404-regeln
tillämpad på ett fält.

### Låset mellan de två deklarationerna

Vokabulären finns deklarerad två gånger: en gång i Python (som validerar) och en
gång i React (som ritar). Två deklarationer av en sak glider isär, och när de
gör det är felet tyst och obehagligt — redigeraren erbjuder ett fält backend
vägrar, och den första som märker det är en styrelseledamot vars sida inte går
att spara.

Därför är paret låst till `backend/app/website/VOCABULARY.lock.json`. Ett
backend-test kontrollerar Python mot låsfilen, ett frontend-test kontrollerar
React mot samma fil. Efter en medveten ändring av vokabulären:

```bash
make website-vocabulary-lock   # spela in på nytt
make website-vocabulary-check  # kontrollera utan att skriva
```

Samma disciplin som `app/invoices/RULES.lock.json`.

## 2. Det finns exakt ett sätt att ändra något

Varje ändring — någon som drar en sektion, någon som skriver i en rubrik,
AI-partnern som skriver om ett stycke, och ångringen som tar tillbaka något av
det — kommer in som ett **kommando** till `backend/app/website/commands.py`, och
valideras och tillämpas där. Det finns ingen andra väg.

```json
{
  "command": "move_block",
  "page_id": "page-4f1c2a",
  "block_id": "block-9c1e",
  "after_block_id": "block-77b0"
}
```

Kommandon: `read_page`, `insert_block`, `update_block`, `update_text`,
`move_block`, `delete_block`, `duplicate_block`, `replace_image`, `create_page`,
`rename_page`, `delete_page`, `update_navigation`, `set_publish_window`,
`confirm_block`, `update_settings`.

Tre av dem får AI:n inte utföra, och alla tre av samma skäl: de ändrar vad en
*besökare* ser eller vem som står för texten. `update_settings` (webbplatsens
publika namn), `set_publish_window` (en spak som kan ta ned en publicerad sida)
och `confirm_block` (att gå i god för text — det enda som absolut inte får vara
tillgängligt för den som skrev den).

Det ger fyra saker som annars bara vore avsikter:

- **Valideringen sker på ett ställe.** Ett värde redigeraren skulle vägra vägras
  för modellen också, för ingen av dem validerar något — det gör motorn.
- **Modellen kan inte hitta på en komponent.** `insert_block` slår upp sin typ i
  vokabulären eller kastar. Det finns ingen fri nod.
- **Behörigheter gäller lika.** Rutten avgör vem som får skicka kommandon;
  motorn bryr sig inte om vem som skrev dem, utom där skillnaden är hela poängen
  (grundning, och publiceringen som en modell aldrig får utföra).
- **Ångra är inget specialfall.** Att tillämpa ett kommando ger tillbaka de
  kommandon som skulle vända det, så ångringen går in genom samma dörr och
  valideras som allt annat.

Klienten skickar aldrig tillbaka en sida. Den säger *flytta det här blocket
under det där*, och motorn läser sidan under lås och gör det. Två personer som
redigerar samma sida ger därför två ändringar i stället för att den ena tyst
vinner — felet den här kodbasen redan lärt sig av i `app/history.py`.

### Redigeraren talar samma språk

Puck (`@puckeditor/core`, fastnaglad på 0.22.4) har en egen aktionsvokabulär,
adresserad med index och zon. `websiteCommands.js` översätter den till
produktens, adresserad med block-id. En `replace`-aktion bär ett helt
komponentobjekt; översättningen reducerar den till *de fält som faktiskt
ändrats*, för att skicka objektet vidare vore precis den ersättningsskrivning
resten av kodbasen har byggts om för att slippa.

Bulk-aktioner (`setData`, `set`) vidarebefordras aldrig — de är vad vi själva
skickar för att synka canvasen efter en AI-ändring, och att eka tillbaka dem
vore att förvandla en uppdatering till en skrivning.

## 3. Grundningen överlever ett blankt papper

Produktens hela anspråk är att den hellre vägrar än hittar på. En sidbyggare är
där det är lättast att tappa: ingen har ställt en fråga, så det finns inget svar
att verifiera — modellen har blivit ombedd att *skriva något*, och prosa som
komponeras för att fylla en sida är precis den prosa som uppfinner ett belopp,
ett datum eller en frist ingen kan peka på.

Så samma grind som skyddar ett svar skyddar en publicerad sida.
`backend/app/website/grounding.py` återanvänder
`app.numeric_grounding.check_numeric_grounding` i stället för att odla en andra,
svagare regel bredvid den. Varje materiellt tal i text en modell skrivit måste
finnas i något som faktiskt stöder det, annars vägras kommandot och ingenting
skrivs.

Behöver modellen en uppgift ur föreningens egna handlingar sätter den
`grounded_from` på operationen. Då körs den vanliga hämtnings- och
verifieringskedjan (`app.answer.ask`), och bara de citat den kedjan **verifierat**
fästs på blocket. Vägrar den, vägras ändringen.

### Den enda ärliga skillnaden mot svarsvägen

`app/numeric_grounding.py` varnar för att användarens egen fråga aldrig får
stödja ett svar, och det är rätt där: den som frågar "stämmer det att avgiften
höjs 4%?" har inte belagt något.

Att författa är en annan handling. När en styrelseledamot skriver *"skriv att
vattnet stängs av 12 mars 08–15"* är datumet inte ett påstående modellen
producerat — det är föreningen som talar om för sin egen webbplats vad den ska
säga, och det är föreningens att säga. Att vägra det vore inte att skydda någon;
det vore bara att göra funktionen oanvändbar för de anslag den finns till för.
Så operatörens egen instruktion är stöd **här och ingen annanstans**, och den
avgränsningen är skälet till att grinden bor i sin egen modul.

### Det som inte har någon siffra i sig

Sifferkontrollen fångar ett påhittat belopp, för ett tal finns antingen i ett
verifierat citat eller inte. Den fångar inte *"Grillning är förbjuden i
föreningen"* — ingen siffra, helt påhittat, och det passerade tidigare som
`editorial` och gick att publicera som vad som helst.

Produkten låtsas inte kunna avgöra det där semantiskt. Den gör i stället det
den gör överallt annars: **motorn föreslår, en människa bestämmer.** Prosa som
en modell skrivit utan källa märks `unverified`, ligger kvar i utkastet, syns
tydligt — och **sidan går inte att publicera** förrän någon står för den. Att
skriva om texten är att stå för den; det är också att trycka "Bekräfta texten".
Ingetdera kan modellen göra åt sig själv.

Ett block bär alltså sitt ursprung: `authored` (föreningen skrev det),
`grounded` (ur egna dokument, med citaten fästa), `editorial` (AI-formulerad
rubrik — en etikett kan inte bära en sakuppgift) eller `unverified` (AI-skriven
prosa som väntar på en människa).

## 4. Utkast, version, publicering, återställning

- **Redigering sker i ett utkast.** Allt en person eller AI:n gör landar där.
- **Publicering skapar en oföränderlig version.** Utkastet kopieras till en
  numrerad `PageRevision` som aldrig skrivs om.
- **Publiken ser en publicerad version**, renderad av *samma*
  komponentkonfiguration som redigeraren använder. Det finns ingen andra,
  genererad representation av en sida någonstans i funktionen.
- **Gränsen gäller hela sidan, inte bara dess mitt.** Adressen (`slug`) ligger i
  versionen; menyn och webbplatsens inställningar publiceras som en egen
  ögonblicksbild (`SiteChrome`). Att byta namn på en sida, plocka bort en
  menypost eller döpa om föreningen ändrar därför ingenting en besökare ser
  förrän någon publicerar. Det gjorde det tidigare — och menyn var något
  AI-partnern fick flytta om i.
- **En publicerad sida kan inte raderas under fötterna på publiken.** Ta ned den
  först (avpublicera), sedan går den att ta bort.
- **Återställning skriver inte om något.** En äldre version publiceras en gång
  till, och historiken säger det. Utkastet lämnas orört: att gå tillbaka till
  vad publiken såg är inte samma beslut som att kasta det någon skrivit sedan
  dess.

Versionerna ligger i egna filer (`revisions/<id>.json`), utkastet och menyn i
`site.json`. Vid publicering skrivs versionsfilen **först** och pekaren sedan:
en krasch däremellan lämnar en föräldralös fil som ingenting refererar, vilket är
ofarligt. Den andra ordningen skulle lämna en sida vars publicering pekar på
innehåll som inte finns, vilket inte är det.

**Publicering finns inte i kommandovokabulären.** En modell kan skriva hela
webbplatsen och ändå inte visa något av det för någon. "Ingenting blir publikt
förrän en människa publicerar det" är därför inte en regel AI:n ombeds
respektera — det är en hon inte har något sätt att uttrycka.

## 5. Arbetsytan

Tvåkolumnad, skrivbordsfirst:

- **Vänster: AI-partnern** (~324 px, hopfällbar till en list). Samtalet, ett
  protokoll över vad AI:n ändrade, källorna bakom grundad text, vad som är
  markerat just nu, och "Ångra allt" per ändring.
- **Resten: webbplatsen**, i en `same-origin`-iframe så att sidans CSS är
  isolerad från appens, brytpunkter går att prova på riktiga bredder (390 /
  820 / full) och canvasen beter sig som den publicerade sidan.

Ingen permanent tredje kolumn. När ett block markeras kommer fälten i en
flytande panel över canvasen, med blockets egna åtgärder (flytta, kopiera, ta
bort) och — för text AI:n skrivit — källorna, som öppnar föreningens PDF på rätt
sida.

Blockbiblioteket är en låda över canvasen. Varje block går att både dra dit man
vill ha det och lägga till med ett klick; dragkällan ensam hade gjort "lägg till
ett avsnitt" till en precisionsövning med pekdon, utan väg via tangentbord.

En AI-ändring tillämpas **direkt i utkastet** — ingen abstrakt förhandsdiff. En
diff av strukturerade operationer är inte något någon kan granska; sidan är det.
Hela svängen blir en transaktion: *"AI-ändring: Ny sida för nya boende ·
6 operationer · Ångra allt"*.

## 6. Behörighet och isolering

Läsning kräver medlemskap; varje skrivning kräver `admin`, för föreningens
publika ansikte är inte något en enskild medlem ändrar. Samma
`tenant_store`/`require_admin` som resten av produkten, så isoleringen ärvs i
stället för att argumenteras om: webbplatsen ligger i föreningens egen katalog,
`registry.delete()` sveper den med allt annat, och en annan förenings sid-id
finns helt enkelt inte på den här disken — 404, aldrig 403.

Canvasen är skrivskyddad för en medlem via Pucks `permissions`, alltså samma
regel som backend uttrycker med en 403, sagd en gång till där den syns.

## 7. Var saker ligger

| | |
| --- | --- |
| `backend/app/website/components.py` | vokabulären — auktoriteten |
| `backend/app/website/commands.py` | kommandomotorn: validering, tillämpning, inverser |
| `backend/app/website/grounding.py` | grinden mot obelagda sakuppgifter |
| `backend/app/website/sanitize.py` | vad som får stå i ett textfält |
| `backend/app/website/models.py` | `SitePage`, `PageDraft`, `PageRevision`, `Publication` |
| `backend/app/website/store.py` | per-förening-lagring, låst läs–validera–skriv |
| `backend/app/website/ai.py` | leverantörsoberoende planerare: instruktion → kommandon |
| `backend/app/website/routes.py` | HTTP-ytan |
| `brfv2-mockup/src/components/website/` | arbetsytan, blocken, översättningen |
| `backend/scripts/website_acceptance.py` | resan genom den riktiga applikationen |

## 8. Känd begränsning: redigeraren i skrivbordsskalet

Redigeraren körs i dag **inte** i Tauri-skalets WebKitGTK (2.52 / JavaScriptCore
"Safari 60"). En transitiv beroendekedja — Puck → `@dnd-kit` →
`@preact/signals-core` — kastar `TypeError: Attempted to assign to readonly
property` när modulen körs, och samma kod fungerar i Chromium.

Två saker gör att det inte är produktens problem längre, och båda behövs:

- Arbetsytan laddas **när någon öppnar den**, inte vid start. Importerad med de
  andra arbetsytorna tog felet ned *hela applikationen* — ett tomt fönster före
  inloggningsrutan.
- Den ligger bakom en felgräns (`WorkspaceBoundary`), så ett fel där blir en
  skärm som säger vad som hände medan dokument, fakturor, post och uppgifter
  fortsätter fungera.

Backend, kommandomotorn, grundningen och publiceringsmodellen är oberoende av
detta och verifieras av `backend/tests/test_website*.py`. Webbleveransen
(Chromium) kör hela arbetsytan. `make website-acceptance` går igenom resan i den
riktiga applikationen och **felar i dag** vid steget som öppnar arbetsytan —
avsiktligt: den är kvitto på när begränsningen är löst, inte en resa som tystats
ned.

Funktionen finns bara i det kanoniska gränssnittet (webb/skrivbord). Den mobila
PWA:n och Android-appen har den inte, av samma skäl som de inte har Fakturor: en
telefon är inte där en förening bygger om sin webbplats.
