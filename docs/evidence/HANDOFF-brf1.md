# Var BRF-1-arbetet står — handoff 2026-08-14

Skrivet för att nästa session ska slippa den här. Läs det här först, och
`fan-out-mvp-beslut.md` bara om du ska fatta grindbeslutet.

## Läget på en rad

Grenen `feat/brf-1-cross-document` är grön, 28 commits före `main`, **inte
pushad**. Ingenting är trasigt och ingenting väntar på att bli klart.

## Det enda öppna beslutet

**Ska grenen mergas till `main`?** Fan-out är avstängd bakom två spärrar
(`BRF_PLANNED_ASK` i servern, `planned` i anropet) och ingen av dem sätts någonstans
i produktionen, så vägen är onåbar och ändrar ingenting för användare. Resten av
grenen är verkliga förbättringar plus 1342 gröna tester.

Ingenting annat kräver ett beslut.

## Fan-out: siffran, en gång

Mot en budgetmatchad baslinje vinner den planerade vägen på **2 verkliga frågor av
11**, till tre sökningar plus ett modellanrop i stället för en sökning.

Det är hela underlaget. Mer mätning på det arkivet ger inget nytt — nio handlingar
är uttömda. Öppna frågan igen först när ett arkiv från en **annan** förening visar
samma mönster eller bättre.

## Tre saker som inte får glömmas bort

**`r01` är förbrukat som bevis.** Fallet har vänt fyra gånger på ändringar som
ingen handlar om ordförråd (katalogordning, sortering, borttaget `clarify`-läge,
expansionsgräns). Sista gången syns orsaken: ordet `pris` råkade matcha
`prisjustering`. Använd det inte som argument för någonting.

**Fel handling överst är det största mätta felet.** I 10 av 11 verkliga frågor låg
toppträffen i fel avtal, ofta med rätt stycke längre ner. Det syns inte i något
recall-tal. Tre billiga åtgärder är prövade och ingen rör det: bredare
bevisbudget, handlingens namn i indexet, lägre expansionsgräns. Den enda
obeprövade är cross-encoder-omrankning, som kostar ett beroende och en modell på
disk i en RPM-paketerad app.

**Läsbarheten är löst.** Sju av nio verkliga handlingar saknar textlager och
OCR:as automatiskt på 99 sekunder, med bättre ordlikhet än de digitalas egna
textlager. Slutsatsen från 2026-08-12 att läsbarhet är den bindande gränsen gäller
inte längre.

## Vad som är gjort i den här omgången

Läs `planner-vs-real-model.md` tilläggen 1–10 om detaljerna behövs. I korthet:
grindparitet och sorterad katalog, `clarify` borttaget ur planerarens kontrakt,
en verkningslös överutlösningsregel borttagen, handlingens namn i söktexten, OCR
mätt på verkligt arkiv, och tre rättelser av mina egna slutsatser.

## Datadisciplin

Det verkliga arkivet ligger utanför repot och får aldrig committas. Fallfilerna
med facit ligger kvar där. Ingen avtalstext finns i repot, och en
innehållsklassificerare hindrar bulkläsning — den ska inte kringgås. Facit togs
fram genom att Simon beskrev handlingarna med egna ord och sidorna slogs upp ur
indexet; endast metadata lästes.

## Säkerhetskopia

`git bundle` av hela repot ligger i `/home/aidev/brfv2-brf1-20260814.bundle`
(34 MB). Grenen är inte pushad, så den filen är enda kopian utanför
arbetskatalogen. Återställ med `git clone <bundle> <katalog>`.
