# Uppgifter och ansvar

Resten av produkten läser och föreslår. Ett fynd säger att en faktura kanske
inte stämmer med sitt avtal; en bevakning säger att en uppsägningsfrist går ut
ett datum. Ingetdera är arbete.

Det här är protokollet över att en människa bestämt att något **ska** göras, av
vem, till när — och det är medvetet den enda domänen i produkten som motorn inte
kan skapa något i.

## 1. Asymmetrin, och varför den finns

Fynd och bevakningar kommer in som *förslag*, för en regelmotor kan läsa ett
dokument. Ingens skyldigheter följer av det förrän en person tar på sig dem. Så
det finns ingen `proposed`-uppgift och ingen genomläsning som producerar en:
**att skapa en uppgift är beslutet**, och det sparas som ett.

Det är också därför det inte finns någon "föreslagen ansvarig". Ett namn som en
maskin satt dit är inte ett åtagande, och en lista där hälften av namnen är
gissningar är värdelös som ansvarsfördelning.

## 2. Tre egenskaper som gör en uppgift värd mer än en rad i ett block

**Bevisen följer med.** En uppgift skapad ur ett fynd eller en bevakning bär med
sig det ursprungets citat, så passagen bakom arbetet öppnas på rätt sida ett
halvår senare. Citaten **kopieras**, de refereras inte: en granskning kan köras
om och en bevakning omdateras, och uppgiften ska fortsätta säga vad den skapades
om i stället för att tyst omformulera sig själv.

**Historiken är append-only.** Varje ändring skriver en `TaskEvent` med vem och
när. Ingenting redigeras tyst, för "vem flyttade datumet, och när" är precis den
fråga som ställs efteråt. `TaskStore.update_task` vägrar en skrivning vars
historik är kortare än den som redan ligger på disk — regeln är alltså inte
beroende av att varje anropare kommer ihåg den.

**Den raderas aldrig.** En uppgift som funnits är ett protokoll över vad
styrelsen beslutade att göra. Arbete som visade sig onödigt **avbryts**, med ett
angivet skäl, och ligger kvar synligt. Det finns ingen delete-route.

## 3. Statusarna

| Status | Betyder |
| -- | -- |
| `open` — att göra | Beslutad, inte påbörjad. |
| `in_progress` — pågår | Någon håller på. |
| `blocked` — blockerad | Väntar på någon annan. **Kräver ett skäl.** |
| `done` — klar | Utförd. |
| `cancelled` — avbruten | Skulle inte göras. **Kräver ett skäl.** |

`blocked` förtjänar sin plats genom att vara den som behöver någon annan: en
stannad uppgift som ser ut som "att göra" i en lista är hur den förblir osynlig
i en månad.

Att markera något **klart** kräver ingen motivering — noten hade blivit ceremoni,
och spåret säger redan vem som stängde den och när. Att blockera eller avbryta
är där den uteblivna meningen är den någon senare önskar fanns.

## 4. Ursprunget

`finding` · `watch` · `source_event` · `manual`

`manual` är en fullvärdig medlem, inte en reservutgång: mycket styrelsearbete
börjar på ett möte och inte i ett dokument, och ett vokabulär som tvingade allt
att påstå en källa hade producerat falsk proveniens i stället för ärlig frånvaro.

`GET /tasks/for/{kind}/{ref_id}` finns för att en vy ska kunna säga "det finns
redan en uppgift för det här" i stället för att låta två personer skapa samma
uppgift en vecka isär — det felet som en gemensam kö ska förhindra, inte orsaka.

## 5. Vad som är försenat

En **avslutad** uppgift är aldrig försenad, hur sen den än blev. Frågan en
styrelse ställer om en stängd uppgift är om den blev gjord, inte om datumet höll.

Listan sorteras på servern: försenat först, sedan efter datum, och odaterat sist.
Odaterat är inte brådskande, det är **oplanerat**, och att lägga det över en
daterad uppgift hade varit en bedömning ingen gjort.

`counts.unassigned` redovisas för sig. Det är siffran som växer tyst.

## 6. API

| Metod | Väg | Vad |
| -- | -- | -- |
| GET | `tasks` | Aktivt, klart, avbrutet, plus etiketter och räknare |
| GET | `tasks/for/{kind}/{ref}` | Uppgifter som redan finns för ett ursprung |
| POST | `tasks` | Ta på sig arbete (admin) |
| POST | `tasks/{id}` | Ändra status, ansvarig, datum eller text (admin) |
| POST | `tasks/{id}/comment` | Säga något utan att ändra något (admin) |

Att sätta ett fält till det det redan är, utan kommentar, ger `422 Inget att
ändra`. En tom ändring som ändå skrev en historikpost hade fyllt spåret med
händelser där ingenting hände.

Läsning kräver medlemskap. Allt som skapar eller ändrar kräver `admin`, för en
uppgift är föreningen som tar på sig arbete och pekar ut vem som äger det.

## 7. Mobilen

Read-only. Samma lista, samma historik, samma citat som öppnar källan — och
inget sätt att skapa, ändra, tilldela eller kommentera. Skrivvägarna är inte
deklarerade i telefonens typade klient, så ett skrivförsök därifrån är ett
kompileringsfel och inte en granskningskommentar.

## 8. Vad som inte finns

Ingen påminnelse som skickas någonstans, ingen kalender, ingen tilldelning till
ett konto (ansvarig är ett **namn**, inte en användare — föreningen vet vem
Karin är, produkten behöver inte ett användarkonto för att skriva det). Ingen
eskalering, inga delegeringskedjor, ingen tidrapportering.

Ansvarig som fritext är ett medvetet val: att kräva ett konto per ansvarig hade
betytt att en vaktmästare, en entreprenör eller en revisor inte kan stå som
ansvarig utan att först bli användare i systemet — vilket är fel ände att börja
i, och en inloggning ingen bad om.

## 9. Verifiering

`backend/tests/test_tasks.py` — att bevisen följer med från både fynd och
bevakning, att varje ändring skriver sin egen händelse, att en tom ändring
vägras, att blockering och avbrytande kräver skäl, att en klar uppgift aldrig är
försenad, att avbrutet arbete ligger kvar synligt, att historiken bara växer,
att det inte går att radera, och att en bevakning i en annan förening inte kan
användas som ursprung.
