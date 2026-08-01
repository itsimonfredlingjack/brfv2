# Källstyrda bevakningar och årshjul

Fakturagranskningen svarar på *stämmer den här räkningen*. Det här svarar på den
fråga en styrelse faktiskt förlorar pengar och fastigheter på: **vad skulle vi ha
gjort, när, och gjorde någon det?**

Produkten kunde redan läsa vad ett avtal säger om tid — uppsägningstider,
löptider, indexvillkor, datum. Det här blocket är vad som gör den läsningen värd
något: villkoren blir daterade åtaganden som en människa tar ställning till.

## 1. Vad en bevakning är

Tre regler, och det är samma tre som resten av produkten vilar på:

**Ingenting påstås som inte lästs.** Varje bevakning bär den passage dess datum
kom ur, ordagrant verifierad genom `app.citations.resolve_citation`, och öppnar
dokumentet på rätt sida med passagen markerad. En bevakning vars underlag inte
går att öppna är ett påstående, inte en bevakning — och den skapas inte.

**Ett förslag är inte ett beslut.** Allt motorn härleder kommer in som
`proposed`. En namngiven person godkänner, justerar datumet, utser ansvarig och
väljer hur långt i förväg påminnelsen ska komma. Fram till dess är det ett
förslag med ett citat, och det visas som ett.

**Ett odaterbart åtagande förblir odaterat.** En tidsfrist motorn inte kan
räkna ut blir en `UnresolvedObligation` som säger vad som saknas — aldrig en
kalenderpost byggd på en gissning, för den hade sett exakt ut som en riktig.

## 2. Domänen

`backend/app/watches/models.py`

| Fält | Innebörd |
| -- | -- |
| `kind` | `notice_deadline` · `expiry` · `warranty` · `inspection` · `recurring_obligation`. Fem sorter som en styrelse har olika rutiner för; en sort ingen behandlar annorlunda ska inte vara en egen sort. |
| `title` | Skriven som en instruktion — "Säg upp eller ompröva avtalet senast 2026-09-30" — inte som en etikett. |
| `due_date` vs `derived_due_date` | Vad som gäller, och vad motorn räknade fram. Båda sparas: att någon flyttade datumet är en del av spåret. |
| `derivation` | Räkningen i klartext: `2026-12-31 minus 3 månader`. En läsare ska kunna kontrollera den utan att lita på den. |
| `recurrence` | `none` · `monthly` · `quarterly` · `yearly` · `biennial` · `triennial`. |
| `responsible` | Tom sträng betyder att ingen är utsedd, och vyn skriver **"ej utsedd"** i stället för att lämna ett blankt fält som ser ut som att någon har det. |
| `remind_lead_days` | Hur långt före `due_date` bevakningen ska börja synas som *snart*. Per bevakning, inte globalt. |
| `citations` | `CitationOut` — samma typ, samma verifiering och samma rektanglar som ett svars citat. |
| `status` | `proposed` → `approved` / `dismissed` / `done`. |

## 3. Vad motorn läser

`backend/app/watches/derive.py`, ovanpå `backend/app/terms.py`.

| Regel | Exempel | Blir |
| -- | -- | -- |
| Uppsägning före ett skrivet datum | "sägs upp senast tre månader före den 31 december 2026" | `notice_deadline` 2026-09-30 |
| Uppsägning före en **citerad** avtalstids utgång | "gäller … till och med den 31 januari 2028. … sägas upp senast sex månader före avtalstidens utgång" | `notice_deadline` 2027-07-31 |
| Avtalstidens slut | "gäller 2026-01-01 – 2026-12-31" | `expiry` 2026-12-31 |
| Garanti räknad från ett datum | "garantitiden är fem år från slutbesiktningen den 12 maj 2024" | `warranty` 2029-05-12 |
| Besiktning med datum, med eller utan cykel | "genomförd senast den 31 maj 2026, och återkommer vart tredje år" | `inspection` 2029-05-31, `triennial` |
| Återkommande skyldighet med startdatum | "avläsning sker kvartalsvis från den 31 januari 2026" | `recurring_obligation`, `quarterly` |

Avtalstidens slut föreslås bara när ingen uppsägningsfrist hittades i samma
passage. Står båda är uppsägningsdatumet det någon måste göra något senast, och
två poster för ett åtagande gör en lista svårare att lita på, inte lättare.

### Datumaritmetiken

`shift_months` klämmer dagen nedåt i målmånaden: 31 december minus tre månader
är **30 september**, inte "31 september" och inte 1 oktober. Det är vad ett
svenskt avtal menar med "tre månader före" — fristen ligger inne i månaden, och
en frist som tyst flyttade till den 1:a i nästa månad hade varit en dag sen åt
det enda håll som spelar roll.

### Regeln som kostade mest att få rätt

Första versionen tog *närmaste* datum som ankare. Mot den seedade
snöröjningskorpusen gav det här:

> "Avtalet gäller från den 1 november 2026 och tills vidare. Uppsägning skall
> ske skriftligen senast tre månader före avtalstidens utgång."

…en bevakning med sista dag **2026-08-01** — tre månader före avtalets *början*.
Verifierbart, självsäkert och nonsens: klausulen räknar från ett datum som inte
står i dokumentet.

Ankaret måste nu uppfylla allt tre:

