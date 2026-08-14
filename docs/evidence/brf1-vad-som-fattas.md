# BRF-1 fan-out: vad som är mätt, och den mätning som fattas före grindbeslutet

> **Uppdaterat samma dag:** mätningen nedan är utförd. Planeraren nådde
> svarsstycket i 11 av 11 verkliga fall och valde `multi` i 10 av 11 — men en
> budgetkontroll fällde samtidigt två av de tre vinster villkor C vilade på.
> Läs `planner-vs-real-model.md` tillägg 8 innan du agerar på det här
> dokumentet; beslutsregeln nedan står kvar men ska tillämpas på tilläggets
> siffror, inte på tillägg 7:s.

*Fristående underlag, 2026-08-14. Skrivet för att kunna läsas av någon utan
förkunskap om kodbasen — klistra in det i vilken AI som helst, eller läs det som
det står. Alla siffror kommer ur `docs/evidence/planner-vs-real-model.md`
(tilläggen 1–7) och `docs/evidence/fan-out-mvp-beslut.md`.*

---

## Vad det handlar om

Träff är en svenskspråkig produkt för styrelser i bostadsrättsföreningar. En
förening laddar upp sina handlingar — avtal, stadgar, årsredovisning,
underhållsplan — och ställer frågor i vanlig text. Varje svar ska bäras av
ordagranna citat som går att peka ut på rätt sida i rätt handling, och systemet
ska hellre vägra än gissa.

**BRF-1** är en tillvalsväg i den kedjan. I stället för att söka direkt på
frågan låter den först en modell *planera*: avgör om frågan besvaras av en
sökning (`single`) eller behöver skrivas om till två–tre sökningar på
handlingarnas eget språk (`multi`), kör då en gränsad fan-out, slår ihop
utdragen till en bevispåse och skickar den vidare till samma syntes- och
citatverifiering som vanligt. Vägen är dubbelgrindad — en serverflagga och ett
fält per anrop — och **avstängd i MVP**.

Motivet är **ordförrådsglappet**. Styrelsen frågar *"vem betalar om en boendes
bil blir skadad?"*; avtalet säger *"friskrivning"*. Orden möts aldrig, så en
sökning på frågans egna ord hittar ingenting — inte för att svaret saknas, utan
för att styrelsen och juristen inte talar samma språk.

Beslutet att inte skeppa vägen i MVP fattades 2026-08-13 med fyra villkor
uppskrivna för när den kan slås på igen. Tre av dem är sedan dess avklarade.
Det här dokumentet beskriver vad som återstår — och varför det viktigaste som
återstår **inte** är ett av de fyra villkoren.

---

## Vad som är mätt

Alla siffror är körda mot en riktig modell (`gemma-4-12b-it`, Q4_K_XL, llama.cpp)
genom produktionens egen kodväg. Avkodningen är girig, så en körning per fall är
hela sanningen för en given prompt.

| Villkor | Innehåll | Status |
|---|---|---|
| **A** | Noll falska motfrågor på de 46 negativa kontrollerna | **Uppfyllt strukturellt.** Läget `clarify` togs bort ur planerarens kontrakt. Det valdes 5 gånger av 59 och tystade fyra besvarbara frågor helt. |
| **B** | Överutlösning ≤ 2 av 46, eller bevis för att extra sökningar köper något | **Besvarat, inte uppfyllt.** 12 av 46 frågor planeras fortfarande som `multi`. De köper ingen recall — och kostar ingen svarskvalitet: riktig syntes på alla 12, svaren ordagrant identiska mot enkelvägen. |
| **C** | Ordförrådsvinsten reproducerad på ≥ 3 verkliga fall, varav ≥ 1 utan bro i filnamnet | **Uppfyllt med marginal.** 8 fall byggda ur två verkliga avtal; 3 visar vinsten (enkel sökning 0.00 → fan-out 1.00), och alla 3 saknar bro i filnamnet. |
| **D** | Den planerade vägen omrankar inte ens när omrankning är påslagen | **Öppet.** Ingen har mätt vad en fix skulle göra. |

Två sidofynd som inte var det någon letade efter, men som står kvar:

- **Enkelsökningens toppträff låg i fel handling i 7 av 8 verkliga fall.** I fyra
  av dem fanns rätt stycke ändå bland de sex utdrag som når prompten, så recall
  räknar dem som träffar. Produkten visar citat med sidhänvisning; ett rätt svar
  med fel avtal överst ser verifierat ut och pekar fel. Nio handlingar räckte för
  att framkalla det.
- **Planerarens utfall vänder på promptdetaljer som inte rör frågan.** Ett
  konstruerat ordförrådsfall (`r01`) gick 0.00 → 1.00 → 0.00 på tre ändringar
  varav ingen handlade om ordförråd: dokumentkatalogens sorteringsordning, och
  senare borttagningen av ett stycke om ett *annat* planeringsläge.

---

## Det som fattas

Villkoren mäter två halvor av samma funktion, och ingen mätning har satt ihop
dem:

| | korpus | delfrågor | vad det säger |
|---|---|---|---|
| Villkor A och B | rekonstruerad golden | **planerarens egna** | hur ofta planeraren väljer fel läge |
| Villkor C | **verkligt arkiv** | handskrivna, i avtalets ord | om hämtningsstrategin fungerar när den får rätt delfrågor |

**Ingen har kört den riktiga planeraren mot det verkliga arkivet.**

Det är inte en formalitet, och det är skälet till att grindbeslutet fortfarande
är för vagt att fatta. Villkor C bevisar att fan-out *kan* hitta svaret på
verklig avtalstext — men delfrågorna som åstadkom det (`friskrivning ansvar
skada`, `administrationskostnad`, `varsko betydande prisjusteringar`) skrevs för
hand. Frågan ingen har svarat på är om en riktig modell skriver dem, eller ens
väljer `multi` på de frågorna.

Och det finns konkret skäl att tvivla: på den rekonstruerade korpusen valde
planeraren `multi` på 4 av 12 tvärdokumentsfall, och tappade motivfallet helt
när en orelaterad rad togs bort ur systemprompten. Planeraren, inte
hämtningsstrategin, är den svaga länken — det är också beslutsdokumentets egen
slutsats: *"planeraren är inte klar, och en halv planerare är sämre än ingen."*

Om planeraren inte väljer `multi` på de tre fall där vinsten finns, så levererar
fan-out i produktion **noll** av det villkor C bevisade. Då är villkoret uppfyllt
och funktionen ändå värdelös. Det är den möjligheten som måste stängas innan
grinden kan öppnas eller stängas för gott.

---

## Mätningen som stänger frågan

Kör den riktiga planeraren mot det verkliga arkivet, på samma åtta fall som
villkor C mättes med. Ungefär en halvtimme, ett par dussin modellanrop.

**Så här:**

1. Bygg ett index över det verkliga arkivet med produktionens egen
   ingestionsväg. Sju av nio handlingar är skannade utan textlager och OCR:as
   automatiskt; det tar 99 sekunder totalt och ger 82–95 % ordlika tokens, vilket
   är bättre än de två digitala handlingarnas egna textlager (75 %). Läsbarhet är
   inte längre ett hinder.
2. För vart och ett av de åtta fallen, kör hela den planerade vägen med en riktig
   modell och notera fyra saker: vilket läge planeraren valde, vilka delfrågor
   den skrev, hur många sökningar som faktiskt kördes, och om det utpekade
   svarsstycket hamnade i bevispåsen.
3. Jämför mot två baslinjer som redan är mätta: enkel sökning, och fan-out med
   de handskrivna delfrågorna.

**Rapportera per fall**, inte bara i genomsnitt — tre av åtta fall bär hela
frågan, och ett medelvärde döljer dem. Ta med de fall där planeraren väljer
`single` också; ett uteblivet val är resultatet, inte frånvaro av resultat.

**Praktiskt:** arkivet får aldrig committas och avtalstext får aldrig hamna i
någon fil som checkas in. Fallfilen med facit ligger utanför repot och pekas ut
med ett argument. En innehållsklassificerare hindrar bulkläsning av korpusen —
den behöver inte kringgås, eftersom mätningen bara behöver dokument, sidnummer
och siffror.

---

## Beslutsregeln, satt i förväg

Skriv ner utfallet den ska leda till *innan* siffrorna finns, så att resultatet
inte kan bortförklaras efteråt. Ett förslag:

| Planeraren når svarsstycket på… | Slutsats |
|---|---|
| **0 av 3** vinstfall | Fan-out levererar inget i produktion. Grinden stängs för gott och koden tas bort, inte bara stängs av. |
| **1–2 av 3** | Hämtningsstrategin är bevisad, planeraren är det inte. Grinden förblir stängd, och nästa arbete är planeraren — inte hämtningen. |
| **3 av 3** | Funktionen gör i produktion vad den lovar. Grinden kan öppnas, med villkor D stängt först. |

Mellanutfallet är det troliga, och det är också det mest användbara: det flyttar
arbetet från "fungerar fan-out?" till "hur får man en 12B-modell att välja rätt
läge?", vilket är en helt annan sorts fråga med helt andra åtgärder.

---

## Villkor D, separat

Den planerade vägen omrankar inte sina utdrag ens när omrankning är påslagen och
tillgänglig. Det är inte en enradsfix: omrankningen skär bevispåsen till `topK`,
vilket skulle klippa den från upp till 10 utdrag ner till 6 och tyst kasta
fan-outens egna träffar. Det är en hämtningsändring som behöver mätas, inte en
grindparitet som kan lagas i förbifarten.

Den behöver bara lösas om grinden öppnas. Blir utfallet 0 av 3 ovan är villkor D
inte längre en fråga.

---

## Om du klistrar in det här i en AI som ska utföra arbetet

Allt ovan är kontexten. Uppgiften är punkt 1–3 under *"Mätningen som stänger
frågan"*, plus att skriva ner resultatet per fall.

Håll dig till det. Förbättra inte planerarens prompt, ändra inte
hämtningsparametrar och skriv inga nya evalfall under tiden — den här mätningen
är värdelös om koden ändras mellan baslinjen och körningen, eftersom planen är en
funktion av prompten och prompten redan har visat sig känslig för ändringar som
inte rör saken. Ser du något som borde ändras, skriv en rad om det i
slutrapporten i stället för att ändra det.

Rapportens längd ska följa substansen: siffror per fall, och vilken av de tre
raderna i beslutsregeln utfallet landar på.