1. ett riktningsord står **efter** löptiden ("tre månader *före* …", "fem år
   *från* …") — ett "senast" framför löptiden är en bestämning av åtagandet, inte
   en operator på datumet;
2. datumet står **efter** riktningsordet, inom räckhåll;
3. **ingen mening slutar emellan**.

Klausulen ovan blir därför ingen bevakning alls, utan en odaterbar post som
säger att uppsägningstiden är tre månader men att avtalets slutdatum saknas.
Det är rätt svar, och det är ett svar styrelsen kan åtgärda genom att fylla i
det som saknas.

### När "avtalstidens utgång" ändå går att lösa upp

Den vanligaste formen i ett svenskt avtal säger båda sakerna, i olika meningar:

> "Avtalet gäller från och med den 1 februari 2026 **till och med den 31 januari
> 2028**. Om avtalet inte sägs upp förlängs det med tolv månader i taget.
> Avtalet får sägas upp skriftligen senast **sex månader** före avtalstidens
> utgång."

Slutdatumet står i dokumentet — bara inte bredvid fristen. Ankarregeln rör inte
det här (och ska inte göra det), så en egen regel löser upp frasen under
villkor som gör upplösningen till en läsning i stället för en gissning: en
**sluten** avtalstid citerad i samma passage, en uppsägningstid **efter** den,
och en klausul som uttryckligen pekar på ett slut ("utgång", "upphörande").
Vad regeln antog skrivs ut i `derivation`:

> `avtalstidens utgång 2028-01-31 enligt citerad avtalstid 2026-02-01 – 2028-01-31, minus 6 månader`

Två fällor i samma mening, båda verkliga och båda stängda med test:

* **Tolv månader är förlängningen, inte uppsägningstiden.** En scanner som tar
  närmaste tal rapporterar tolv. Ett förlängningsverb mellan uppsägningsordet
  och talet diskvalificerar talet, liksom ett meningsslut.
* **"sägas upp" räknades inte som uppsägning.** Ordlistan hade "säga" men
  varken "sägas" eller "sägs", så den vanligaste formuleringen lästes som att
  avtalet saknade uppsägningstid.

### Vad som inte scannas

Föreningens eget arkiv: uppladdade dokument, plus bilagor som en namngiven
administratör har **arkiverat** ur granskningskön. Material som fortfarande
ligger i kön är inte föreningens än — samma bevisregel som fakturagranskningen,
av samma skäl (se [INTEGRATIONSDOMAN.md](INTEGRATIONSDOMAN.md)).

## 4. Årshjulet

`GET /api/brf/{id}/watches` räknar ut hinkarna på servern, så att desktopvyn och
telefonen inte kan vara oense om vad *snart* betyder:

| Hink | Betyder |
| -- | -- |
| **Försenat** | Datumet har passerat. Gäller även en återkommande bevakning — ett missat åtagande är ingen rytm. |
| **Snart** | Påminnelsen har slagit till (`due_date` minus `remind_lead_days` är passerad). |
| **Senare** | Kommer, men inte än. |
| **Återkommande** | Har en cykel och ligger i framtiden. Egen hink för att ett årligt åtagande är något annat att planera kring än en engångsfrist. |

Förslag ligger **utanför** hinkarna. En blandad vy hade lärt användarna att
regelmotorns gissningar är föreningens åtaganden.

## 5. Att slutföra något återkommande

Markeras en återkommande bevakning som avklarad skapas nästa varv som en **egen
post**, och den avklarade behålls. Att i stället flytta fram datumet på samma rad
hade raderat historiken över vad som faktiskt gjordes, vilket är det enda en
bevakning finns till för att kunna visa i efterhand.

## 6. API

| Metod | Väg | Vad |
| -- | -- | -- |
| GET | `watches` | Hinkar, förslag, odaterbara och avslutade |
| POST | `watches/scan` | Läs om arkivet och föreslå (admin) |
| POST | `watches/{id}/decision` | Godkänn, justera, utse ansvarig, avfärda eller markera avklarad (admin) |
| DELETE | `watches/{id}` | Ta bort ett **förslag**. En bevakning någon tagit ställning till raderas inte — den markeras avklarad eller avfärdad |

Att avfärda kräver ett skäl. Samma regel som en korrigerad fakturagranskning:
att avfärda ett åtagande som motorn läst ur föreningens eget avtal är ett beslut
någon kan behöva försvara, och "ingen sa varför" är inget försvar.

En omkörd scan rör aldrig en bevakning någon beslutat om, och föreslår inte
heller om den — varken en godkänd eller en avfärdad. Att erbjuda samma avfärdade
åtagande varje vecka är hur en kö lär folk att strunta i den.

## 7. Vad som inte finns, och varför

Ingen kalenderintegration, ingen e-postpåminnelse, ingen push, ingen
bakgrundsjobb som skickar något. `remind_at` är ett *datum vyn sorterar på*,
inte ett utskick.

Det är medvetet och det är ordningen: en stabil intern åtagandedomän först, en
adapter mot någon annans kalender sedan — precis som fixtureadaptern kom före
Fortnox. En påminnelse som skickas någonstans är dessutom en utgående åtgärd, och
sådana går genom `egress.py` med allt vad det innebär (se
[ADR 0004](adr/0004-utgaende-integrationsgrans.md)).

Mobilen visar bevakningarna **read-only**. Beslut fattas där arbetet görs.

## 8. Verifiering

`backend/tests/test_watches.py` — datumaritmetiken inklusive klämningen,
ankarregeln och de tre fall den stänger, cykler, hinkarna, och att en bilaga i
kön inte scannas förrän den arkiverats.

`backend/tests/test_watches_http.py` — behörigheter (en medlem läser, en
administratör beslutar), tenantisolering över riktig HTTP, att ett beslut
överlever en omkörning, att en avfärdad inte föreslås igen, och att ett
återkommande åtagande får ett efterföljande varv med bevarad historik.

Ingenting i någon av dem behöver en credential, en nätverksendpoint eller en
körande modell.
